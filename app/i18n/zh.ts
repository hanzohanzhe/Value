// 中文界面词表（P1 规格第 3 节）。key 与 en.ts 完全一致，占位符 {name} 也一致（有测试检查）。
// 各页面的词条分文件存放（zh/*.ts、pages/*.zh.ts、messages/*.zh.ts），都照下面的术语表。
//
// 一、方法学术语：照 docs/handoff/METHODOLOGY_EDITOR_HANDOFF.md 第 2.4 节，全界面只用一种译法。
//   methodology profile                方法学口径
//   corrected methodology (default)    修正口径（默认）
//   doctoral reproduction profile      论文复现口径（不简称“doctoral 口径”，以免与 Doctoral 路径混淆）
//   compatibility profile              兼容口径
//   thesis-era setting                 论文时期的设定（不写成“错误”或“缺陷”）
//   universal / profile-gated correction  通用修正 / 口径受控修正
//   declared deviation                 已声明偏差
//   market rule set                    市场规则集
//   model clock                        模型时钟（UTC，固定 365 天模型年）
//   stress event / stress period / shortfall   stress 事件 / stress 时段 / 缺口（“stress”照写英文）
//   unserved energy (booked) / recorded blackout   缺电量（记账）/ 记录的切负荷
//   energy served                      已供电量
//   raw residual / compatibility adjustment   原始残差 / 兼容调整
//   headline (cost) / memo line        头条（成本）/ 备忘项
//   levelised CAPEX                    平准化 CAPEX
//   physical operating cost            物理运营成本
//   settlement transfer                结算转移
//   uniform marginal price             统一边际价
//   average period cost                时段平均成本
//   cycle wear / cycle depreciation    循环损耗 / 循环折旧
//   net position (per period)          （逐期）净头寸
//   down regulation                    下调
//   network-free counterfactual        无网络反事实
//   boundary marginal value            边界边际值
//   wake / availability / electrical loss   尾流 / 可用率 / 电气损耗
//   performance ratio (PR)             性能比
//   unused VRE                         未利用的 VRE（简称时也不写“未用 VRE”）
//   curtailment / congestion           弃电 / 阻塞
//   load factor / capacity factor      负荷率 / 容量因子
//   constant start-year money          起始年不变币值
//   undiscounted                       不折现
//
// 二、界面约定（W5 统一核对）：
//   * Study、Run、VALUE、PSM、CEM、VRE、SOC 等产品名和技术代号不翻译；ID、哈希、文件名、模块名、错误码不翻译。
//   * 页面名照侧栏中文标签：首页、学习、研究路径、Study、数据、模块、扩展、Run、比较、检查、市场回放、
//     VRE 与弃电、网络与再调度、网络与水系统。正文提到页面时写“在 Run 页”“打开“模块”页”，不写英文页名。
//   * readiness / Check readiness 一律写“就绪情况 / 检查就绪情况”；scope 写“范围”；trash 写“回收站”；
//     withheld（Q14 暂不发布）写“暂不发布”；Full market replay 写“完整市场回放”。
//   * 模型时间一律标 UTC，不换算成本地时间（S-中1）；数字和日期的格式跟随界面语言（format.ts）。
//   * 后端返回的英文错误消息原样显示；已知错误码在前面显示 errors.* 中的中文解释。
import type { MessageKey } from "./en.ts";
import { homeZh } from "./zh/home.ts";
import { journeyZh } from "./zh/journey.ts";
import { learnZh } from "./zh/learn.ts";
import { studiesZh } from "./zh/studies.ts";
import { dataZh } from "./pages/data.zh.ts";
import { dataWorkbenchZh } from "./pages/dataWorkbench.zh.ts";
import { modulesZh } from "./pages/modules.zh.ts";
import { resultPagesZh } from "./messages/resultPages.zh.ts";
import { networkZh } from "./messages/network.zh.ts";
import { marketZh } from "./messages/market.zh.ts";
import { runViewsZh } from "./messages/runViews.zh.ts";
import { evidenceZh } from "./messages/evidence.zh.ts";
import { workspaceZh } from "./messages/workspace.zh.ts";
import { errorsZh } from "./messages/errors.zh.ts";
import { viewModelsZh } from "./messages/viewModels.zh.ts";

