"""Metrics on independent CSV truth rows. No synthetic or missing cases silently removed.
CSV columns documented in docs/evaluation.md. Output JSON, never fabricated scores.
"""
import argparse,csv,json,math
from pathlib import Path
TARGETS={'book_count_error':.05,'title_correct_rate':.70,'confident_wrong_rate':.03,'spine_within_15_pct':.85,'book_price_within_25_pct':.75,'nonbook_recall':.80,'floor_error':.10,'wall_error':.15,'packet_seconds':300}

def read_csv(path):
    with open(path,encoding='utf8',newline='') as f:return list(csv.DictReader(f))

def norm(s):return ' '.join((s or '').casefold().split())

def bool_value(s):return norm(s) in ('yes','y','true','1')

def relative_error(actual,pred):
    try:
        actual=float(actual);pred=float(pred)
        return abs(actual-pred)/abs(actual) if actual>0 else None
    except (ValueError,TypeError):return None

def evaluate(truth,room=None):
    metrics={}; rows=truth
    book_rows=[r for r in rows if norm(r.get('kind','book'))!='nonbook']
    actual=len(book_rows);found=sum(bool_value(r.get('detected')) for r in book_rows)
    # A complete evaluation also requires ALL predicted book instances, including false positives.
    # If this total is absent, report count accuracy as unevaluated rather than undercounting over-detection.
    predicted_total=room.get('predicted_book_count') if room else None
    count_err=abs(int(predicted_total)-actual)/actual if predicted_total is not None and actual else None
    metrics['book_count_error']={'numerator':abs(int(predicted_total)-actual) if count_err is not None else None,'denominator':actual,'value':count_err}
    legible=[r for r in book_rows if bool_value(r.get('legible'))]
    correct=sum(bool_value(r.get('title_correct')) for r in legible)
    metrics['title_correct_rate']={'numerator':correct,'denominator':len(legible),'value':correct/len(legible) if legible else None}
    confident=[r for r in legible if r.get('pred_title') and float(r.get('confidence') or 0)>=.8]
    wrong=sum(not bool_value(r.get('title_correct')) for r in confident)
    metrics['confident_wrong_rate']={'numerator':wrong,'denominator':len(confident),'value':wrong/len(confident) if confident else None}
    # Missing values remain in denominator for the client-facing eligible subset.
    spine=[r for r in book_rows if r.get('true_height_cm') and r.get('true_thickness_cm')]
    ok=sum((a is not None and b is not None and a<=.15 and b<=.15) for r in spine
           for a,b in [(relative_error(r['true_height_cm'],r.get('pred_height_cm')),relative_error(r['true_thickness_cm'],r.get('pred_thickness_cm')))])
    metrics['spine_within_15_pct']={'numerator':ok,'denominator':len(spine),'value':ok/len(spine) if spine else None}
    price=[r for r in book_rows if r.get('verified_price')]
    good=sum(err is not None and err<=.25 for r in price for err in [relative_error(r['verified_price'],r.get('pred_price'))])
    metrics['book_price_within_25_pct']={'numerator':good,'denominator':len(price),'value':good/len(price) if price else None}
    others=[r for r in rows if norm(r.get('kind'))=='nonbook']
    right=sum(bool_value(r.get('detected')) and norm(r.get('true_category'))==norm(r.get('pred_category')) for r in others)
    metrics['nonbook_recall']={'numerator':right,'denominator':len(others),'value':right/len(others) if others else None}
    if room:
        for typ in ('floor','wall'):
            actual=room.get('true_'+typ+'_m2');pred=room.get('pred_'+typ+'_m2')
            err=relative_error(actual,pred)
            metrics[typ+'_error']={'numerator':None,'denominator':1 if actual else 0,'value':err}
        duration=room.get('packet_seconds');
        metrics['packet_seconds']={'numerator':None,'denominator':1 if duration else 0,'value':float(duration) if duration else None}
    for k,v in metrics.items():
        val=v['value'];target=TARGETS.get(k)
        if val is None or target is None:v['status']='NOT EVALUATED'
        else:v['status']='PASS' if (val<=target if k.endswith('_error') or k in ('confident_wrong_rate','packet_seconds') else val>=target) else 'FAIL'
    return {'metrics':metrics,'dataset_book_rows':len(book_rows),
            'client_samples_sufficient':{'books_60':actual>=60,'spines_20':len(spine)>=20,'prices_15':len(price)>=15,'items_8':len(others)>=8}}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--truth',required=True);ap.add_argument('--room-json');ap.add_argument('--out',required=True);args=ap.parse_args()
    output=evaluate(read_csv(args.truth),json.load(open(args.room_json)) if args.room_json else None)
    Path(args.out).write_text(json.dumps(output,indent=2),encoding='utf8')
    print(json.dumps(output,indent=2))
