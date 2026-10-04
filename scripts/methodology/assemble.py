from pathlib import Path
import json,re,os

S=Path(os.environ.get("VALUE_METHODOLOGY_SOURCE",Path(__file__).resolve().parent))
W=Path(os.environ.get("VALUE_METHODOLOGY_WORK",S)); W.mkdir(parents=True,exist_ok=True)
PARTS=json.loads((S/'edition.json').read_text())['chapterIDs']
EXPECTED=['introduction','datasets','core_weather','core','national_alternatives','r029_cem','transmission','optional_modules','appendix']
if PARTS != EXPECTED: raise ValueError('The VALUE methodology requires its nine declared chapters')
report={}
for lang,suffix in [('zh',''),('en','-en')]:
    chapters=[]
    for n,name in enumerate(PARTS,1):
        text=(S/lang/(name+'.md')).read_text()
        if re.search(r'\b[0-9a-fA-F]{32,64}\b',text):
            raise ValueError(f'Hash digest in {lang}/{name}')
        if re.search(r'/home/|/mnt/',text):
            raise ValueError(f'Local path in {lang}/{name}')
        lines=[]
        for line in text.splitlines():
            if line.startswith('# '):
                line='# '+str(n)+' '+re.sub(r'^\d+[. ]*','',line[2:])
            lines.append(line)
        chapters.append({'id':name,'number':n,'markdown':'\n'.join(lines).strip()+'\n'})
    (W/('chapters'+suffix+'.json')).write_text(json.dumps(chapters,ensure_ascii=False,indent=2))
    report[lang]={'chapters':len(chapters),'characters':sum(len(c['markdown']) for c in chapters),'words':sum(len(c['markdown'].split()) for c in chapters)}
report['pairs']=[]
for name in PARTS:
    pair={l:(S/l/(name+'.md')).read_text() for l in ['zh','en']}
    item={'id':name}
    for l,t in pair.items():
        item[l]={'headings':len(re.findall(r'^#{1,4} ',t,re.M)),'tables':len(re.findall(r'^\|[- :|]+\|$',t,re.M)),'fences':t.count('```'),'display_math':t.count('$$')//2}
    item['matching_structure']=item['zh']==item['en']
    report['pairs'].append(item)
(W/'assembly-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
