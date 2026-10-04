"""Release pages gated on confirmed public assets, with factual platform limits."""
def pages(w,existing):
 existing=data_pages(w,existing)
 if not w.CONFIG.get('publication_ready'):return existing
 t=w.t;rows=[]
 for r in w.CONFIG['products'][0]['releases']:
  rows.append([r['platform'],'<a download href="'+r['url']+'">'+r['filename']+'</a><br>'+r['size'],t('Linux offline installation and scoped tasks passed.','Linux 断网安装与指定短任务已通过。') if r['native_acceptance'] else t('Experimental candidate; native installation, signing and notarisation are unverified.','实验候选；实机安装、签名与公证未验收。'),'<code>'+r['sha256']+'</code>'])
 cards=[]
 for r in w.CONFIG['products'][0]['releases']:
  status=t('Linux offline installation and scoped tasks passed.','Linux 断网安装与指定短任务已通过。') if r['native_acceptance'] else t('Experimental candidate; native installation, signing and notarisation are unverified.','实验候选；实机安装、签名与公证未验收。')
  cards.append('<article class="release-card"><p class="eyebrow">'+r['platform']+'</p><h2>Full · '+r['version']+'</h2><p>'+status+'</p><p>'+r['size']+'</p><a class="button" download href="'+r['url']+'">'+t('Download candidate','下载候选包')+'</a><p class="release-filename">'+r['filename']+'</p><p class="small">SHA256</p><code class="release-checksum">'+r['sha256']+'</code></article>')
 body=w.heading('VALUE / 2026-10-03-rc1',t('Download the Full candidate','下载 Full 候选包'),t('Choose your platform, verify the checksum, then follow its installation guide.','选择平台，核对校验和，再按安装指南操作。'))+'<div class="release-grid">'+''.join(cards)+'</div>'+w.note(t('Included environment','随包环境'),t('Full includes Python, Node and dependencies. These installer candidates have their own source identity; the documentation source tag is a separate snapshot.','Full 包包含 Python、Node 与依赖。安装候选包具有独立源码身份；文档源码 tag 是另一份快照。'))+'<p>'+w.a('docs/value','Installation steps','安装步骤')+'</p>'
 existing=ready_copy(existing)
 return [(path,t('Download VALUE','下载 VALUE'),t('Versioned installation candidates.','有版本的安装候选包。'),body) if path in ['releases','release-check'] else (path,title,desc,text) for path,title,desc,text in existing]

def data_pages(w,existing):
 t=w.t;ready=w.CONFIG.get('publication_ready');rows=[]
 for x in w.CONFIG.get('data_assets',[]):
  link='<a download href="'+x['url']+'">'+x['filename']+'</a>' if ready else x['filename']+'<br>'+t('Publication pending','等待公开发布')
  rows.append([x['title'][w.LANG],x['interface'][w.LANG],link+'<br>'+f'{x["bytes"]/1048576:.2f} MiB','<code>'+x['sha256']+'</code>'])
 body=w.heading('VALUE / DATA',t('Choose data for your workflow','按工作流程选择数据'),t('Different packages use different installation interfaces. Keep the source, rights and pack identity with each study.','各类数据包使用不同安装接口；随研究保留来源、权利说明与 pack 身份。'))+w.table([t('Material','材料'),t('Installation route','安装方式'),t('File','文件'),'SHA256'],rows)
 body+=w.note(t('Execution scope','执行范围'),t('The final GBP1 pack preserves its original runtime ID and initializes five nuclear stations totalling 5,958 MW. A two-period run passed execution and contract checks. The suite passed its UI/API import checks. These checks cover installation and short execution, not annual or historical scientific equivalence.','最终 GBP1 包保留原运行时 ID，初始化五座核电站、合计 5,958 MW；两时段运行通过执行与契约检查，套件通过 UI/API 导入检查。这些检查覆盖安装与短运行，不证明全年或历史研究的科学等价。'))
 body+=w.note(t('Research boundaries','研究范围'),t('R029 provides inputs compatible with the ordinary VALUE chain; doctoral initialization/investment eligibility currently fails on Full, so frozen doctoral replay is not offered. The 11-zone family contains runtime overlays and is not the complete 29-study annual reproduction suite.','R029 提供与普通 VALUE 流程兼容的输入；当前 Full 的博士初始化与投资资格路径尚未通过，因此不提供博士冻结复跑。11 区集合包含运行 overlay，不是完整的 29 项年度研究复现套件。'))
 body+=w.note(t('Data rights','数据条款'),t('Read RIGHTS.json and ATTRIBUTION.md inside each research archive. Third-party data retains its source-specific terms. CC0 applies to the separately identified synthetic teaching packs, not every research dataset.','阅读各研究归档内的 RIGHTS.json 与 ATTRIBUTION.md。第三方数据保留来源条款；CC0 适用于明确标识的合成教学包，不适用于全部研究数据。'))
 source_note=w.note(t('Clean source snapshot','干净源码快照'),t('source-2026-10-04 passed clean installation, frontend build, thirteen wheel-object checks and a short teaching run. Installer candidates retain their own earlier application identity; the source checks do not establish frozen doctoral or annual research replay.','source-2026-10-04 已通过干净安装、前端构建、十三项 wheel 对象检查与教学短运行。安装候选保留其早期应用身份；源码检查不证明博士冻结或年度研究复跑。'))
 existing=[(p,title,desc,text+source_note if p in ['about','docs'] else text) for p,title,desc,text in existing]
 return [(path,t('Data and installation routes','数据与安装方式'),t('Six research archives with distinct interfaces and rights.','六份研究归档，各有安装接口与条款。'),body) if path=='data' else (path,title,desc,text) for path,title,desc,text in existing]

def ready_copy(pages):
 changes={'complete installer downloads remain pending.':'Full installer candidates are available from the matching software release.','完整安装包下载仍待发布。':'Full 安装候选包可从对应软件版本下载。','Public download packaging is pending.':'Downloadable software and teaching materials are provided by the matching release.','公开下载包仍待发布。':'可下载的软件与教学材料由匹配版本提供。','VALUE software use Apache-2.0':'VALUE software uses Apache-2.0','not a published tag or DOI':'a release-candidate tag, without a DOI','不代表已发布 tag 或 DOI':'标识已发布候选 tag，未分配 DOI','Unpublished local candidate':'Published release candidate','Unpublished local distribution candidate':'Published release candidate'}
 for a,b in changes.items():pages=[(p,title.replace(a,b),desc.replace(a,b),body.replace(a,b)) for p,title,desc,body in pages]
 return pages
