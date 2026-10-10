"""Frame quality, conservative local candidate proposals, optional remote multimodal detector."""
import base64, json, os, re, time
import cv2, httpx, numpy as np, pytesseract

CATEGORIES={'bookshelf','cabinet','desk','table','chair','coffee machine','appliance','lamp','electronics','rug','artwork','framed artwork','decorative object','sofa','furniture','other'}

def decode_image(raw:bytes):
    arr=np.frombuffer(raw,dtype=np.uint8)
    im=cv2.imdecode(arr,cv2.IMREAD_COLOR)
    if im is None or min(im.shape[:2])<100: raise ValueError('Invalid image or too small')
    if max(im.shape[:2])>2200:
        ratio=2200/max(im.shape[:2]);im=cv2.resize(im,None,fx=ratio,fy=ratio)
    return im

def quality(image):
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    blur=float(cv2.Laplacian(gray,cv2.CV_64F).var())
    glare=float(np.mean(np.all(image>245,axis=2)))
    under=float(np.mean(gray<25))
    messages=[]
    if blur<85: messages.append('Motion blur: slow down and hold the camera steady')
    if glare>.09: messages.append('Glare detected: tilt the camera away from direct reflection')
    if under>.35: messages.append('Low light: illuminate the shelf')
    return {'blur_score':round(blur,2),'glare_fraction':round(glare,3),'dark_fraction':round(under,3),'warnings':messages,'usable':blur>=35 and glare<.35}

def _bbox(box,shape):
    h,w=shape[:2]
    if not isinstance(box,list) or len(box)!=4: return None
    try: y1,x1,y2,x2=[min(1000,max(0,float(v))) for v in box]
    except (ValueError,TypeError): return None
    b=[round(x1*w/1000),round(y1*h/1000),round(x2*w/1000),round(y2*h/1000)]
    if b[2]-b[0]<5 or b[3]-b[1]<10: return None
    return b

