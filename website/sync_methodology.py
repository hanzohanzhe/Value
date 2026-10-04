#!/usr/bin/env python3
"""Import one reviewed VALUE-only edition; no document generation or deployment."""
from pathlib import Path
import argparse, hashlib, json, re, shutil, tempfile
ROOT=Path(__file__).resolve().parent
PRIVATE=re.compile(r'VALUE[-_ ]single|value_single|Electrace|\bSDX\b',re.I)
def read(path): return json.loads(path.read_text())
def sync(source,build,documents):
    edition=read(source/'edition.json'); raw=read(source/'artifacts.json')
    files=raw if isinstance(raw,list) else raw.get('filesmanifest',raw.get('files',[]))
    for key in ['edition','date','basis','chapterIDs','revision','basisLabel']:
        if key not in edition: raise ValueError('Missing edition field: '+key)
    ids=edition['chapterIDs']
    if len(ids)!=9 or len(set(ids))!=9: raise ValueError('Exactly nine distinct chapter IDs required')
    if len(files)!=6 or {(x['language'],x['format']) for x in files}!={(lang,fmt) for lang in ['zh','en'] for fmt in ['pdf','docx','html']}:
        raise ValueError('Six bilingual PDF/DOCX/HTML artifacts required')
    for x in files:
        if Path(x['path']).name!=x['path']: raise ValueError('Artifact paths must be basenames')
        data=(documents/x['path']).read_bytes()
        if len(data)!=x['bytes'] or hashlib.sha256(data).hexdigest()!=x['sha256']: raise ValueError('Artifact hash/size mismatch: '+x['path'])
        if x['format']=='html' and PRIVATE.search(data.decode()): raise ValueError('Private material found in HTML artifact')
    payloads={}; refs={}
    for lang,suffix in [('zh',''),('en','-en')]:
        payload=read(build/('rendered'+suffix+'.json')); chapters=payload['chapters']
        if [x['id'] for x in chapters]!=ids: raise ValueError('Chapter order mismatch: '+lang)
        if [int(x['number']) for x in chapters]!=list(range(1,10)): raise ValueError('Chapter numbering must be 1–9')
        if PRIVATE.search(json.dumps(chapters,ensure_ascii=False)): raise ValueError('Private material in chapters')
        directory='math'+suffix; text='\n'.join(x['html'] for x in chapters)
        refs[lang]=set(re.findall(r'(?:'+directory+r'/)(eq-[0-9]+\.svg)',text)); payloads[lang]=chapters
        for name in refs[lang]:
            data=(build/directory/name).read_text()
            if PRIVATE.search(data): raise ValueError('Private material in equation asset')
    with tempfile.TemporaryDirectory(prefix='.methodology-import-',dir=ROOT) as temp:
        temp=Path(temp);chapterdir=temp/'chapters';assets=temp/'assets';chapterdir.mkdir();assets.mkdir()
        for lang,suffix in [('zh',''),('en','-en')]:
            (chapterdir/('chapters'+suffix+'.json')).write_text(json.dumps(payloads[lang],ensure_ascii=False,indent=2)+'\n')
            d=assets/('math'+suffix);d.mkdir()
            for name in refs[lang]: shutil.copy2(build/('math'+suffix)/name,d/name)
        for x in files: shutil.copy2(documents/x['path'],assets/x['path'])
        for filename in ['edition.json','artifacts.json']: shutil.copy2(source/filename,chapterdir/filename)
        # All inputs validate before replacing complete input sets; no merge with older editions.
        for target,prepared in [(ROOT/'methodology',chapterdir),(ROOT/'static/assets/methodology',assets)]:
            if target.exists(): shutil.rmtree(target)
            shutil.move(str(prepared),target)
    config=read(ROOT/'site.json');config.update(methodology_edition=edition['edition'],methodology_revision_date=edition['date'],evidence_date=edition['basis']);(ROOT/'site.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    status=read(ROOT/'methodology-sync.json');status.update(edition=edition['edition'],revision_date=edition['date'],basis_date=edition['basis'],state='reviewed-artifacts-imported',downloads_enabled=True);(ROOT/'methodology-sync.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
    print('Imported reviewed edition',edition['edition'],'with nine bilingual chapters and six verified artifacts')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=ROOT.parent/'docs/methodology');parser.add_argument('--build',type=Path,required=True);parser.add_argument('--documents',type=Path,required=True);args=parser.parse_args();sync(args.source.resolve(),args.build.resolve(),args.documents.resolve())
