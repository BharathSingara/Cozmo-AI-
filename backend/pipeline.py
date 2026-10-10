"""Small auditable stages and geometrically conservative short-horizon deduplication."""
import asyncio, os, time, uuid
from dataclasses import dataclass,field
import cv2
from backend import store
from backend.schemas import Book,Item,Packet,now_iso
from backend.vision import decode_image,quality,local_book_candidates,local_item_candidates,remote_scene,crop_ocr,_iou
from backend.tracker import estimate_transform,match_proposals
from backend.geometry import book_spine_dimensions
from backend import catalog, pricing
from backend.catalog import identify_book
from backend.pricing import book_prices,item_price_range
from backend.calculations import calculate_totals,make_review

@dataclass
class LastFrame:
    image:object
    boxes:list
    ids:list
    item_boxes:list=field(default_factory=list)
    item_ids:list=field(default_factory=list)
    shelf:str='Shelf A'

TRACKS:dict[str,LastFrame]={}
SESSION_LOCKS:dict[str,asyncio.Lock]={}

def lock_for(sid:str):return SESSION_LOCKS.setdefault(sid,asyncio.Lock())

def update_aggregates(packet):
    packet.totals=calculate_totals(packet.books,packet.items,packet.sweep.currency)
    packet.review_queue=make_review(packet.books,packet.items,packet.room)

def stage(packet,name,start):
    packet.stage_timings_ms[name]=round(packet.stage_timings_ms.get(name,0)+(time.perf_counter()-start)*1000,2)

def is_same_shelf_object(box_a:list[int],box_b:list[int]) -> bool:
    if _iou(box_a,box_b)>0.20:return True
    wa=abs(box_a[2]-box_a[0]);ha=abs(box_a[3]-box_a[1])
    wb=abs(box_b[2]-box_b[0]);hb=abs(box_b[3]-box_b[1])
    y_overlap=max(0,min(box_a[3],box_b[3])-max(box_a[1],box_b[1]))
    min_h=min(ha,hb)
    if min_h>0 and (y_overlap/min_h)>0.55:
        ca_x=(box_a[0]+box_a[2])/2.0;cb_x=(box_b[0]+box_b[2])/2.0
        avg_w=(wa+wb)/2.0
        if abs(ca_x-cb_x)<max(32,1.3*avg_w):return True
    x_overlap=max(0,min(box_a[2],box_b[2])-max(box_a[0],box_b[0]))
    min_w=min(wa,wb)
    if min_w>0 and (x_overlap/min_w)>0.55:
        ca_y=(box_a[1]+box_a[3])/2.0;cb_y=(box_b[1]+box_b[3])/2.0
        avg_h=(ha+hb)/2.0
        if abs(ca_y-cb_y)<max(32,1.3*avg_h):return True
    return False

