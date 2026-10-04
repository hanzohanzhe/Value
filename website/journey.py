"""Shared bilingual entry journey, using existing routes."""
ROLES = [
 ('reproduce','reproduce from existing data','Run VALUE 101 and compare the matching reference.','运行 VALUE 101，对照同版参考结果。'),
 ('adapt','add your new data','Copy a Study, map fields and units, then run a separate case.','复制 Study，映射字段与单位，再运行独立案例。'),
 ('modify','Edit module','Change a supported module and compare its results with the baseline.','修改支持的模块，与基线结果比较。'),
 ('extend','add new function to VALUE','Define inputs and outputs, add an extension, and run a small example.','定义输入输出，接入扩展，再运行小型示例。')]

def paths(w):
 return '<div class="path-grid">'+''.join('<a class="path-card" href="'+w.url('community')+'#'+key+'"><span class="card-index">0'+str(i+1)+'</span><h3>'+label+'</h3><p>'+w.t(en,zh)+'</p></a>' for i,(key,label,en,zh) in enumerate(ROLES))+'</div>'

def home(w):
 t=w.t
 edition=w.CONFIG.get("methodology_edition")
 metadata=''
 manifest=w.ROOT/'methodology/edition.json'
 if manifest.exists():
  import json
  info=json.loads(manifest.read_text())
  metadata='<p class="small">'+info['revision'][w.LANG]+' · '+info['basisLabel'][w.LANG]+'</p>'
 return '<section class="hero wrap"><div class="hero-copy">'+w.heading('VALUE',t('Electricity systems,<br>operating and evolving.','电力系统，<br>运行与演化。'),t('Connect half-hourly operation with annual investment decisions.','连接半小时运行与年度投资决策。'))+'<div class="actions">'+w.a('community','Get started','开始使用','button')+w.a('models/value','Explore the model','了解模型','button button-outline')+'</div></div>'+w.diagram()+'</section><section class="section wrap">'+w.section_head(t('CHOOSE YOUR TASK','选择你的任务'),t('Start with a small example.','从小型案例开始。'))+paths(w)+'</section><section class="section soft-band"><div class="wrap">'+w.cards([(t('Install','安装'),t('Full installers are pending. Check platform availability before starting.','完整安装包待发布；开始前查看平台状态。'),w.a('docs/value','Installation guide','安装指南')),(t('Data','数据'),t('Begin with CC0 teaching inputs, then bring data with its own source and terms.','从 CC0 教学输入开始，再接入有来源与许可的数据。'),w.a('data','Find the inputs','获取输入')),(t('Methodology','方法学'),t('Read the equations, algorithms and inputs for your VALUE configuration.','阅读对应 VALUE 配置的公式、算法与输入。'),w.a('methodology','Read the methods','阅读方法'))])+metadata+'</div></section>'

