"""Same-origin live capture server, explicit configuration and evidence-gated claims."""
import asyncio, os, secrets, time, uuid, zipfile, io
from pathlib import Path
from fastapi import FastAPI,Body,Header,HTTPException,Request
from fastapi.responses import FileResponse,HTMLResponse,Response,StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from backend import store
from backend.schemas import Packet,Sweep,Room,Totals,now_iso
from backend.pricing import validate_market
from backend.calculations import populate_room
from backend.pipeline import ingest,enrich,lock_for,update_aggregates,TRACKS,recheck_book
from backend.reporting import write_claim

app=FastAPI(title='Library Contents Claim Agent',version='0.1.0')
FRONT=Path(__file__).resolve().parent.parent/'frontend'
TASKS:dict[str,list[asyncio.Task]]={}
STARTS:dict[str,float]={}

@app.middleware('http')
async def guard(request:Request,call_next):
    key=os.getenv('APP_ACCESS_KEY','')
    if request.url.path.startswith('/api/') and key and not secrets.compare_digest(request.headers.get('x-access-key',''),key):
        return Response('Unauthorized',status_code=401)
    return await call_next(request)

class SessionCreate(BaseModel):
    country:str='IN'
    currency:str='INR'
    device:str='browser-camera'

class Correction(BaseModel):
    command:str
    ref_id:str|None=None
    value:str|None=None
    shelf:str|None=None

class RoomInput(BaseModel):
    length_m:float|None=Field(default=None,gt=0)
    width_m:float|None=Field(default=None,gt=0)
    height_m:float|None=Field(default=None,gt=0)
    shape:str|None=None
    scale_method:str|None=None
    shelved_wall_area_m2:float|None=Field(default=None,ge=0)
    reference_frame:str|None=None
    polygon_points:list[list[float]]|None=None

@app.get('/api/health')
async def health():return {'ok':True,'remote_vision_enabled':os.getenv('ALLOW_REMOTE_VISION','false').lower()=='true' and bool(os.getenv('GEMINI_API_KEY')),'external_lookups_enabled':os.getenv('ALLOW_EXTERNAL_LOOKUPS','true').lower()=='true'}

@app.post('/api/sessions',status_code=201)
async def create_session(body:SessionCreate):
    try:country,currency=validate_market(body.country,body.currency)
    except ValueError as e:raise HTTPException(422,str(e))
    sid=uuid.uuid4().hex
    packet=Packet(sweep=Sweep(id=sid,captured_at=now_iso(),device=body.device[:140],country=country,currency=currency),
      room=Room(),books=[],items=[],totals=Totals(currency=currency),review_queue=[])
    update_aggregates(packet)
    store.create(packet);STARTS[sid]=time.monotonic();TASKS[sid]=[]
    return {'id':sid,'packet':packet}

@app.get('/api/sessions/{sid}')
async def get_session(sid:str):
    try:return store.load(sid)
    except (FileNotFoundError,ValueError):raise HTTPException(404,'No such session')

@app.post('/api/sessions/{sid}/frames')
async def frames(sid:str,request:Request,shelf:str='Shelf A',reference_cm:float|None=None,reference_px:float|None=None):
    if request.headers.get('content-type','').split(';')[0]!='image/jpeg':raise HTTPException(415,'Send image/jpeg')
    content=await request.body()
    if len(content)>4_000_000:raise HTTPException(413,'Frame exceeds 4MB')
    if not shelf or len(shelf)>64:raise HTTPException(422,'Invalid shelf identifier')
    if (reference_cm is None)!=(reference_px is None):raise HTTPException(422,'Both scale values must be provided')
    if reference_cm is not None and (reference_cm<=0 or reference_px<=0):raise HTTPException(422,'Invalid scale')
    try:result=await ingest(sid,content,shelf,reference_cm,reference_px)
    except FileNotFoundError:raise HTTPException(404,'No session')
    except ValueError as e:raise HTTPException(422,str(e))
    fresh_books=result['new_book_ids']; fresh_items=result['new_item_ids']
    if fresh_books or fresh_items:
        task=asyncio.create_task(enrich(sid,fresh_books,fresh_items))
        TASKS.setdefault(sid,[]).append(task)
    packet=result['packet']
    return {'packet':packet,'frame_ref':result['frame_ref'],'quality':result['quality'],'new_books':len(fresh_books),'new_items':len(fresh_items)}

