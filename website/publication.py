"""Release pages gated on confirmed public assets, with factual platform limits."""
def pages(w,existing):
 if not w.CONFIG.get('publication_ready'):return existing
 t=w.t;rows=[]
 for r in w.CONFIG['products'][0]['releases']:
  rows.append([r['platform'],'<a download href="'+r['url']+'">'+r['filename']+'</a><br>'+r['size'],t('Linux offline installation and scoped tasks passed.','Linux 断网安装与指定短任务已通过。') if r['native_acceptance'] else t('Experimental candidate; native installation, signing and notarisation are unverified.','实验候选；实机安装、签名与公证未验收。'),'<code>'+r['sha256']+'</code>'])
 body=w.heading('VALUE / 2026-10-03-rc1',t('Download the Full candidate','下载 Full 候选包'),t('Choose your platform, verify the checksum, then follow its installation guide.','选择平台，核对校验和，再按安装指南操作。'))+w.table([t('Platform','平台'),t('Package','安装包'),t('Validation','验收'),'SHA256'],rows)+w.note(t('Included environment','随包环境'),t('Full includes Python, Node and dependencies. These installer candidates have their own source identity; the documentation source tag is a separate snapshot.','Full 包包含 Python、Node 与依赖。安装候选包具有独立源码身份；文档源码 tag 是另一份快照。'))+'<p>'+w.a('docs/value','Installation steps','安装步骤')+'</p>'
 return [(path,t('Download VALUE','下载 VALUE'),t('Versioned installation candidates.','有版本的安装候选包。'),body) if path in ['releases','release-check'] else (path,title,desc,text) for path,title,desc,text in existing]
