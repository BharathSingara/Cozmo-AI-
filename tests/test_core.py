import io,json,os,uuid,zipfile
import cv2,numpy as np,pytest
from fastapi.testclient import TestClient
from backend import store
from backend.schemas import Book,Item,Room,Packet,Sweep,Totals,Price,PriceRange
from backend.calculations import rectangular_room,polygon_area,populate_room,calculate_totals,make_review
from backend.geometry import metric_from_reference,book_spine_dimensions
from backend.pricing import validate_market,convert,choose_listing
from backend.vision import quality,_bbox,local_book_candidates,local_item_candidates
from backend.tracker import match_proposals
from backend.reporting import html_report,write_claim,pdf_report
from backend.catalog import similarity
from backend.api import app

@pytest.fixture
def session_root(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path/'sessions')
    monkeypatch.setenv('ALLOW_REMOTE_VISION','false')
    monkeypatch.setenv('ALLOW_EXTERNAL_LOOKUPS','false')
    monkeypatch.delenv('APP_ACCESS_KEY',raising=False)
    return store.ROOT

def packet(session_root):
    p=Packet(sweep=Sweep(id=uuid.uuid4().hex,captured_at='2026-10-09',device='test synthetic',country='IN',currency='INR'),room=Room(),books=[],items=[],totals=Totals(currency='INR'),review_queue=[])
    store.create(p);return p

def synthetic_frame():
    img=np.full((480,720,3),[68,78,96],np.uint8)
    for x in range(50,600,29):
        cv2.rectangle(img,(x,60),(x+20,350),((x*3)%200+30,(x*5)%180+40,(x*7)%150+60),-1)
        cv2.rectangle(img,(x,60),(x+20,350),(235,235,235),2)
        cv2.putText(img,'BOOK',(x,150),cv2.FONT_HERSHEY_SIMPLEX,.25,(255,255,255),1)
    ok,jpg=cv2.imencode('.jpg',img)
    assert ok
    return bytes(jpg)

def test_rectangle():assert rectangular_room(4,3,2.5)==(12,35)
def test_irregular_polygon():assert polygon_area([(0,0),(4,0),(4,2),(2,2),(2,4),(0,4)])==12

def test_room_unmeasured_is_none():assert populate_room(Room()).floor_area_m2 is None

def test_room_unconfirmed_shape():
    r=populate_room(Room(length_m=3,width_m=4,height_m=2.5,shape='irregular'))
    assert r.wall_area_m2 is None

def test_measurement_reference():
    m=metric_from_reference(30,150,30,'frames/frame.jpg')
    assert m.value==6 and m.method=='coplanar_known_width_pixel_ratio' and m.uncertainty>0

def test_measurement_missing_scale():assert book_spine_dimensions([1,2,20,200],'frames/f.jpg',None,None)==(None,None)

def test_negative_scale():
    with pytest.raises(ValueError):metric_from_reference(15,0,25,'f')

def test_market_validation():
    assert validate_market('in','inr')==('IN','INR')
    with pytest.raises(ValueError):validate_market('IN','USD')

def test_currency_conversion_documented_rate():
    assert convert(10,'USD','INR',85,'verified_bank_rate')==(850,True)
    with pytest.raises(ValueError):convert(10,'USD','INR',None)

def test_pricing_rejects_untraceable():
    with pytest.raises(ValueError):Price(amount=150,currency='INR')
    with pytest.raises(ValueError):PriceRange(low=1,high=2)

def test_pricing_rejects_ebooks():
    listing=[{'title':'Novel eBook Kindle','price':{'value':'12','currency':'INR'},'condition':'NEW','itemWebUrl':'https://example.com/1'}]
    assert choose_listing(listing,'INR','new') is None

