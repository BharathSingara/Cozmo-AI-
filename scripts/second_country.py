"""Live second-country price comparison of the SAME ten verified editions.
Usage: ALLOW_EXTERNAL_LOOKUPS=true SERPAPI_KEY=... python -m scripts.second_country \
 --input data/books_to_price.csv --country-a IN --country-b US --out data/second_country_live.csv
"""
import argparse,asyncio,csv
from pathlib import Path
from backend.pricing import COUNTRY_CURRENCY,book_prices,validate_market

async def run(input_path:str,country_a:str,country_b:str,output_path:str):
    if country_a==country_b:raise ValueError('Markets must differ')
    validate_market(country_a,COUNTRY_CURRENCY[country_a]);validate_market(country_b,COUNTRY_CURRENCY[country_b])
    with open(input_path,newline='',encoding='utf8') as f:rows=list(csv.DictReader(f))
    if len(rows)!=10 or any(not r.get('title') or not r.get('verified_edition') for r in rows):
        raise ValueError('Provide exactly 10 evidence-verified books and edition identifiers')
    out=[]
    for book in rows:
        result={'title':book['title'],'verified_edition':book['verified_edition'],'author':book.get('author',''),
                'isbn':book.get('isbn',''),'country_a':country_a,'country_b':country_b}
        for code,label in [(country_a,'a'),(country_b,'b')]:
            new,used=await book_prices(book['title'],book.get('author'),book.get('isbn'),code,COUNTRY_CURRENCY[code])
            for typ,price in [('replacement',new),('used',used)]:
                result.update({f'{label}_{typ}_amount':price.amount,f'{label}_{typ}_currency':price.currency,
                               f'{label}_{typ}_source':price.source,f'{label}_{typ}_url':price.url,
                               f'{label}_{typ}_retrieved_at':price.retrieved_at,
                               f'{label}_{typ}_unavailable_reason':price.unavailable_reason})
        out.append(result)
    with open(output_path,'w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=list(out[0]));writer.writeheader();writer.writerows(out)
    print(f'Price comparisons written: {len(out)} books, {country_a} versus {country_b}; unavailable prices remain blank.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--out',required=True)
    parser.add_argument('--country-a',default='IN');parser.add_argument('--country-b',default='US')
    args=parser.parse_args();asyncio.run(run(args.input,args.country_a,args.country_b,args.out))