def pages(w):
 t=w.t;out=[]
 for path in ['community','docs/value','docs']:
  title=desc=body=''
  if path=='community':
   title=t('Get started with VALUE','开始使用 VALUE');desc=t('Choose a task, then follow the matching workflow.','选择任务，再按对应流程操作。')
   body=w.heading(t('GET STARTED','开始使用'),title,desc)+paths(w)
   instructions=[
    ['Obtain matching software and VALUE 101 inputs.','Open or copy the teaching Study and explicitly start a Run.','Compare the run with its matching reference.'],
    ['Copy a Study and its data pack.','Map field names, MW/MWh, time zones and sampling intervals.','Validate inputs and run a separate case.'],
    ['Choose a supported module and retain its baseline.','Change the configuration or implementation in a separate copy.','Run the same short case and compare results.'],
    ['Define the extension input and output contract.','Implement and register the function through the supported interface.','Run a small example before a longer study.']]
   chinese=[['获取匹配的软件与 VALUE 101 输入。','打开或复制教学 Study，显式启动 Run。','与对应参考结果比较。'],['复制 Study 与数据包。','映射字段、MW/MWh、时区与采样间隔。','校验输入并运行独立案例。'],['选择支持的模块并保留基线。','在独立副本中修改配置或实现。','运行相同短案例并比较结果。'],['定义扩展的输入输出契约。','通过支持的接口实现并登记功能。','先运行小型示例，再开展长期研究。']]
   for i,(key,label,en,zh) in enumerate(ROLES):
    body+='<section class="page-section" id="'+key+'"><h2>'+label+'</h2><ol>'+''.join('<li>'+t(a,b)+'</li>' for a,b in zip(instructions[i],chinese[i]))+'</ol></section>'
   body+='<div class="actions">'+w.a('docs/value','Install VALUE','安装 VALUE','button')+w.a('data','Choose inputs','选择输入','button button-outline')+w.a('docs','Develop VALUE','开发 VALUE','button button-outline')+'</div>'
  elif path=='docs':
   title=t('Develop VALUE','开发 VALUE');desc=t('Adapt inputs, edit modules and add functions with a small reproducible case.','用小型可复现案例接入数据、修改模块与新增功能。')
   body=w.heading('VALUE / '+t('DEVELOP','开发'),title,desc)+w.cards([(label,t(en,zh),w.a('community#'+key,'Follow this workflow','查看对应流程')) for key,label,en,zh in ROLES[1:]])+'<p>'+w.external('https://github.com/hanzohanzhe/Value/tree/source-2026-10-04',t('Source repository · source-2026-10-04','源码仓库 · source-2026-10-04'))+'</p>'+w.note(t('Software and materials','软件与材料'),t('VALUE software uses Apache-2.0. Documentation uses CC BY 4.0; teaching data uses CC0; third-party terms remain separate. Research citation is recommended.','VALUE 软件采用 Apache-2.0，文档采用 CC BY 4.0，教学数据采用 CC0；第三方条款分别适用。建议在研究成果中引用项目。'))
  elif path=='docs/value':
   title=t('Install VALUE','安装 VALUE');desc=t('Full installer downloads are pending. These steps apply once a matching package is available.','完整安装包下载待发布；匹配安装包可获得后，按以下步骤操作。')
   body=w.heading('VALUE / '+t('INSTALL','安装'),title,desc)+'<ol class="checklist">'+''.join('<li>'+t(en,zh)+'</li>' for en,zh in [('Choose your platform and the matching Full package.','选择平台与对应 Full 安装包。'),('Verify its checksum and extract the complete archive into a new directory.','核对校验和，将完整归档解压到新目录。'),('Run the platform installer, launch VALUE, and keep its terminal open.','运行对应平台安装器，启动 VALUE，并保持终端打开。'),('Open the local address printed by the launcher; start with VALUE 101.','打开启动器显示的本机地址，从 VALUE 101 开始。')])+'</ol><pre class="code-box">cd VALUE-Linux-x64\n./install-value --prefix "$HOME/VALUE-full"\n"$HOME/VALUE-full/start-value"</pre>'+w.note(t('Platform availability','平台状态'),t('Public downloads remain pending. Linux candidate offline installation and scoped user tasks passed. Windows and macOS native acceptance, signing and notarisation remain pending.','公开下载待发布。Linux 候选包断网安装与指定短任务已通过；Windows、macOS 实机验收、签名与公证仍待完成。'))+'<div class="actions">'+w.a('releases','Download status','下载状态','button')+w.a('community','Start your task','开始你的任务','button button-outline')+'</div>'
  if path=='docs/value':
   body+=w.note(t('Included environment','随包环境'),t('Full packages include Python, Node and the required dependencies. You do not need to install Python or Node separately.','Full 包包含 Python、Node 与所需依赖，无需另行安装 Python 或 Node。'))
   body+=w.table([t('Platform','平台'),t('Install','安装'),t('Launch','启动')],[['Linux','<code>./install-value --prefix "$HOME/VALUE-full"</code>','<code>"$HOME/VALUE-full/start-value"</code>'],['Windows','<code>install-value.cmd</code>',t('Run start-value.cmd in the installed directory.','在安装目录运行 start-value.cmd。')],['macOS','<code>Install VALUE.command</code>',t('Open Start VALUE.command in the installed directory.','在安装目录打开 Start VALUE.command。')]])
   body+='<div class="faq"><h2>'+t('Common questions','常见问题')+'</h2>'+''.join('<details><summary>'+t(en,zh)+'</summary><p>'+t(a,b)+'</p></details>' for en,zh,a,b in [('The local page does not open.','本机页面打不开。','Keep the launch terminal open and use the address printed by the launcher.','保持启动终端打开，使用启动器显示的地址。'),('Inputs fail validation.','输入校验失败。','Check field names, units, missing values and timestamps. Start with VALUE 101.','检查字段、单位、缺失值与时间戳，先运行 VALUE 101。'),('How do I stop the application?','如何停止应用？','Press Ctrl+C in the launch terminal. Install new versions in a separate directory.','在启动终端按 Ctrl+C；新版本安装到独立目录。')])+'</div>'
  out.append((path,title,desc,body))
 if w.CONFIG.get('publication_ready'):
  replacements={'Full installers are pending. Check platform availability before starting.':'Full candidates are available. Check platform validation before starting.','完整安装包待发布；开始前查看平台状态。':'Full 候选包可下载；开始前查看平台验收状态。','Full installer downloads are pending. These steps apply once a matching package is available.':'Download the matching Full candidate, then follow these steps.','完整安装包下载待发布；匹配安装包可获得后，按以下步骤操作。':'下载匹配的 Full 候选包，再按以下步骤操作。','Public downloads remain pending.':'Full candidates are available for download.','公开下载待发布。':'Full 候选包可下载。'}
  out=[(p,title,desc,body) for p,title,desc,body in out]
  for a,b in replacements.items():out=[(p,title.replace(a,b),desc.replace(a,b),body.replace(a,b)) for p,title,desc,body in out]
 return out