def test_price_sum_missing_excluded_and_shelf_run(session_root):
    p=packet(session_root)
    ref='frames/a.jpg';(store.session_dir(p.sweep.id)/ref).write_bytes(b'fake')
    a=Book(id='a',shelf='A',position=1,frame_ref=ref,status='identified',title='Sample',spine_thickness_cm=3,
        replacement_cost=Price(amount=250,currency='INR',source='shop',url='https://example.com',retrieved_at='2026-10-09'))
    b=Book(id='b',shelf='A',position=2,frame_ref=ref)
    c=Book(id='c',shelf='A',position=3,frame_ref=ref,excluded=True)
    totals=calculate_totals([a,b,c],[], 'INR')
    assert totals.book_count==2 and totals.books_replacement_cost==250 and totals.shelf_run_m is None and totals.excluded_from_totals==1 and totals.unpriced_books==2

def test_distinct_titles_not_deduplicated_by_name():
    from backend.tracker import match_proposals
    # Dedup is geometric, not title-based: missing homography means no merge.
    assert match_proposals([[10,10,30,90]],[[10,10,30,90]],None)=={}

def test_track_one_to_one():
    m=np.eye(3);matches=match_proposals([[0,0,20,90],[23,0,45,90]],[[1,1,21,91],[24,1,46,91]],m)
    assert matches=={0:0,1:1}

def test_review_queue_preserves_uncertainty(session_root):
    p=packet(session_root);b=Book(id='x',shelf='A',position=1,frame_ref='frames/f.jpg')
    issues=make_review([b],[],Room());assert len(issues)>=3 and any('unverified' in i.reason for i in issues)

def test_missing_evidence_rejected(session_root):
    p=packet(session_root);p.books=[Book(id='x',shelf='A',position=1,frame_ref='frames/missing.jpg')]
    with pytest.raises(ValueError,match='Missing evidence'):write_claim(p)

def test_html_escaping(session_root):
    p=packet(session_root);p.books=[Book(id='b',shelf='A',position=1,frame_ref='frames/x.jpg',title='<script>alert(1)</script>')]
    assert '&lt;script&gt;' in html_report(p)

def test_blur_detected():
    im=np.full((320,320,3),120,np.uint8)
    assert any('blur' in x.lower() for x in quality(im)['warnings'])

def test_glare_detected():
    im=np.full((320,320,3),255,np.uint8)
    assert quality(im)['glare_fraction']>.9

def test_bbox_validation():
    assert _bbox([100,100,800,900],(100,200,3))==[20,10,180,80]
    assert _bbox([800,900,100,100],(100,200,3)) is None

def test_local_candidates_returns_safe_shape():
    im=cv2.imdecode(np.frombuffer(synthetic_frame(),np.uint8),cv2.IMREAD_COLOR)
    boxes=local_book_candidates(im)
    assert isinstance(boxes,list) and all(b['title'] is None for b in boxes)

def test_json_contract_schema(session_root):
    p=packet(session_root);obj=json.loads(p.model_dump_json());assert {'sweep','room','books','items','totals','review_queue'}<=set(obj)
    assert Packet.model_validate(obj)

def test_integration_full_sweep(session_root):
    with TestClient(app) as c:
        init=c.post('/api/sessions',json={'country':'IN','currency':'INR','device':'synthetic automated test'});assert init.status_code==201
        sid=init.json()['id']
        image=synthetic_frame();response=c.post(f'/api/sessions/{sid}/frames?shelf=A',content=image,headers={'content-type':'image/jpeg'})
        assert response.status_code==200,response.text
        ref=response.json()['frame_ref'];assert store.evidence_exists(sid,ref)
        room=c.post(f'/api/sessions/{sid}/room',json={'length_m':4,'width_m':3,'height_m':2.5,'shape':'rectangular','scale_method':'user_reported_during_sweep','reference_frame':ref})
        assert room.status_code==200 and room.json()['floor_area_m2']==12
        corrected=c.post(f'/api/sessions/{sid}/corrections',json={'command':'missed_shelf'});assert corrected.status_code==200
        finish=c.post(f'/api/sessions/{sid}/finish');assert finish.status_code==200,finish.text
        final=finish.json()['packet'];assert final['room']['floor_area_m2']==12 and final['sweep']['finished_at']
        assert c.get(f'/api/sessions/{sid}/report').status_code==200
        schema=c.get(f'/api/sessions/{sid}/packet');assert schema.status_code==200
        packet_data=schema.json();assert packet_data['totals']==final['totals']
        z=c.get(f'/api/sessions/{sid}/archive');assert z.status_code==200
        with zipfile.ZipFile(io.BytesIO(z.content)) as archive:
            assert {'claim_report.html','claim_packet.json',ref}<=set(archive.namelist())
        assert c.delete(f'/api/sessions/{sid}').status_code==204
        assert not store.session_dir(sid).exists()