@app.post('/api/sessions/{sid}/room')
async def room_update(sid:str,body:RoomInput):
    try:
        async with lock_for(sid):
            packet=store.load(sid)
            if packet.sweep.finished_at:raise HTTPException(409,'Session finished')
            if body.reference_frame and not store.evidence_exists(sid,body.reference_frame):raise HTTPException(422,'Missing room geometry evidence frame')
            for attr in ('length_m','width_m','height_m','shelved_wall_area_m2'):
                if getattr(body,attr) is not None:setattr(packet.room,attr,getattr(body,attr))
            if body.shape is not None:
                if body.shape not in ('rectangular','irregular','unknown'):raise HTTPException(422,'Unsupported shape')
                packet.room.shape=body.shape
            if body.scale_method:
                if body.scale_method not in ('user_reported_during_sweep','measured_reference_in_sweep','device_depth'):
                    raise HTTPException(422,'Unsupported method')
                packet.room.scale_method=body.scale_method
            else:packet.room.scale_method=packet.room.scale_method or 'user_reported_during_sweep'
            packet.room.confidence=.3 if packet.room.scale_method=='user_reported_during_sweep' else .6
            packet.room.uncertainty='User-supplied dimensions not independently verified' if packet.room.scale_method=='user_reported_during_sweep' else 'Device/reference calibration must be verified'
            if body.reference_frame:packet.room.geometry_evidence_refs.append(body.reference_frame)
            poly=[tuple(p) for p in body.polygon_points] if body.polygon_points else None
            populate_room(packet.room,poly);update_aggregates(packet);store.save(packet)
            return packet.room
    except (FileNotFoundError,ValueError):raise HTTPException(404,'No session')

@app.post('/api/sessions/{sid}/corrections')
async def corrections(sid:str,body:Correction):
    try:
        async with lock_for(sid):
            packet=store.load(sid)
            if packet.sweep.finished_at:raise HTTPException(409,'Session finished')
            books={b.id:b for b in packet.books};items={i.id:i for i in packet.items}
            target=books.get(body.ref_id) or items.get(body.ref_id)
            if body.command=='exclude_shelf':
                if not body.shelf:raise HTTPException(422,'Shelf required')
                for book in packet.books:
                    if book.shelf==body.shelf:book.excluded=True
            elif body.command=='exclude_item':
                if not target:raise HTTPException(404,'Item not found')
                target.excluded=True
            elif body.command=='first_edition':
                if body.ref_id not in books:raise HTTPException(404,'Book not found')
                books[body.ref_id].edition='First edition (user assertion; unverified)'
                books[body.ref_id].status='needs_appraisal'
                books[body.ref_id].notes.append('User claimed first edition; verification pending')
            elif body.command=='art_print':
                if body.ref_id not in items:raise HTTPException(404,'Artwork not found')
                item=items[body.ref_id];item.notes.append('User stated item is a print; still needs market evidence')
            elif body.command=='correct_title':
                if body.ref_id not in books or not body.value:raise HTTPException(422,'Book id and title required')
                book=books[body.ref_id];book.title=body.value[:200];book.id_confidence=0.5
                book.status='unidentified';book.notes.append('User-provided title; catalogue verification scheduled')
                task=asyncio.create_task(recheck_book(sid,body.ref_id,body.value[:200]))
                TASKS.setdefault(sid,[]).append(task)
            elif body.command=='missed_shelf':packet.warnings.append('User reported a missed shelf/corner; revisit during same sweep')
            else:raise HTTPException(422,'Unknown correction command')
            packet.audit_log.append({'at':now_iso(),'command':body.command,'ref_id':body.ref_id,'value':body.value,'shelf':body.shelf})
            update_aggregates(packet);store.save(packet);return packet
    except (FileNotFoundError,ValueError):raise HTTPException(404,'No session')

