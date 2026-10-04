"""Reader-facing wording; metadata and scientific chapter inputs remain intact."""
import re
CHANGES={
'VALUE software use Apache-2.0':'VALUE software uses Apache-2.0',
'Rerun settlement hashes identical.':'Rerun settlement results matched.',
'rerun settlement hashes identical.':'rerun settlement results matched.',
'A rerun produced identical settlement hashes for the baseline.':'A rerun reproduced the baseline settlement results.',
'repeated settlement hashes in engineering checks':'repeated settlement results in engineering checks',
'复跑结算哈希一致':'复跑结算结果一致','基线复跑的结算哈希一致。':'基线复跑的结算结果一致。',
'Keep the source, rights and pack identity with each study.':'Keep each package’s source, rights and file name with the study.',
'随研究保留来源、权利说明与 pack 身份。':'随研究保留来源、权利说明与文件名。',
'Do not import the family into national Data.':'Install the selected nested ZIP through the Python interface.',
'整个集合不能导入 national Data。':'通过 Python 接口安装选中的嵌套 ZIP。',
'Supplementary input files; not an installable value.data-bundle/v1 ZIP.':'Supplementary input files for dataset preparation.',
'补充输入文件，不是可安装的 value.data-bundle/v1 ZIP。':'用于准备数据集的补充输入文件。',
'network-only roles are not accepted by national Data.':'network-only inputs use the zonal extension interface.',
'national Data 不接收仅网络角色。':'仅网络输入通过分区扩展接口接入。',
'Doctoral frozen replay is unsupported on the current Full; no failed doctoral Study template is provided.':'The current Full supports ordinary national input workflows. Frozen doctoral replay awaits initialization and investment-eligibility work.',
'当前 Full 不支持博士冻结精确复跑，不提供失败的博士 Study 模板。':'当前 Full 支持普通全国输入流程；博士冻结复跑待初始化与投资资格路径完善。',
'These checks cover installation and short execution, not annual or historical scientific equivalence.':'These checks cover installation and short execution. Annual and historical scientific comparisons remain to be evaluated.',
'这些检查覆盖安装与短运行，不证明全年或历史研究的科学等价。':'这些检查覆盖安装与短运行；全年及历史研究的科学对照待评估。',
'doctoral initialization/investment eligibility currently fails on Full, so frozen doctoral replay is not offered.':'frozen doctoral replay awaits working initialization and investment eligibility on Full.',
'当前 Full 的博士初始化与投资资格路径尚未通过，因此不提供博士冻结复跑。':'当前 Full 的博士冻结复跑待初始化与投资资格路径完善。',
'The 11-zone family contains runtime overlays and is not the complete 29-study annual reproduction suite.':'The 11-zone family contains 33 runtime overlays. The complete 29-study annual reproduction suite is a separate research deliverable.',
'11 区集合包含运行 overlay，不是完整的 29 项年度研究复现套件。':'11 区集合包含 33 个运行 overlay；完整的 29 项年度研究复现套件属于独立研究交付。',
'CC0 applies to the separately identified synthetic teaching packs, not every research dataset.':'CC0 covers the identified synthetic teaching packs; research datasets use their recorded source terms.',
'CC0 适用于明确标识的合成教学包，不适用于全部研究数据。':'CC0 适用于明确标识的合成教学包；研究数据使用其记录的来源条款。',
'source-2026-10-04 passed clean installation, frontend build, thirteen wheel-object checks and a short teaching run. Installer candidates retain their own earlier application identity; the source checks do not establish frozen doctoral or annual research replay.':'The clean source snapshot passed installation, frontend build and a short teaching run. The released installers use their recorded application version. Annual research and frozen doctoral replay require separate scientific validation.',
'source-2026-10-04 已通过干净安装、前端构建、十三项 wheel 对象检查与教学短运行。安装候选保留其早期应用身份；源码检查不证明博士冻结或年度研究复跑。':'干净源码快照已通过安装、前端构建与教学短运行。已发布安装包使用其记录的应用版本；年度研究与博士冻结复跑需独立科学验证。',
'Source repository · source-2026-10-04':'Source repository','源码仓库 · source-2026-10-04':'源码仓库',
'This configuration is not an AC power-flow or N−1 security study.':'This configuration uses a lossless zonal transport model.',
'此配置不是交流潮流或 N−1 安全分析。':'本配置采用分区无损输电模型。',
'The case is not an AC power-flow calculation or an N−1 security assessment.':'The case uses a lossless zonal transport model.',
'此案例不是交流潮流计算，也不是 N−1 安全评估。':'此案例采用无损分区输电模型。',
'These checks do not establish global optimality, predictive accuracy or policy validity.':'These checks establish repeatable execution under the specified conditions. Global optimality, prediction and policy interpretation require separate evidence.',
'上述检查不证明全局最优、预测精度或政策有效性。':'上述检查支持指定条件下的可重复执行；全局最优、预测与政策解释需分别补充证据。',
'Engineering repeatability is not a global optimality proof.':'Engineering repeatability applies to the tested configuration; global optimality requires separate analysis.',
'工程可重复性不等于全局最优证明。':'工程可重复性适用于已测试配置；全局最优需独立分析。',
'Applies to the tested baseline. Not a global optimality or policy-validity claim.':'Applies to repeated execution of the tested baseline; scientific and policy interpretation requires separate review.',
'适用于已测试基线，不构成全局最优或政策有效性结论。':'适用于已测试基线的重复执行；科学与政策解释需独立审阅。',
'Short-scope usability and wiring checks; not full-year scientific validation.':'Short-scope usability and interface checks; full-year scientific validation remains to be completed.',
'短范围可用性与接线检查，不是全年科学验证。':'短范围可用性与接口检查；全年科学验证待完成。',
'It does not inherit the national baseline’s completion status. No completed ten-year zonal result is asserted here.':'Longer-horizon scenario validation is planned for further research.',
'它不继承全国基线的完成状态；此处不声明分区十年结果已经完成。':'长期情景验证列入后续研究。',
'Does not inherit the national baseline’s status; fixed lossless transport representation.':'Uses a fixed lossless transport representation with its own validation record.',
'不继承全国基线的状态；采用固定无损输电表示。':'采用固定无损输电表示，验证按本配置记录。',
'一次运行完成，并不能单独证明科学有效性。':'科学解释结合完整研究假设与独立审阅。',
'A completed run alone does not establish scientific validity.':'Scientific interpretation uses the full study assumptions and independent review.',
'This page records a dated research status, not a live progress monitor.':'This page records the research status on the stated date.',
'本页记录有日期的研究状态，不是实时进度监控。':'本页记录所示日期的研究状态。',
'The case is an instructional example, not a calibrated forecast for an actual power system.':'The case teaches model inputs, operation and result interpretation with synthetic data.',
'此案例用于教学，不是对真实电力系统经过校准的预测。':'此案例使用合成数据讲解模型输入、运行与结果解释。',
'Software openness does not relicense data':'Data source terms','软件开源不会改变数据许可':'数据来源条款',
'An Apache-2.0 software licence does not grant permission to redistribute third-party data. Obtain restricted datasets from their authorised source.':'Third-party data uses its own redistribution terms. Obtain restricted datasets from their authorised source.',
'Apache-2.0 软件许可不会赋予第三方数据的再分发权。受限数据应从其授权来源获取。':'第三方数据使用其自身再分发条款；受限数据从授权来源获取。',
'The SCHEME-C PhD reproduction repository is an earlier research archive, not the source or download location of the current VALUE application.':'The SCHEME-C PhD reproduction repository preserves earlier research.',
'SCHEME-C 博士复现仓库属于较早的研究档案，不是当前 VALUE 应用的源码或下载地址。':'SCHEME-C 博士复现仓库保存较早的研究档案。',
'Research citation is recommended and is not an additional condition for using the software.':'Research citation is recommended; software use follows Apache-2.0.',
'建议在研究成果中引用项目，学术引用不是软件使用的附加条件。':'建议在研究成果中引用项目；软件使用遵循 Apache-2.0。',
'What it does not establish':'Scope and next steps','不能据此推断':'适用范围与后续工作'}
def pages(w,original):
 out=[]
 for path,title,desc,body in original:
  if path=='cite':
   title=w.t('Cite VALUE','引用 VALUE');desc=w.t('Record the version, study configuration and data sources used.','记录所用版本、研究配置与数据来源。')
   body=w.heading('VALUE / '+w.t('CITATION','引用'),title,desc)+'<p>'+w.t('Research citation is recommended. Use the citation file for the software snapshot and cite datasets using their own authors and source terms.','建议在研究成果中引用项目。使用软件快照对应的引用文件，并按数据集作者与来源条款分别引用数据。')+'</p>'+w.table([w.t('Material','材料'),w.t('File','文件')],[['VALUE','<a download href="/assets/value-source-review-CITATION.cff">CITATION.cff</a>'],[w.t('Full release candidate','Full 发布候选'),'<a download href="/assets/release-candidate/CITATION.cff">CITATION.cff</a> · <a download href="/assets/release-candidate/CITATION.bib">CITATION.bib</a>']])+'<p>'+w.a('data','Find data sources and terms','查看数据来源与条款')+'</p>'
  if not path.startswith("methodology"):
   for a,b in CHANGES.items():body=body.replace(a,b);title=title.replace(a,b);desc=desc.replace(a,b)
  # A shared plain-language status applies to the software-facing routes.
  if path in ['', 'releases','release-check','docs/value']:
   body+=w.note(w.t('Current candidate','当前候选版'),w.t('The improved frontend is under review. Installation packages will be updated when that review is complete.','改进前端正在审查，完成后更新安装包。'))
  out.append((path,title,desc,body))
 return out