async def ingest(sid:str,raw:bytes,shelf:str,reference_cm:float|None=None,reference_px:float|None=None):
    async with lock_for(sid):
        t0=time.perf_counter();packet=store.load(sid)
        if packet.sweep.finished_at:raise ValueError('Finished session cannot accept more frames')
        frames=len(list((store.session_dir(sid)/'frames').glob('*.jpg')))
        if frames>=int(os.getenv('MAX_FRAMES_PER_SESSION','200')):raise ValueError('Frame cap reached')
        im=decode_image(raw)
        ref=f'frames/{uuid.uuid4().hex}.jpg'
        cv2.imwrite(str(store.session_dir(sid)/ref),im,[cv2.IMWRITE_JPEG_QUALITY,86])
        q=quality(im)
        stage(packet,'frame_processing',t0)
        t=time.perf_counter();scene,error=await remote_scene(im)
        packet.stage_api_calls['remote_vision']=packet.stage_api_calls.get('remote_vision',0)+(1 if os.getenv('ALLOW_REMOTE_VISION','false').lower()=='true' and os.getenv('GEMINI_API_KEY') else 0)
        stage(packet,'vision_detection',t)
        if scene is not None and scene.get('usage'):
            packet.cost['usage_tokens']={'input':scene['usage'].get('promptTokenCount'),'output':scene['usage'].get('candidatesTokenCount'),'total':scene['usage'].get('totalTokenCount')}
        if scene is None:
            t=time.perf_counter();candidates=local_book_candidates(im)
            item_candidates=local_item_candidates(im)
            scene={'books':candidates,'items':item_candidates}
            stage(packet,'local_book_detection',t)
            if error and error!='Remote vision is disabled or missing GEMINI_API_KEY':packet.warnings.append(error)
        if q['warnings']:packet.warnings.extend(q['warnings'])
        if not q['usable']:
            packet.warnings.append(f'{ref}: insufficient capture quality; frame kept as evidence')
            store.save(packet)
            return {'packet':packet,'quality':q,'frame_ref':ref,'new_book_ids':[],'new_item_ids':[]}
        previous=TRACKS.get(sid)
        t=time.perf_counter()
        transform=estimate_transform(previous.image,im) if previous is not None and previous.shelf==shelf else None
        new_boxes=[x['bbox'] for x in scene['books']];new_item_boxes=[x['bbox'] for x in scene['items']]
        bmatch=match_proposals(previous.boxes,new_boxes,transform) if previous else {}
        imatch=match_proposals(previous.item_boxes,new_item_boxes,transform) if previous else {}
        book_ids=[];item_ids=[];new_books=[];new_items=[]
        for idx,proposal in enumerate(scene['books']):
            matched=previous.ids[bmatch[idx]] if (previous and idx in bmatch) else None
            existing=next((b for b in packet.books if b.id==matched),None) if matched else None
            if not existing:
                p_box=proposal['bbox']
                for b in packet.books:
                    if b.shelf==shelf and not b.excluded and is_same_shelf_object(b.bbox,p_box):
                        existing=b;break
            if existing:
                if ref not in existing.evidence_refs:existing.evidence_refs.append(ref)
                book_ids.append(existing.id);continue
            bid='book_'+uuid.uuid4().hex[:12]
            book=Book(id=bid,shelf=shelf,position=sum(b.shelf==shelf for b in packet.books)+1,frame_ref=ref,
             bbox=proposal['bbox'],evidence_refs=[ref],detection_source=proposal.get('source','visual_model'),
             id_confidence=0,notes=['Object boundary is a proposal; verify count and read spine'])
            if proposal.get('title'):book.notes.append('Unverified image-model text: '+str(proposal['title'])[:90])
            h,th=book_spine_dimensions(proposal['bbox'],ref,reference_px,reference_cm)
            if h and th:
                book.height_measurement=h;book.thickness_measurement=th
                book.spine_height_cm=h.value;book.spine_thickness_cm=th.value;book.measurement_confidence=min(h.confidence,th.confidence)
            packet.books.append(book);new_books.append((bid,proposal,im.copy()))
            book_ids.append(bid)
        for idx,proposal in enumerate(scene['items']):
            matched=previous.item_ids[imatch[idx]] if (previous and idx in imatch) else None
            existing=next((i for i in packet.items if i.id==matched),None) if matched else None
            if not existing:
                p_box=proposal['bbox']
                for it in packet.items:
                    if not it.excluded and is_same_shelf_object(it.bbox,p_box):
                        existing=it;break
            if existing:
                if ref not in existing.evidence_refs:existing.evidence_refs.append(ref)
                item_ids.append(existing.id);continue
            iid='item_'+uuid.uuid4().hex[:12]
            cat=proposal['category']
            item=Item(id=iid,category=cat,description=proposal['description'],brand_model=proposal.get('brand_model'),
             frame_ref=ref,bbox=proposal['bbox'],evidence_refs=[ref],confidence=proposal['confidence'],
             status='needs_appraisal',notes=['Classification is a visual proposal; verify object and make/model'])
            if reference_cm is not None and reference_px is not None:
                m_h,m_w=book_spine_dimensions(proposal['bbox'],ref,reference_px,reference_cm)
                item.dimensions_cm['w']=m_w.value;item.dimensions_cm['h']=m_h.value
                item.dimension_measurements['w']=m_w;item.dimension_measurements['h']=m_h
                item.notes.append('Width and height are same-plane estimates; depth unavailable')
            packet.items.append(item);new_items.append(iid);item_ids.append(iid)
        if previous and transform is None and previous.shelf==shelf:
            packet.warnings.append(f'{ref}: camera alignment weak; possible duplicate objects require review')
        TRACKS[sid]=LastFrame(image=im,boxes=new_boxes,ids=book_ids,item_boxes=new_item_boxes,item_ids=item_ids,shelf=shelf)
        stage(packet,'book_detection_tracking',t)
        update_aggregates(packet);store.save(packet)
    return {'packet':packet,'quality':q,'frame_ref':ref,'new_book_ids':new_books,'new_item_ids':new_items}

