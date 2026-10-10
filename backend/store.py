import json, os, re, shutil, threading, uuid
from pathlib import Path
from backend.schemas import Packet

ROOT = Path(os.getenv('DATA_ROOT','./data/sessions')).resolve()
LOCK = threading.RLock()

def session_dir(sid:str)->Path:
    if not re.fullmatch(r'[0-9a-f]{32}',sid): raise ValueError('Invalid session ID')
    return ROOT / sid

def create(packet: Packet):
    folder=session_dir(packet.sweep.id);folder.mkdir(parents=True,exist_ok=False)
    (folder/'frames').mkdir()
    save(packet)

def save(packet:Packet):
    folder=session_dir(packet.sweep.id)
    folder.mkdir(parents=True,exist_ok=True)
    tmp=folder/'state.tmp'
    tmp.write_text(packet.model_dump_json(indent=2),encoding='utf8')
    tmp.replace(folder/'state.json')

def load(sid:str)->Packet:
    return Packet.model_validate_json((session_dir(sid)/'state.json').read_text(encoding='utf8'))

def evidence_exists(sid:str,ref:str)->bool:
    return bool(re.fullmatch(r'frames/[a-zA-Z0-9_-]+\.jpg',ref) and (session_dir(sid)/ref).is_file())

def validate_evidence(packet:Packet)->list[str]:
    refs={b.frame_ref for b in packet.books}|{i.frame_ref for i in packet.items}
    refs.update(r for b in packet.books for r in b.evidence_refs)
    refs.update(r for i in packet.items for r in i.evidence_refs)
    refs.update(packet.room.geometry_evidence_refs)
    return sorted(r for r in refs if not evidence_exists(packet.sweep.id,r))

def remove(sid:str):
    folder=session_dir(sid)
    if not folder.is_dir(): raise FileNotFoundError(sid)
    shutil.rmtree(folder)
