"""Open Library verifies WORK candidates; edition/ISBN requires stronger evidence."""
import os, re
from difflib import SequenceMatcher
import httpx

def similarity(a,b):
    def norm(s):return re.sub(r'[^a-z0-9 ]','',str(s or '').lower()).strip()
    na, nb = norm(a), norm(b)
    if not na or not nb: return 0.0
    if na == nb: return 1.0
    na_base = norm(str(a or '').split(':')[0].split(' - ')[0])
    nb_base = norm(str(b or '').split(':')[0].split(' - ')[0])
    base_ratio = SequenceMatcher(None,na_base,nb_base).ratio() if (na_base and nb_base) else 0.0
    full_ratio = SequenceMatcher(None,na,nb).ratio()
    return max(full_ratio, base_ratio)

async def identify_book(text:str, title_hint:str|None=None, author_hint:str|None=None):
    if not os.getenv('ALLOW_EXTERNAL_LOOKUPS','true').lower()=='true':return None,'External book catalogue lookup disabled'
    raw_query=(title_hint or text or '').strip()
    words=[w for w in re.findall(r'[a-zA-Z0-9]+', raw_query) if len(w)>=2]
    query=' '.join(words)
    if len(query)<4:return None,'Insufficient legible title for catalog verification'
    try:
        docs=[]
        async with httpx.AsyncClient(timeout=6) as client:
            response=await client.get('https://openlibrary.org/search.json',params={'title':query[:90],'limit':5,'fields':'key,title,author_name,edition_key,isbn,publisher'})
            if response.status_code==200:
                docs=response.json().get('docs',[])
            if not docs:
                gb_resp=await client.get('https://www.googleapis.com/books/v1/volumes',params={'q':query[:80],'maxResults':5})
                if gb_resp.status_code==200:
                    for it in gb_resp.json().get('items',[]):
                        info=it.get('volumeInfo',{})
                        docs.append({'title':info.get('title',''),'author_name':info.get('authors',[]),'key':'/books/'+it.get('id','')})
        matches=[]
        for d in docs:
            score=similarity(d.get('title',''),raw_query)
            if author_hint and d.get('author_name'):score=.75*score+.25*similarity(d['author_name'][0],author_hint)
            if score>=.70:matches.append((score,d))
        if not matches:return None,'No reliable matching work in catalogue'
        score,best=max(matches,key=lambda x:x[0])
        if len(matches)>1 and sorted([m[0] for m in matches],reverse=True)[0]-sorted([m[0] for m in matches],reverse=True)[1]<.025:
            return None,'Ambiguous catalogue matches'
        return {'title':best['title'],'author':(best.get('author_name') or [None])[0],
                'work_url':'https://openlibrary.org'+best.get('key','') if best.get('key','').startswith('/works') else 'https://books.google.com/books?id='+best.get('key','').replace('/books/',''), 'score':round(score,3)},None
    except (httpx.HTTPError,ValueError,KeyError,IndexError) as exc:
        return None,f'Book identification lookup failed: {type(exc).__name__}'