async def enrich(sid:str,new_books:list,new_item_ids:list):
    """Enrichment runs after live update; records remain even if services fail."""
    for bid,proposal,image in new_books:
        t=time.perf_counter();raw_ocr=await asyncio.to_thread(crop_ocr,image,proposal['bbox'])
        async with lock_for(sid):
            packet=store.load(sid);book=next((b for b in packet.books if b.id==bid),None)
            if not book or book.excluded:continue
            book.ocr_text=raw_ocr or None
            if raw_ocr:book.notes.append('OCR candidate: '+raw_ocr[:100])
            stage(packet,'ocr',t);store.save(packet)
        t=time.perf_counter()
        catalog,reason=await identify_book(raw_ocr,proposal.get('title'),proposal.get('author'))
        if proposal.get('source')=='local_contour_candidate' and not catalog and not proposal.get('title'):
            words=[re.sub(r'[^a-zA-Z]','',w).lower() for w in (raw_ocr or '').split()]
            vowels=set('aeiouy')
            valid_words=[w for w in words if len(w)>=3 and any(c in vowels for c in w)]
            has_genuine_title=any(len(w)>=4 for w in valid_words) or len(valid_words)>=2
            if not has_genuine_title:
                async with lock_for(sid):
                    packet=store.load(sid)
                    packet.books=[b for b in packet.books if b.id!=bid]
                    update_aggregates(packet);store.save(packet)
                continue
        async with lock_for(sid):
            packet=store.load(sid);book=next((b for b in packet.books if b.id==bid),None)
            if not book or book.excluded:continue
            if catalog:
                book.title=catalog['title'];book.author=catalog['author'];book.id_confidence=catalog['score']
                # Do not assert a printed edition or ISBN from work-level catalog data.
                book.status='identified';book.notes.append('Verified work: '+catalog['work_url'])
            elif reason:book.notes.append(reason)
            if os.getenv('ALLOW_EXTERNAL_LOOKUPS','true').lower()=='true':
                packet.stage_api_calls['catalogue']=packet.stage_api_calls.get('catalogue',0)+1
            stage(packet,'book_identification',t)
            update_aggregates(packet);store.save(packet)
        if catalog:
            t=time.perf_counter()
            replacement,used=await book_prices(catalog['title'],catalog['author'],None,packet.sweep.country,packet.sweep.currency)
            async with lock_for(sid):
                packet=store.load(sid);book=next((b for b in packet.books if b.id==bid),None)
                if book and not book.excluded:
                    book.replacement_cost=replacement;book.used_value=used
                    book.valuation_confidence=min([p.match_confidence for p in (replacement,used) if p.match_confidence is not None],default=0)
                    default_thresholds={'INR':80000,'USD':1000,'GBP':800,'EUR':900,'CAD':1400,'AUD':1600}
                    threshold=float(os.getenv('APPRAISAL_THRESHOLD_'+packet.sweep.currency,default_thresholds.get(packet.sweep.currency,1000.0)))
                    if any(p.amount is not None and p.amount>=threshold for p in (replacement,used)):
                        book.status='needs_appraisal'
                        book.notes.append(f'Price exceeds {threshold} {packet.sweep.currency} appraisal threshold; listing indicative only')
                if os.getenv('ALLOW_EXTERNAL_LOOKUPS','false').lower()=='true':
                    packet.stage_api_calls['market_listings']=packet.stage_api_calls.get('market_listings',0)+1
                stage(packet,'book_price_retrieval',t);update_aggregates(packet);store.save(packet)
    for iid in new_item_ids:
        async with lock_for(sid):
            packet=store.load(sid);item=next((i for i in packet.items if i.id==iid),None)
            if not item or item.excluded or 'artwork' in item.category:continue
            q=(item.description,item.brand_model,packet.sweep.country,packet.sweep.currency)
        t=time.perf_counter();price=await item_price_range(*q)
        async with lock_for(sid):
            packet=store.load(sid);item=next((i for i in packet.items if i.id==iid),None)
            if item and not item.excluded:
                item.replacement_cost=price;item.status='range' if price.low is not None else 'needs_appraisal'
            if os.getenv('ALLOW_EXTERNAL_LOOKUPS','false').lower()=='true' and item and item.brand_model:
                packet.stage_api_calls['market_listings']=packet.stage_api_calls.get('market_listings',0)+1
            stage(packet,'non_book_pricing',t);update_aggregates(packet);store.save(packet)

async def recheck_book(sid:str,bid:str,title:str):
    """Re-enrich a book following user title correction."""
    catalog_res,reason=await catalog.identify_book(title,title_hint=title)
    async with lock_for(sid):
        packet=store.load(sid);book=next((b for b in packet.books if b.id==bid),None)
        if not book or book.excluded:return
        if catalog_res:
            book.title=catalog_res['title'];book.author=catalog_res['author'];book.id_confidence=catalog_res['score']
            book.status='identified';book.notes.append('User correction verified work: '+catalog_res['work_url'])
        elif reason:
            book.notes.append('Correction verification: '+reason)
        update_aggregates(packet);store.save(packet)
    if catalog_res:
        replacement,used=await pricing.book_prices(catalog_res['title'],catalog_res['author'],None,packet.sweep.country,packet.sweep.currency)
        async with lock_for(sid):
            packet=store.load(sid);book=next((b for b in packet.books if b.id==bid),None)
            if book and not book.excluded:
                book.replacement_cost=replacement;book.used_value=used
                book.valuation_confidence=min([p.match_confidence for p in (replacement,used) if p.match_confidence is not None],default=0)
                default_thresholds={'INR':80000,'USD':1000,'GBP':800,'EUR':900,'CAD':1400,'AUD':1600}
                threshold=float(os.getenv('APPRAISAL_THRESHOLD_'+packet.sweep.currency,default_thresholds.get(packet.sweep.currency,1000.0)))
                if any(p.amount is not None and p.amount>=threshold for p in (replacement,used)):
                    book.status='needs_appraisal'
            update_aggregates(packet);store.save(packet)