export const zh: Record<MessageKey, string> = {
  // W4a 各页（P1 规格 6.1、6.2），每页一个文件：首页、Learn、研究路径、Studies。
  ...homeZh, ...learnZh, ...journeyZh, ...studiesZh,

  // ---------------------------------------------------------------- 语言
  "locale.label": "语言",
  "locale.en": "English",
  "locale.zh": "中文",

  // ---------------------------------------------------------------- 外壳
  "shell.brand.mark": "VA",
  "shell.brand.name": "VALUE",
  "shell.brand.tagline": "电力系统演化",
  "shell.contract": "契约 {version}",
  "shell.version": "VALUE {version}",

  // ---------------------------------------------------------------- 导航
  "nav.label": "工作区",
  "nav.item": "{label}：{note}",
  "nav.group.start": "开始",
  "nav.group.work": "工作",
  "nav.group.results": "结果",
  "nav.journey.label": "研究路径",
  "nav.journey.note": "复现或更换数据",
  "nav.learn.label": "学习",
  "nav.learn.note": "VALUE 101",
  "nav.overview.label": "首页",
  "nav.overview.note": "Study 状态",
  "nav.data.label": "数据",
  "nav.data.note": "输入与映射",
  "nav.models.label": "模块",
  "nav.models.note": "PSM 与 CEM",
  "nav.projects.label": "Study",
  "nav.projects.note": "情景与设置",
  "nav.run.label": "Run",
  "nav.run.note": "启动与结果",
  "nav.marketReplay.label": "市场回放",
  "nav.marketReplay.note": "报价与调度",
  "nav.curtailment.label": "VRE 与弃电",
  "nav.curtailment.note": "未利用的 VRE 电量",
  "nav.networkRedispatch.label": "网络与再调度",
  "nav.networkRedispatch.note": "阻塞与平衡",
  "nav.systems.label": "网络与水系统",
  "nav.systems.note": "可选领域结果",
  "nav.audit.label": "检查",
  "nav.audit.note": "账本与规划",
  "nav.compare.label": "比较",
  "nav.compare.note": "并排比较 Run",
  "nav.extend.label": "扩展",
  "nav.extend.note": "目录与编写",
  "nav.runSection": "此 Run 的页面",
  "nav.runResults": "年度结果",
  "nav.openMenu": "打开导航",
  "nav.closeMenu": "关闭导航",
  "shell.skipToMain": "跳到主要内容",
  "shell.sidebar": "侧栏",

  // ---------------------------------------------------------------- 服务状态
  "service.loading.title": "正在连接模型服务…",
  "service.loading.detail": "正在检查本地 API",
  "service.online.title": "Python {version}",
  "service.online.ready": "{capability} 已就绪",
  "service.online.runtimeUnavailable": "VALUE 原生运行时不可用",
  "service.degraded.title": "● 后端降级运行",
  "service.degraded.failed": "{count, plural, other {最近 # 次请求失败}}；{seconds} 秒后重试",
  "service.degraded.reduced": "以降低的能力运行：{reasons}",
  "service.degraded.seeModules": "见“模块”页",
  "service.offline.title": "● 后端离线",
  "service.offline.detail": "尝试 {attempts} 次均无应答。请从启动器启动 VALUE，然后重试",
  "service.retry": "重试",

  // ---------------------------------------------------------------- 顶栏
  "header.breadcrumb": "VALUE / {group}",
  "header.draftPack": "草稿数据包",
  "header.draftPackSelect": "所选数据包",
  "header.studyPack": "所选 Study 的数据包",
  "header.studyPackTitle": "这个已保存 Study 运行时使用的数据包。新建 Study 的草稿数据包在 Study 页选择。",
  "header.baseInputsTitle": "此数据包必需的基础输入。Study 的扩展输入在“数据”页的输入契约中计数。",
  "header.backgroundRuns": "{count, plural, other {● # 个 Run 正在后台运行}}",
  "header.readMe": "阅读说明",
  "header.studyDisclosure": "Study：{name}",
  "header.pill.notLoaded": "输入未载入",
  "header.pill.noPack": "没有数据包",
  "header.pill.ready": "基础输入就绪 {valid}/{required}",

  // ---------------------------------------------------------------- 契约版本
  "contract.mismatch.title": "界面与本地服务的版本不一致。请重启 VALUE。",
  "contract.mismatch.detail": "界面契约 {expected}；本地服务契约 {actual}。",
  "contract.mismatch.notReported": "未报告",
  "contract.mismatch.reload": "重新载入页面",

  // ---------------------------------------------------------------- 错误码解释
  "errors.GF_REQUEST_TIMEOUT": "本地服务没有在限定时间内应答，可能仍在处理。请稍后刷新查看结果，再决定是否重做。",
  "errors.GF_RESPONSE_UNREADABLE": "本地服务返回了界面无法读取的应答。",

  // ---------------------------------------------------------------- 共享组件
  "ui.loading": "加载中",
  "ui.working": "处理中",
  "ui.close": "关闭",
  "ui.cancel": "取消",
  "ui.confirm": "确认",
  "ui.copy": "复制",
  "ui.copied": "已复制",
  "ui.copyFailed": "复制失败",
  "ui.copyFullValue": "复制完整值",
  "ui.dismiss": "关闭提示",
  "ui.showDataTable": "显示数据表",
  "ui.hideDataTable": "隐藏数据表",
  "ui.chooseFile": "选择文件，或拖放到此处",
  "ui.noFileChosen": "未选择文件",
  "ui.scrollTable": "可滚动表格",
  "ui.numberRequired": "请输入数字",
  "ui.numberNotNumeric": "不是数字",
  "ui.numberBelowMin": "不能小于 {min}",
  "ui.numberAboveMax": "不能大于 {max}",
  "ui.numberStep": "必须是 {step} 的整数倍",
  "ui.steps": "步骤",

  // ------------------------------------- Data、Modules、Extensions（P1 W4b）
  ...dataZh,
  ...dataWorkbenchZh,
  ...modulesZh,
  // ------------------------------------------ 结果页（W4c，规格 6.5/6.6）
  ...resultPagesZh,
  // ------------------------------------------ 其余结果视图（W5，规格第 3 节）
  ...networkZh,
  ...marketZh,
  ...runViewsZh,
  ...evidenceZh,
  ...workspaceZh,
  // ------------------------------------------ 已知后端错误码（W5，规格第 3 节）
  ...errorsZh,
  // ------------------------------------------ 纯视图代码（W5，随当前界面语言）
  ...viewModelsZh,
};
