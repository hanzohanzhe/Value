#!/usr/bin/env python3
"""Dependency-free, bilingual static website. Run: python3 build.py."""
from pathlib import Path
from html import escape
import json, os, shutil
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parent
DIST = ROOT / 'dist'
CONFIG = json.loads((ROOT / 'site.json').read_text())
ORIGIN = CONFIG.get('origin', '').rstrip('/')
LANG = 'en'

def t(en, zh): return zh if LANG == 'zh' else en
def url(path=''):
    parsed = urlsplit(path)
    return f'/{LANG}/' + (parsed.path.strip('/') + '/' if parsed.path else '') + ('?'+parsed.query if parsed.query else '') + ('#'+parsed.fragment if parsed.fragment else '')
def a(path, en, zh, cls='text-link'): return f'<a class="{cls}" href="{url(path)}">{t(en,zh)}</a>'
def external(link, label): return f'<a href="{escape(link)}" rel="noopener noreferrer" target="_blank">{label}<span class="sr-only">{t(" (opens in a new tab)","（在新标签页打开）")}</span></a>'
def tag(en, zh): return f'<span class="tag">{t(en,zh)}</span>'
def heading(kicker, title, lead=''): return f'<header class="page-heading"><p class="eyebrow">{kicker}</p><h1>{title}</h1>'+ (f'<p class="lead">{lead}</p>' if lead else '')+'</header>'
def section_head(kicker, title, link=''): return f'<div class="section-heading"><div><p class="eyebrow">{kicker}</p><h2>{title}</h2></div>{link}</div>'
def note(title, body): return f'<aside class="note"><strong>{title}</strong><p>{body}</p></aside>'
def cards(items, cls='three-grid'): return '<div class="'+cls+'">'+''.join(f'<article class="info-card"><span class="card-index">{i+1:02}</span><h3>{h}</h3><p>{b}</p>{link}</article>' for i,(h,b,link) in enumerate(items))+'</div>'
def table(headers, rows): return '<div class="table-scroll" tabindex="0" role="region" aria-label="'+t('Comparison table','对照表')+'"><table><thead><tr>'+''.join('<th scope="col">'+h+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(('<th scope="row">'+c+'</th>') if i==0 else '<td>'+c+'</td>' for i,c in enumerate(row))+'</tr>' for row in rows)+'</tbody></table></div>'

def diagram(single=False):
    return f'''<figure class="system-figure"><div class="figure-top"><span>VALUE / SYSTEM LOGIC</span><span>{t('Concept diagram','机制示意')}</span></div>
    <svg viewBox="0 0 540 360" role="img" aria-labelledby="diagram-title"><title id="diagram-title">{t('Generation, storage and demand interact through a network. Operation informs annual investment.','发电、储能和需求通过网络交互；运行结果反馈年度投资。')}</title>
    <defs><pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#344359"/></pattern></defs><rect width="540" height="360" fill="url(#grid)"/>
    <g fill="none" stroke="#9ccdc7" stroke-width="2"><path d="M124 110H245V170M416 110H295V170M270 230V275H125V152M270 275H416V152"/><path d="M60 315H485V55H340" stroke="#eeab71" stroke-dasharray="5 5"/></g>
    <g fill="#1c2b42" stroke="#506075"><rect x="40" y="82" width="168" height="70" rx="8"/><rect x="332" y="82" width="168" height="70" rx="8"/><rect x="186" y="169" width="168" height="70" rx="8"/><rect x="40" y="249" width="168" height="50" rx="8"/><rect x="332" y="249" width="168" height="50" rx="8"/></g>
    <g fill="#f5f4ef" text-anchor="middle" font-family="Arial, sans-serif" font-size="17"><text x="124" y="115">{t('Generation','发电')}</text><text x="416" y="115">{t('Demand','需求')}</text><text x="270" y="201">{t('Network','网络')}</text><text x="124" y="281">{t('Storage','储能')}</text><text x="416" y="281">{t('Settlement','结算')}</text></g>
    <g fill="#a9b9cb" text-anchor="middle" font-family="Arial, sans-serif" font-size="13"><text x="124" y="136">{t('WIND · SOLAR · THERMAL','风电 · 光伏 · 常规机组')}</text><text x="416" y="136">{t('LOAD · FLEXIBILITY','负荷 · 灵活性')}</text><text x="270" y="222">{t('DISPATCH & FLOWS','调度与电力流')}</text></g><text x="270" y="48" fill="#eeab71" text-anchor="middle" font-size="15">{t('Annual investment feedback','年度投资反馈')}</text><circle cx="245" cy="110" r="4" fill="#9ccdc7"/><circle cx="295" cy="110" r="4" fill="#9ccdc7"/>
    </svg><figcaption><span><i class="legend mint"></i>{t('Half-hourly operation','半小时运行')}</span><span><i class="legend peach"></i>{t('Annual evolution','年度演化')}</span></figcaption></figure>'''

def product_cards():
    return '<article class="product-card"><h2>VALUE</h2><p>'+t('Power-system operation and investment evolution.','电力系统运行与投资演化。')+'</p>'+a('models/value','Explore VALUE','了解 VALUE','button')+'</article>'

def home():
    import journey
    return journey.home(__import__(__name__))