def local_book_candidates(image):
    """Conservative region proposals; NOT an accurate general book detector.
    Detects both upright slender vertical spines and horizontal flat/stacked spines.
    """
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    blur=cv2.GaussianBlur(gray,(3,3),0)
    edges=cv2.Canny(blur,55,145)
    edges_v=cv2.morphologyEx(edges,cv2.MORPH_CLOSE,np.ones((5,2),np.uint8))
    edges_h=cv2.morphologyEx(edges,cv2.MORPH_CLOSE,np.ones((2,5),np.uint8))
    combined=cv2.bitwise_or(edges_v,edges_h)
    contours,_=cv2.findContours(combined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    ycrcb=cv2.cvtColor(image,cv2.COLOR_BGR2YCrCb)
    skin=cv2.inRange(ycrcb,np.array([0,133,77]),np.array([255,173,127]))
    h,w=gray.shape; boxes=[]
    for c in contours:
        x,y,bw,bh=cv2.boundingRect(c)
        area=bw*bh
        # Exclude artifacts touching the extreme edges of the camera sensor
        if x<=5 or y<=5 or (x+bw)>=w-5 or (y+bh)>=h-5: continue
        if area<0.010*w*h or area>0.35*w*h: continue
        # Upright book spine condition: slender vertical rectangle occupying at least 20% of frame height
        is_upright = (bh>=0.20*h and bw>=12 and bw<=0.22*w and bh<=0.88*h and (bh/max(bw,1))>=1.6)
        # Flat/stacked book spine condition: slender horizontal rectangle
        is_stacked = (bw>=0.20*w and bh>=16 and bh<=0.22*h and bw<=0.55*w and (bw/max(bh,1))>=1.6)
        if not (is_upright or is_stacked):
            continue
        # Reject human skin (faces, hands, neck)
        skin_roi=skin[y:y+bh,x:x+bw]
        if cv2.countNonZero(skin_roi)/max(area,1)>0.25: continue
        # Reject completely flat/monotone surfaces (plain solid wall or shirt)
        gray_roi=gray[y:y+bh,x:x+bw]
        if float(np.std(gray_roi))<14.0: continue
        roi=combined[y:y+bh,x:x+bw]
        density=cv2.countNonZero(roi)/max(area,1)
        if 0.015<=density<=0.55:
            boxes.append([x,y,x+bw,y+bh])
    boxes=sorted(boxes,key=lambda b:(b[0],b[1]))
    kept=[]
    for b in boxes:
        if any(_iou(b,k)>0.25 or (b[0]>=k[0] and b[2]<=k[2] and b[1]>=k[1] and b[3]<=k[3]) for k in kept): continue
        kept.append(b)
    return [{'bbox':b,'title':None,'author':None,'edition':None,'confidence':0.35,'source':'local_contour_candidate'} for b in kept[:25]]

def local_item_candidates(image):
    """Propose large rectangular non-book belongings (shelving, furniture, artwork) in offline mode."""
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    blur=cv2.GaussianBlur(gray,(5,5),0)
    thresh=cv2.adaptiveThreshold(blur,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,15,4)
    contours,_=cv2.findContours(thresh,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    h,w=gray.shape; items=[]
    for c in contours:
        x,y,bw,bh=cv2.boundingRect(c)
        area=bw*bh
        if area<0.04*w*h or bw>=0.96*w or bh>=0.96*h:
            continue
        aspect=bw/max(bh,1)
        # Heuristic classification based on geometry and position
        if bh>0.4*h and aspect<1.2:
            cat='bookshelf'
            desc='Shelving unit or vertical bookcase'
        elif y<0.4*h and 0.6<=aspect<=1.8 and area<0.25*w*h:
            cat='artwork'
            desc='Framed artwork or wall hanging'
        elif y>0.3*h and aspect>=1.0:
            cat='furniture'
            desc='Desk, table, or seating furniture'
        else:
            cat='electronics' if 0.8<=aspect<=2.0 and area>0.08*w*h else 'furniture'
            desc='Room electronics or furnishing'
        items.append({'bbox':[x,y,x+bw,y+bh],'category':cat,'description':desc,'brand_model':None,'confidence':0.45})
    items=sorted(items,key=lambda i: (i['bbox'][2]-i['bbox'][0])*(i['bbox'][3]-i['bbox'][1]),reverse=True)
    kept=[]
    for it in items:
        if any(_iou(it['bbox'],k['bbox'])>0.30 for k in kept): continue
        kept.append(it)
    return kept[:10]

def _iou(a,b):
    x1=max(a[0],b[0]);y1=max(a[1],b[1]);x2=min(a[2],b[2]);y2=min(a[3],b[3])
    intersection=max(0,x2-x1)*max(0,y2-y1)
    if not intersection: return 0
    return intersection / max(1,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection)

def crop_ocr(image,bbox):
    x1,y1,x2,y2=bbox
    crop=image[max(0,y1):y2,max(0,x1):x2]
    if crop.size==0:return ''
    # Enhance contrast with CLAHE
    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
    clahe=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8))
    enhanced=clahe.apply(gray)
    variants=[crop, cv2.cvtColor(enhanced,cv2.COLOR_GRAY2BGR),
              cv2.rotate(crop,cv2.ROTATE_90_CLOCKWISE),
              cv2.rotate(crop,cv2.ROTATE_90_COUNTERCLOCKWISE)]
    found=[]
    for im in variants:
        if max(im.shape[:2])<120:
            scale=max(2.0, 180/max(im.shape[:2]))
            im=cv2.resize(im,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
        for psm in ('--psm 6', '--psm 11', '--psm 3'):
            try:
                t=pytesseract.image_to_string(im,config=psm,timeout=2)
                t=' '.join(t.split())
                if t and any(c.isalpha() for c in t) and len(t)>=3:
                    found.append(t)
            except (RuntimeError,pytesseract.TesseractNotFoundError):
                pass
    return max(found,key=len,default='')[:180]

async def remote_scene(image):
    """Gemini generateContent JSON. Returns validated box proposals, not guaranteed identities."""
    if os.getenv('ALLOW_REMOTE_VISION','false').lower()!='true' or not os.getenv('GEMINI_API_KEY'):
        return None,'Remote vision is disabled or missing GEMINI_API_KEY'
    model=os.getenv('GEMINI_MODEL','gemini-2.5-flash')
    _,jpeg=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,80])
    instruction='''Analyze a photograph from a home-library camera sweep. Return only JSON with keys "books" and "items", both arrays. For EVERY VISIBLE INDIVIDUAL BOOK SPINE (including stacked horizontal books), return bbox=[ymin,xmin,ymax,xmax] coordinates 0..1000, possible_title (string or null), possible_author (string or null), confidence 0..1. Distinguish adjacent individual spines; do not invent words you cannot clearly read. For non-book physical objects return category, description, brand_model only if directly legible, bbox, confidence. Do not include people or private documents. Artwork category must be "artwork". Never supply price, dimension or ISBN. Only box actual visible objects. If uncertain omit details, not object.'''
    payload={'contents':[{'parts':[{'text':instruction},{'inline_data':{'mime_type':'image/jpeg','data':base64.b64encode(jpeg).decode()}}]}], 'generationConfig':{'responseMimeType':'application/json','temperature':0.0}}
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response=await client.post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',params={'key':os.environ['GEMINI_API_KEY']},json=payload)
            response.raise_for_status()
            obj=response.json()
        body=obj['candidates'][0]['content']['parts'][0]['text'].strip()
        if body.startswith('```'):
            body=re.sub(r'^```(?:json)?\s*','',body)
            body=re.sub(r'\s*```$','',body)
        parsed=json.loads(body.strip())
        if not isinstance(parsed,dict):raise ValueError('Invalid VLM output')
        books=[];items=[]
        for b in parsed.get('books',[])[:120]:
            bb=_bbox(b.get('bbox'),image.shape)
            if bb: books.append({'bbox':bb,'title':b.get('possible_title') if isinstance(b.get('possible_title'),str) else None,
                                'author':b.get('possible_author') if isinstance(b.get('possible_author'),str) else None,
                                'confidence':min(1.,max(0.,float(b.get('confidence',.2)))),'source':'gemini_visual_proposal'})
        for i in parsed.get('items',[])[:60]:
            bb=_bbox(i.get('bbox'),image.shape)
            if bb:
                category=str(i.get('category','other')).lower()
                items.append({'bbox':bb,'category':category if category in CATEGORIES else 'other',
                  'description':str(i.get('description','visible belonging'))[:150],
                  'brand_model':str(i['brand_model'])[:100] if i.get('brand_model') else None,
                  'confidence':min(1.,max(0.,float(i.get('confidence',.2))))})
        return {'books':books,'items':items,'usage':obj.get('usageMetadata',{})},None
    except (httpx.HTTPError,ValueError,KeyError,IndexError,TypeError) as exc:
        return None,f'Remote vision unavailable: {type(exc).__name__}: {str(exc)[:130]}'