def test_bad_market(session_root):
    with TestClient(app) as c:
        assert c.post('/api/sessions',json={'country':'US','currency':'INR'}).status_code==422

def test_invalid_frame_returns_error(session_root):
    with TestClient(app) as c:
        sid=c.post('/api/sessions',json={'country':'IN','currency':'INR'}).json()['id']
        assert c.post(f'/api/sessions/{sid}/frames',content=b'not-a-jpeg',headers={'content-type':'image/jpeg'}).status_code==422

def test_private_access_when_key_set(session_root,monkeypatch):
    monkeypatch.setenv('APP_ACCESS_KEY','test-only')
    with TestClient(app) as c:
        assert c.post('/api/sessions',json={'country':'IN','currency':'INR'}).status_code==401
        assert c.post('/api/sessions',json={'country':'IN','currency':'INR'},headers={'x-access-key':'test-only'}).status_code==201

def test_appraisal_listing_excluded_from_financial_totals(session_root):
    p=packet(session_root)
    source=dict(amount=2000,currency='INR',source='vendor',url='https://example.com/book',retrieved_at='2026-10-09')
    b=Book(id='rare',shelf='S',position=1,frame_ref='frames/frame.jpg',status='needs_appraisal',
           replacement_cost=Price(**source),used_value=Price(**source))
    t=calculate_totals([b],[],'INR')
    assert t.book_count==1 and t.books_replacement_cost==0 and t.books_used_value==0
    assert t.excluded_from_totals==1

@pytest.mark.asyncio
async def test_book_price_provenance_mocked(monkeypatch):
    from backend import pricing
    async def listing(query,country,limit=20):
        return ([{'title':'Sample Novel by Writer paperback','price':{'value':'300','currency':'INR'},'condition':'NEW','itemWebUrl':'https://shop.example/new'},
                 {'title':'Sample Novel by Writer used paperback','price':{'value':'150','currency':'INR'},'condition':'GOOD','itemWebUrl':'https://shop.example/used'}],None)
    monkeypatch.setattr(pricing,'search_listings',listing)
    a,b=await pricing.book_prices('Sample Novel','Writer',None,'IN','INR')
    assert a.amount==300 and b.amount==150
    assert a.url=='https://shop.example/new' and b.url=='https://shop.example/used'

@pytest.mark.asyncio
async def test_missing_vendor_yields_null_price(monkeypatch):
    from backend import pricing
    async def no_lookup(query,country,limit=20):return [],'Network timeout'
    monkeypatch.setattr(pricing,'search_listings',no_lookup)
    a,b=await pricing.book_prices('A book',None,None,'IN','INR')
    assert a.amount is None and b.amount is None
    assert a.unavailable_reason=='Network timeout'

def test_pdf_report_generation(session_root):
    p=packet(session_root)
    ref='frames/f.jpg';(store.session_dir(p.sweep.id)/ref).write_bytes(b'fake')
    p.books=[Book(id='b1',shelf='A',position=1,frame_ref=ref,title='Test Book',author='Author',status='identified',spine_height_cm=20,spine_thickness_cm=3)]
    pdf_bytes=pdf_report(p)
    assert isinstance(pdf_bytes,bytes) and len(pdf_bytes)>500
    assert pdf_bytes.startswith(b'%PDF-')

