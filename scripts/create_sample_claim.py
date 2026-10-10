"""Generate a clearly labeled synthetic evidence/contract sample, never real GT."""
from pathlib import Path
import shutil,cv2,numpy as np
from backend.schemas import Book,Packet,Room,Sweep,Totals,now_iso
from backend.calculations import calculate_totals,make_review
from backend.reporting import html_report, pdf_report

root=Path(__file__).resolve().parent.parent/'sample_claim';(root/'frames').mkdir(parents=True,exist_ok=True)
img=np.full((400,600,3),(36,52,68),np.uint8)
cv2.rectangle(img,(120,72),(158,338),(65,141,180),-1)
cv2.rectangle(img,(120,72),(158,338),(220,220,220),2)
cv2.putText(img,'SYNTHETIC SAMPLE - NOT REAL EVIDENCE',(20,32),cv2.FONT_HERSHEY_SIMPLEX,.59,(245,245,245),2)
cv2.putText(img,'Unidentified test spine',(190,210),cv2.FONT_HERSHEY_SIMPLEX,.6,(245,245,245),1)
cv2.imwrite(str(root/'frames'/'synthetic_frame.jpg'),img)
book=Book(id='synthetic-book-1',shelf='Synthetic Shelf',position=1,frame_ref='frames/synthetic_frame.jpg',status='unidentified',
  evidence_refs=['frames/synthetic_frame.jpg'],bbox=[120,72,158,338],
  detection_source='explicit_synthetic_schema_fixture',notes=['Synthetic artwork drawn by script; not a real detected book; do not use in model evaluation'])
room=Room(uncertainty='No metric measurement; synthetic sample')
packet=Packet(sweep=Sweep(id='synthetic-example-not-session',captured_at=now_iso(),device='SYNTHETIC FIXTURE - NOT REAL CLAIM',
  duration_s=0,country='IN',currency='INR',finished_at=now_iso()),room=room,books=[book],items=[],totals=calculate_totals([book],[],'INR'),review_queue=make_review([book],[],room),
  warnings=['SYNTHETIC SCHEMA EXAMPLE ONLY: no real camera capture, no actual prices, no measured room dimensions'])
(root/'claim_packet.json').write_text(packet.model_dump_json(indent=2),encoding='utf8')
(root/'claim_report.html').write_text(html_report(packet),encoding='utf8')
pdf_bytes = pdf_report(packet)
if pdf_bytes:
    (root/'claim_report.pdf').write_bytes(pdf_bytes)
print(f'Synthetic sample created at {root} (JSON, HTML, and PDF)')
