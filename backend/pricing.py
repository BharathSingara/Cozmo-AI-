"""Only live, traceable physical-product listings. No unsupported ebook substitutions."""
import os, math
from datetime import datetime,timezone
import httpx
from backend.schemas import Price, PriceRange

COUNTRY_CURRENCY={'US':'USD','GB':'GBP','IN':'INR','CA':'CAD','AU':'AUD','DE':'EUR','FR':'EUR'}
MARKETPLACE={'US':'EBAY_US','GB':'EBAY_GB','CA':'EBAY_CA','AU':'EBAY_AU','DE':'EBAY_DE','FR':'EBAY_FR'}

def validate_market(country,currency):
    c=country.upper(); cur=currency.upper()
    if c not in COUNTRY_CURRENCY or COUNTRY_CURRENCY[c]!=cur:raise ValueError('Unsupported country/currency pairing')
    return c,cur

def convert(amount:float,source_currency:str,target_currency:str,rate:float|None,rate_source:str|None=None):
    if amount<0:raise ValueError('Negative price')
    if source_currency==target_currency:return round(amount,2),False
    if not rate or rate<=0 or not rate_source:raise ValueError('Documented FX rate is required')
    return round(amount*rate,2),True

def choose_listing(summaries,requested_currency,condition):
    """Exclude ambiguous titles/digital products, retain exact source URL and currency."""
    candidates=[]
    for listing in summaries:
        p=listing.get('price') or {}
        try: amt=float(p['value']);currency=p['currency']
        except (KeyError,TypeError,ValueError):continue
        label=str(listing.get('title','')).lower()
        if amt<=0 or currency!=requested_currency or any(s in label for s in ('ebook','e-book','kindle','audiobook','summary of','study guide for')):continue
        cond=str(listing.get('condition','')).upper().replace(' ','_')
        if condition=='new' and cond not in ('NEW','BRAND_NEW'):continue
        if condition=='used' and cond not in ('USED','LIKE_NEW','VERY_GOOD','GOOD','ACCEPTABLE','PRE_OWNED'):continue
        url=listing.get('itemWebUrl')
        if not url or not url.startswith('https://'):continue
        candidates.append((amt,listing))
    if not candidates:return None
    return min(candidates,key=lambda x:x[0])

async def search_listings(query:str,country:str,limit:int=20):
    if os.getenv('ALLOW_EXTERNAL_LOOKUPS','true').lower()!='true':return [],'External price lookup disabled'
    # Prefer Google Shopping through a configured, regional SerpApi account.
    # The returned retailer link and source remain attached to every quoted price.
    if os.getenv('SERPAPI_KEY'):
        try:
            async with httpx.AsyncClient(timeout=float(os.getenv('PRICE_TIMEOUT_SECONDS','6'))) as client:
                resp=await client.get('https://serpapi.com/search.json',params={
                    'engine':'google_shopping','q':query[:110],'gl':country.lower(),
                    'hl':'en','api_key':os.environ['SERPAPI_KEY']})
                resp.raise_for_status();payload=resp.json()
            if payload.get('error'):return [],'Shopping service error: '+str(payload['error'])[:100]
            offers=[]
            for row in payload.get('shopping_results',[]):
                amount=row.get('extracted_price');link=row.get('product_link')
                if not isinstance(amount,(float,int)) or amount<=0 or not link or not link.startswith('https://'):continue
                display=str(row.get('price',''))
                symbols={'USD':'$','GBP':'£','INR':'₹','CAD':'$','AUD':'$','EUR':'€'}
                expected=COUNTRY_CURRENCY[country]
                sym=symbols.get(expected,'')
                has_curr=(sym and sym in display) or (expected in display) or (expected=='INR' and ('rs' in display.lower() or '₹' in display))
                if not has_curr and display:continue
                used=bool(row.get('second_hand_condition'))
                offers.append({'title':row.get('title',''),'price':{'value':str(amount),'currency':expected},
                  'condition':'USED' if used else 'NEW','itemWebUrl':link,
                  '_source':str(row.get('source') or 'Google Shopping merchant')+' (Google Shopping via SerpApi)'})
            return offers[:limit],None
        except (httpx.HTTPError,ValueError,KeyError) as exc:
            return [],f'Shopping service error: {type(exc).__name__}'
    token=os.getenv('EBAY_BROWSE_TOKEN')
    if country not in MARKETPLACE:return [],f'No configured physical-listing provider for {country}; supply SERPAPI_KEY'
    if not token:return [],'SERPAPI_KEY or EBAY_BROWSE_TOKEN required for live physical listings' 
    headers={'Authorization':f'Bearer {token}','X-EBAY-C-MARKETPLACE-ID':MARKETPLACE[country]}
    try:
        async with httpx.AsyncClient(timeout=float(os.getenv('PRICE_TIMEOUT_SECONDS','6'))) as client:
            resp=await client.get('https://api.ebay.com/buy/browse/v1/item_summary/search',params={'q':query[:110],'limit':limit},headers=headers)
            resp.raise_for_status()
            return resp.json().get('itemSummaries',[]),None
    except (httpx.HTTPError,ValueError) as exc:
        return [],f'Price service error: {type(exc).__name__}'

async def book_prices(title:str,author:str|None,isbn:str|None,country:str,currency:str):
    # Match listings to physical books and work names. Require title in listing to reduce wrong-item prices.
    query=isbn or ' '.join(x for x in [title,author] if x)
    listings,error=await search_listings(query,country)
    safe=[]
    from backend.catalog import similarity
    for listing in listings:
        label=listing.get('title','')
        if isbn and isbn in label: safe.append(listing);continue
        if similarity(title,label)>.55 or title.lower() in label.lower():safe.append(listing)
    results=[]
    for condition in ('new','used'):
        selected=choose_listing(safe,currency,condition)
        if selected:
            amt,entry=selected
            results.append(Price(amount=round(amt,2),currency=currency,source=entry.get('_source','eBay Browse listing'),url=entry['itemWebUrl'],
             retrieved_at=datetime.now(timezone.utc).isoformat(),condition_assumed='New or equivalent' if condition=='new' else 'Used listing; condition per seller',
             match_confidence=.7 if isbn else .55))
        else:results.append(Price(unavailable_reason=error or f'No verifiable {condition} physical-book listing matches'))
    return results[0],results[1]

async def item_price_range(description:str,brand_model:str|None,country:str,currency:str):
    if not brand_model:return PriceRange(unavailable_reason='Brand or model not verified; broad catalogue prices not comparable')
    listings,error=await search_listings(f'{brand_model} {description}',country)
    from backend.catalog import similarity
    suitable=[]
    for item in listings:
        if similarity(brand_model,item.get('title',''))>.42 or brand_model.lower() in item.get('title','').lower():
            found=choose_listing([item],currency,'new')
            if found:suitable.append(found[0])
    if not suitable:return PriceRange(unavailable_reason=error or 'No comparable brand/model physical listing')
    low,high=min(suitable),max(suitable)
    representative=next(i for i in listings if i.get('itemWebUrl') and brand_model.lower() in i.get('title','').lower()) if any(i.get('itemWebUrl') and brand_model.lower() in i.get('title','').lower() for i in listings) else None
    if representative is None:return PriceRange(unavailable_reason='Comparable URL could not be verified')
    return PriceRange(low=round(low,2),high=round(high,2),currency=currency,source=representative.get('_source','eBay Browse comparable listing'),url=representative['itemWebUrl'],retrieved_at=datetime.now(timezone.utc).isoformat())
