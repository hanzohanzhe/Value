"""Release pages gated on confirmed public assets, with factual platform limits."""
def pages(w,existing):
 existing=data_pages(w,existing)
 if not w.CONFIG.get('publication_ready'):return existing
 t=w.t;rows=[]
 names={"linux-x64":t("Linux 64-bit","Linux 64位"),"windows-x64":t("Windows 64-bit","Windows 64位"),"macos-arm64":t("macOS Apple Silicon","macOS Apple 芯片"),"macos-x64":t("macOS Intel","macOS Intel") }
 def platform(r):return names.get(r["platform"],r["platform"])
 for r in w.CONFIG['products'][0]['releases']:
  rows.append([platform(r),'<a download href="'+r['url']+'">'+r['filename']+'</a><br>'+r['size'],t('Linux offline installation and scoped tasks passed.','Linux 断网安装与指定短任务已通过。') if r['native_acceptance'] else t('Experimental candidate; native acceptance, signing and notarisation are planned for later releases.','实验候选；实机验收、签名与公证列入后续发布工作。'),r['filename']])
 cards=[]
 for r in w.CONFIG['products'][0]['releases']:
  status=t('Linux offline installation and scoped tasks passed.','Linux 断网安装与指定短任务已通过。') if r['native_acceptance'] else t('Experimental candidate; native acceptance, signing and notarisation are planned for later releases.','实验候选；实机验收、签名与公证列入后续发布工作。')
  cards.append('<article class="release-card"><p class="eyebrow">'+platform(r)+'</p><h2>Full · '+r['version']+'</h2><p>'+status+'</p><p>'+r['size']+'</p><a class="button" download href="'+r['url']+'">'+t('Download candidate','下载候选包')+'</a><p class="release-filename">'+r['filename']+'</p></article>')
 body=w.heading('VALUE 0.6.0-alpha.2 / Full 2026-10-03-rc1',t('Download the Full candidate','下载 Full 候选包'),t('Choose your platform and follow its installation guide.','选择平台，再按安装指南操作。'))+'<div class="release-grid">'+''.join(cards)+'</div>'+w.note(t('Included environment','随包环境'),t('Full includes Python, Node, dependencies and teaching data. Follow the installation steps for your platform.','Full 包含 Python、Node、依赖与教学数据。按对应平台的步骤安装。'))+'<p>'+w.a('docs/value','Installation steps','安装步骤')+'</p>'
 existing=ready_copy(existing)
 return [(path,t('Download VALUE','下载 VALUE'),t('Versioned installation candidates.','有版本的安装候选包。'),body) if path in ['releases','release-check'] else (path,title,desc,text) for path,title,desc,text in existing]

def data_pages(w,existing):
 t=w.t;ready=w.CONFIG.get('publication_ready');rows=[]
 for x in w.CONFIG.get('data_assets',[]):
  link='<a download href="'+x['url']+'">'+x['filename']+'</a>' if ready else x['filename']+'<br>'+t('Publication pending','等待公开发布')
  rows.append([x['title'][w.LANG],x['interface'][w.LANG],link+'<br>'+f'{x["bytes"]/1048576:.2f} MiB'])
 body=w.heading('VALUE / DATA',t('Choose data for your workflow','按工作流程选择数据'),t('Different packages use different installation interfaces. Keep the source, rights and pack identity with each study.','各类数据包使用不同安装接口；随研究保留来源、权利说明与 pack 身份。'))+w.table([t('Material','材料'),t('Installation route','安装方式'),t('File','文件')],rows)
 body+=w.note(t('Choose a starting point','选择起点'),t('Start with the bundled VALUE 101 teaching data. Choose GBP1 for national studies, or the 23-zone research suite for combined national and network studies.','新手从随包 VALUE 101 教学数据开始；全国研究选 GBP1，同时研究全国与网络时选 23 区研究套件。'))
 body+=w.note(t('Research scope','研究范围'),t('R029 supports ordinary national input workflows; frozen doctoral replay remains to be verified. The 11-zone collection provides 33 runtime overlays. Annual research validation is a separate study task.','R029 适用于普通全国输入流程；博士冻结复跑仍待验证。11 区集合提供 33 个运行 overlay；年度研究验证作为独立研究任务开展。'))
 body+=w.note(t('Data rights','数据条款'),t('Read RIGHTS.json and ATTRIBUTION.md inside each research archive. Third-party data retains its source-specific terms. CC0 applies to the separately identified synthetic teaching packs, not every research dataset.','阅读各研究归档内的 RIGHTS.json 与 ATTRIBUTION.md。第三方数据保留来源条款；CC0 适用于明确标识的合成教学包，不适用于全部研究数据。'))

 return [(path,t('Data and installation routes','数据与安装方式'),t('Six research archives with distinct interfaces and rights.','六份研究归档，各有安装接口与条款。'),body) if path=='data' else (path,title,desc,text) for path,title,desc,text in existing]

def ready_copy(pages):
 changes={'complete installer downloads remain pending.':'Full installer candidates are available from the matching software release.','完整安装包下载仍待发布。':'Full 安装候选包可从对应软件版本下载。','Public download packaging is pending.':'Downloadable software and teaching materials are provided by the matching release.','公开下载包仍待发布。':'可下载的软件与教学材料由匹配版本提供。','VALUE software use Apache-2.0':'VALUE software uses Apache-2.0','not a published tag or DOI':'a release-candidate tag, without a DOI','不代表已发布 tag 或 DOI':'标识已发布候选 tag，未分配 DOI','Unpublished local candidate':'Published release candidate','Unpublished local distribution candidate':'Published release candidate'}
 for a,b in changes.items():pages=[(p,title.replace(a,b),desc.replace(a,b),body.replace(a,b)) for p,title,desc,body in pages]
 return pages
