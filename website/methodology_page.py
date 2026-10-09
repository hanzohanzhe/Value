from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parent
def pages(w):
    t=w.t
    lang=w.LANG
    chapters=json.loads((ROOT/'methodology'/('chapters-en.json' if lang=='en' else 'chapters.json')).read_text())
    toc=''.join('<a href="#'+c['id']+'">'+re.search(r'<h2>(.*?)</h2>',c['html'])[1]+'</a>' for c in chapters)
    downloads=''
    status=json.loads((ROOT/'methodology-sync.json').read_text())
    imported=(ROOT/'methodology/edition.json').exists() and (ROOT/'methodology/artifacts.json').exists()
    if imported and status.get('downloads_enabled'):
        raw=json.loads((ROOT/'methodology/artifacts.json').read_text())
        files=raw if isinstance(raw,list) else raw.get('filesmanifest',raw.get('files',[]))
        labels={'pdf':'PDF','docx':t('Word','Word'),'html':t('Offline HTML','离线 HTML')}
        downloads='<div class="actions methodology-downloads">'+''.join('<a class="button button-outline" download href="/assets/methodology/'+x['path']+'">'+labels[x['format']]+'</a>' for x in files if x['language']==lang)+'</div>'
    body=w.heading(t('METHODS / EDITION 0.2','方法学 / 修订版 0.2'),t('VALUE model methodology','VALUE 模型方法学'),t('Mathematical formulation, algorithms and input data for system operation, annual investment, transmission.','电力系统运行、年度投资、传输约束的数学设定、计算方法和输入数据。'))
    if not downloads: body+=w.note(t('VALUE web methodology','VALUE 网页方法学'),t('The retained chapters describe VALUE system modelling. PDF, Word and offline HTML downloads are temporarily withdrawn until a matching VALUE-only edition is reviewed.','保留章节说明 VALUE 电力系统模型；PDF、Word 与离线 HTML 暂停提供，待一致的 VALUE 专用版本完成审阅。'))
    if imported:
        edition=json.loads((ROOT/'methodology/edition.json').read_text())
        body=body.replace('EDITION 0.2','EDITION '+str(edition['edition'])).replace('修订版 0.2','修订版 '+str(edition['edition']))
    other='zh' if lang=='en' else 'en'
    body+='<div class="methodology-intro"><nav class="methodology-language" aria-label="'+t('Methodology language','方法学语言')+'"><span>'+t('English edition','中文版本')+'</span><a data-language-link href="/'+other+'/methodology/" lang="'+other+'">'+t('阅读中文版','Read in English')+'</a></nav><p class="small">'+(edition['revision'][lang]+' · '+edition['basisLabel'][lang] if imported else t('Revised 3 October 2026 · Implementation and data basis 2 October 2026','修订于 2026年10月3日 · 模型实现与数据依据 2026年10月2日'))+'</p>'+downloads+'</div>'
    body+='<p class="small">'+t('Edition 0.4 describes the reviewed VALUE 0.7.0-alpha.1 implementation. The downloadable Full 2026-10-03-rc1 contains VALUE 0.6.0-alpha.2; the revised installer awaits publication.','0.4 版方法学描述经修订的 VALUE 0.7.0-alpha.1 实现。当前可下载的 Full 2026-10-03-rc1 内含 VALUE 0.6.0-alpha.2；修订实现的安装包待发布。')+'</p>'
    body+='<details class="methodology-toc" open><summary>'+t('Chapters · full English methodology','章节目录 · 完整中文方法学')+'</summary><nav aria-label="'+t('Methodology chapters','方法学章节')+'">'+toc+'</nav></details>'
    body+='<article class="methodology-body" lang="'+lang+'">'
    for c in chapters:
        math_dir='math-en' if lang=='en' else 'math'
        text=c['html'].replace('src="'+math_dir+'/','src="/assets/methodology/'+math_dir+'/')
        text=re.sub(r'<table>([\s\S]*?)</table>',r'<div class="methodology-table" tabindex="0" role="region" aria-label="'+t('Methodology data table','方法学数据表')+r'"><table>\1</table></div>',text)
        body+='<section id="'+c['id']+'">'+text+'<a class="back-to-contents" href="#methodology-top">'+t('Back to contents ↑','返回目录 ↑')+'</a></section>'
    body+='</article>'
    return [('methodology',t('Methodology','模型方法学'),t('Mathematical formulation, algorithms and input data for VALUE.','VALUE 的数学设定、计算方法和输入数据。'),'<div id="methodology-top">'+body+'</div>')]