def test_horizontal_stacked_book_detection_and_sizing():
    img=np.full((400,600,3),[50,60,70],np.uint8)
    # Draw horizontal stacked book (wide and slender)
    cv2.rectangle(img,(100,200),(350,230),(180,100,60),-1)
    cv2.rectangle(img,(100,200),(350,230),(240,240,240),2)
    cv2.putText(img,'HORIZONTAL',(120,222),cv2.FONT_HERSHEY_SIMPLEX,0.3,(255,255,255),1)
    candidates=local_book_candidates(img)
    assert len(candidates)>=1
    # Check that spine dimensions compute long dimension as height and short as thickness
    h_m,th_m=book_spine_dimensions([100,200,350,230],'frames/h.jpg',reference_px=100,reference_cm=10)
    assert h_m is not None and th_m is not None
    assert h_m.value==25.0 and th_m.value==3.0

def test_local_item_candidates_offline():
    img=np.full((500,700,3),[40,40,40],np.uint8)
    # Draw large furniture-like rectangle
    cv2.rectangle(img,(100,250),(600,450),(120,120,120),-1)
    cv2.rectangle(img,(100,250),(600,450),(200,200,200),2)
    items=local_item_candidates(img)
    assert len(items)>=1 and items[0]['category'] in ('furniture','bookshelf','artwork')

def test_irregular_room_with_perimeter_and_area():
    points=[(0.0,0.0),(4.0,0.0),(4.0,3.0),(0.0,3.0)]
    r=populate_room(Room(shape='irregular',height_m=2.5),points)
    assert r.floor_area_m2==12.0
    # Perimeter is 4+3+4+3=14; wall area is 14*2.5=35.0
    assert r.wall_area_m2==35.0
    assert r.floor_area_ft2>100 and r.wall_area_ft2>300

def test_subtitle_similarity_matching():
    # Subtitle match should succeed
    s=similarity('The Great Gatsby: A Novel','The Great Gatsby')
    assert s>=0.85
    # Completely different titles should have low score
    s2=similarity('The Great Gatsby','Moby Dick')
    assert s2<0.4

@pytest.mark.asyncio
async def test_recheck_book_on_title_correction(session_root,monkeypatch):
    p=packet(session_root)
    ref='frames/f.jpg';(store.session_dir(p.sweep.id)/ref).write_bytes(b'fake')
    b=Book(id='b_test',shelf='A',position=1,frame_ref=ref,title='Original Title')
    p.books=[b]
    store.save(p)
    from backend import catalog,pipeline
    async def mock_identify(text,title_hint=None,author_hint=None):
        return {'title':'Corrected Verified Title','author':'Known Author','work_url':'https://openlibrary.org/works/OL123W','score':0.95},None
    monkeypatch.setattr(catalog,'identify_book',mock_identify)
    await pipeline.recheck_book(p.sweep.id,'b_test','Corrected Verified Title')
    updated=store.load(p.sweep.id)
    ub=next(x for x in updated.books if x.id=='b_test')
    assert ub.status=='identified'
    assert ub.title=='Corrected Verified Title'
    assert ub.author=='Known Author'

def test_pdf_endpoint_in_full_sweep(session_root):
    with TestClient(app) as c:
        init=c.post('/api/sessions',json={'country':'IN','currency':'INR','device':'test pdf'}).json()
        sid=init['id']
        image=synthetic_frame()
        c.post(f'/api/sessions/{sid}/frames?shelf=A',content=image,headers={'content-type':'image/jpeg'})
        fin=c.post(f'/api/sessions/{sid}/finish')
        assert fin.status_code==200
        pdf_resp=c.get(f'/api/sessions/{sid}/report/pdf')
        assert pdf_resp.status_code==200
        assert pdf_resp.headers['content-type']=='application/pdf'
        assert pdf_resp.content.startswith(b'%PDF-')
        c.delete(f'/api/sessions/{sid}')