@app.post('/api/sessions/{sid}/finish')
async def finish(sid:str):
    try:store.load(sid)
    except (FileNotFoundError,ValueError):raise HTTPException(404,'No session')
    finish_started=time.perf_counter()
    active=[t for t in TASKS.get(sid,[]) if not t.done()]
    if active:
        _,pending=await asyncio.wait(active,timeout=240)
        for task in pending:task.cancel()
    async with lock_for(sid):
        packet=store.load(sid)
        if not packet.sweep.finished_at:
            packet.sweep.finished_at=now_iso()
            packet.sweep.duration_s=round(time.monotonic()-STARTS.get(sid,time.monotonic()),2)
        if any(not t.done() for t in TASKS.get(sid,[])):
            packet.warnings.append('Some enrichment tasks did not finish before report deadline')
        start=time.perf_counter();update_aggregates(packet)
        packet.stage_timings_ms['validation']=round((time.perf_counter()-start)*1000,2)
        start=time.perf_counter();store.save(packet)
        try:target=write_claim(packet)
        except ValueError as e:raise HTTPException(409,str(e))
        report_latency=round((time.perf_counter()-start)*1000,2)
        packet.stage_timings_ms['report_generation']=report_latency
        packet.stage_timings_ms['post_sweep_packet_generation']=round((time.perf_counter()-finish_started)*1000,2)
        store.save(packet);write_claim(packet)
        TRACKS.pop(sid,None)
        return {'packet':packet,'report':'/api/sessions/'+sid+'/report','pdf_report':'/api/sessions/'+sid+'/report/pdf','download':'/api/sessions/'+sid+'/archive'}

@app.get('/api/sessions/{sid}/packet')
async def packet_json(sid:str):
    path=store.session_dir(sid)/'claim_packet.json'
    if not path.is_file():raise HTTPException(404,'Finish the sweep first')
    return FileResponse(path,media_type='application/json',filename='claim_packet.json')

@app.get('/api/sessions/{sid}/report')
async def report_html(sid:str):
    path=store.session_dir(sid)/'claim_report.html'
    if not path.is_file():raise HTTPException(404,'Finish the sweep first')
    return FileResponse(path,media_type='text/html',filename='claim_report.html')

@app.get('/api/sessions/{sid}/report/pdf')
async def report_pdf(sid:str):
    path=store.session_dir(sid)/'claim_report.pdf'
    if not path.is_file():raise HTTPException(404,'PDF report not generated or finish sweep first')
    return FileResponse(path,media_type='application/pdf',filename='claim_report.pdf')

@app.get('/api/sessions/{sid}/evidence/{name}')
async def evidence(sid:str,name:str):
    ref='frames/'+name
    if not store.evidence_exists(sid,ref):raise HTTPException(404,'Evidence not found')
    return FileResponse(store.session_dir(sid)/ref,media_type='image/jpeg')

@app.get('/api/sessions/{sid}/archive')
async def archive(sid:str):
    target=store.session_dir(sid)
    if not (target/'claim_packet.json').is_file():raise HTTPException(404,'Finish the sweep first')
    memory=io.BytesIO()
    with zipfile.ZipFile(memory,'w',zipfile.ZIP_DEFLATED) as z:
        for path in (target/'claim_packet.json',target/'claim_report.html',target/'claim_report.pdf'):
            if path.is_file():
                z.write(path,path.name)
        for path in sorted((target/'frames').glob('*.jpg')):
            z.write(path,'frames/'+path.name)
    memory.seek(0)
    return StreamingResponse(memory,media_type='application/zip',headers={'Content-Disposition':'attachment; filename="library-claim-'+sid+'.zip"'})

@app.delete('/api/sessions/{sid}',status_code=204)
async def delete_session(sid:str):
    try:
        for t in TASKS.pop(sid,[]):t.cancel()
        async with lock_for(sid):store.remove(sid)
        TRACKS.pop(sid,None);STARTS.pop(sid,None)
    except (FileNotFoundError,ValueError):raise HTTPException(404,'No session')
    return Response(status_code=204)

@app.get('/')
async def index():return FileResponse(FRONT/'index.html')
app.mount('/static',StaticFiles(directory=str(FRONT)),name='static')