def nav(path):
    other='zh' if LANG=='en' else 'en'
    links=[('', 'Home','首页'),('community','Get started','开始使用'),('docs/value','Install','安装'),('data','Data','数据'),('methodology','Methodology','方法学'),('docs','Develop','开发')]
    menu=''.join('<a href="'+url(p)+'"'+(' aria-current="page"' if path==p else '')+'>'+t(en,zh)+'</a>' for p,en,zh in links)
    return '<a class="skip-link" href="#main">'+t('Skip to content','跳至正文')+'</a><header class="site-header"><div class="wrap nav-inner"><a class="brand" href="'+url()+'"><span class="brand-mark">VA</span><span>VALUE</span></a><button class="menu-toggle" aria-controls="main-nav" aria-expanded="false">'+t('Menu','菜单')+'</button><nav id="main-nav" aria-label="'+t('Main navigation','主导航')+'">'+menu+'</nav><div class="nav-actions"><a class="language" href="/'+other+'/'+(path+'/' if path else '')+'" lang="'+other+'">'+t('中文','EN')+'</a></div></div></header>'

def footer():
    return '<footer class="site-footer"><div class="wrap footer-grid"><div><h2>VALUE</h2><p>'+t('Electricity system operation and evolution.','电力系统运行与演化。')+'</p></div><div>'+a('community','Get started','开始使用','')+a('docs/value','Install','安装','')+a('data','Data','数据','')+'</div><div>'+a('methodology','Methodology','方法学','')+a('docs','Develop','开发','')+a('studies','Studies','案例','')+'</div><div>'+a('about','About and licences','关于与许可','')+a('cite','Research citation','研究引用','')+a('validation','Validation','验证','')+'</div></div></footer>'

def page(path,title,desc,body,full=False):
    directory=DIST/LANG/path; directory.mkdir(parents=True,exist_ok=True)
    route=path+'/' if path else ''
    absolute=f'{ORIGIN}/{LANG}/{route}'
    icon='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#2455d6"/><path d="M13 18l10 29h7l10-29h-7l-6 21-7-21zm29 14-5 15h7l2-7h7l2 7h7L52 18h-8l-3 9h7l2 7h-6z" fill="white"/></svg>'
    head=f'''<!doctype html><html lang="{LANG}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(title)} | VALUE</title><meta name="description" content="{escape(desc)}"><meta name="theme-color" content="#10182b"><link rel="icon" type="image/svg+xml" href="data:image/svg+xml,{quote(icon)}"><link rel="stylesheet" href="/assets/site.css"><script defer src="/assets/site.js"></script>'''
    if ORIGIN:
        head+=f'<link rel="canonical" href="{absolute}"><link rel="alternate" hreflang="en" href="{ORIGIN}/en/{route}"><link rel="alternate" hreflang="zh" href="{ORIGIN}/zh/{route}"><link rel="alternate" hreflang="x-default" href="{ORIGIN}/en/{route}"><meta property="og:url" content="{absolute}">'
    head+=f'<meta property="og:title" content="{escape(title)} | VALUE"><meta property="og:description" content="{escape(desc)}"><meta property="og:type" content="website"></head><body>'
    (directory/'index.html').write_text(head+nav(path)+f'<main id="main"'+('' if full else ' class="wrap page-main"')+'>'+body+'</main>'+footer()+'</body></html>')

def build():
    global LANG
    if DIST.exists(): shutil.rmtree(DIST)
    shutil.copytree(ROOT / "static", DIST)
    import journey, publication, presentation
    routes=[]
    for LANG in ['en','zh']:
        homebody=presentation.pages(__import__(__name__), [('', '', '', home())])[0][3]
        page('',t('Electricity System Modelling','电力系统建模'),t('VALUE for power-system operation and investment evolution.','VALUE 电力系统运行与投资演化。'),homebody,True)
        routes.append(f'/{LANG}/')
        import content
        import methodology_page
        import release_candidate
        for path,title,desc,body in presentation.pages(__import__(__name__), publication.pages(__import__(__name__), content.pages(__import__(__name__)) + journey.pages(__import__(__name__)) + methodology_page.pages(__import__(__name__)) + release_candidate.pages(__import__(__name__)))):
            page(path,title,desc,body)
            routes.append(f'/{LANG}/{path}/')
    (DIST/'index.html').write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>VALUE | Electricity System Modelling</title><meta http-equiv="refresh" content="0;url=/en/"></head><body><a href="/en/">VALUE · English</a> <a href="/zh/">中文</a></body></html>')
    (DIST/'404.html').write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Find a page | VALUE</title><link rel="stylesheet" href="/assets/site.css"></head><body><main class="wrap page-main"><p class="eyebrow">VALUE / 404</p><h1>Find a page.<br>查找页面。</h1><p>This address may have changed.</p><a class="button" href="/en/">English home</a> <a class="button button-outline" href="/zh/">中文首页</a></main></body></html>')
    if ORIGIN:
        (DIST/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+ORIGIN+p+'</loc></url>' for p in routes)+'</urlset>')
    (DIST/'robots.txt').write_text('User-agent: *\nAllow: /\n'+('Sitemap: '+ORIGIN+'/sitemap.xml\n' if ORIGIN else ''))
    (DIST/'assets'/'releases.json').write_text(json.dumps(CONFIG['products'],indent=2,ensure_ascii=False)+'\n')
    print(f'Generated {len(routes)} localized routes in {DIST}')

if __name__ == '__main__': build()
