"""Acceptance check for generated routes, assets and bilingual metadata."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
import json, re
ROOT=Path(__file__).resolve().parent
DIST=ROOT/'dist'
class Document(HTMLParser):
    def __init__(self,text):
        super().__init__();self.links=[];self.ids=[];self.h1=0;self.meta={};self.lang='';self.feed(text)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.append(attrs['id'])
        if tag=='html':self.lang=attrs.get('lang','')
        if tag=='h1':self.h1+=1
        if tag=='a' and attrs.get('href'):self.links.append(attrs['href'])
        if tag in ['script','img'] and attrs.get('src'):self.links.append(attrs['src'])
        if tag=='link' and attrs.get('rel')=='stylesheet':self.links.append(attrs['href'])
        if tag=='link' and attrs.get('rel') in ['canonical','alternate']:
            self.meta[attrs.get('hreflang',attrs['rel'])]=attrs['href']
errors=[];docs={p:Document(p.read_text()) for p in DIST.rglob('*.html')}
pages=[p for p in docs if p.relative_to(DIST).parts[0] in ['en','zh']]
for p in pages:
    doc=docs[p];lang=p.relative_to(DIST).parts[0]
    if doc.lang!=lang:errors.append(f'{p}: language mismatch')
    if doc.h1!=1:errors.append(f'{p}: expected one H1')
    if len(doc.ids)!=len(set(doc.ids)):errors.append(f'{p}: duplicate ID')
    for key in (['canonical','en','zh','x-default'] if json.loads((ROOT/'site.json').read_text()).get('origin') else []):
        if key not in doc.meta:errors.append(f'{p}: missing {key}')
    relative=p.relative_to(DIST/lang)
    if not (DIST/('zh' if lang=='en' else 'en')/relative).exists():errors.append(f'{p}: missing translation')
    for link in doc.links:
        parsed=urlsplit(link)
        if parsed.scheme or parsed.netloc:continue
        path=unquote(parsed.path)
        target=(DIST/path.lstrip('/')) if path.startswith('/') else (p.parent/path if path else p)
        if target.is_dir():target=target/'index.html'
        if not target.exists():errors.append(f'{p}: missing {link}')
        elif parsed.fragment and target in docs and parsed.fragment not in docs[target].ids:errors.append(f'{p}: missing anchor {link}')
config=json.loads((ROOT/'site.json').read_text())
for product in config['products']:
    for release in product['releases']:
        for key in ['version','platform','date','size','requirements','url','sha256']:
            if not release.get(key):errors.append(f'Missing release field: {product["id"]} {key}')
        if not re.fullmatch(r'[a-fA-F0-9]{64}',release.get('sha256','')):errors.append('Invalid release SHA256')
        if not release.get('url','').startswith('https://'):errors.append('Release requires HTTPS')
total=sum(p.stat().st_size for p in DIST.rglob('*') if p.is_file())
print(json.dumps({'localized_pages':len(pages),'local_links_and_assets':'passed' if not errors else 'failed','bilingual_metadata':'checked','static_bytes':total,'errors':errors},indent=2,ensure_ascii=False))
raise SystemExit(bool(errors))
