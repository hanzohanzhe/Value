// 已知后端错误码的中文解释（P1 W5，规格第 3 节）。错误码本身和后端消息不翻译：
// 界面先显示解释，再按原样显示“错误码: 消息”。key 与 errors.en.ts 一致。
import type { errorsEn } from "./errors.en.ts";

export const errorsZh: Record<keyof typeof errorsEn, string> = {
  // ------------------------------------------------------------ Run 生命周期
  "errors.GF_RUN_EXECUTION_IDENTITY_CHANGED": "此 Run 排队之后，已安装的模块、扩展或 VALUE 代码发生了变化，因此它没有启动。请重新提交，用当前代码运行。",
  "errors.GF_WORKER_EXITED": "模型工作进程在记录最终状态之前停止了。已完成年份的结果仍可读取；如有已核验的年度检查点，可从那里继续。",
  "errors.GF_WORKER_LOST": "模型工作进程已不在运行，Run 没有最终状态。把它标记为丢失，记为失败后即可继续。",
  "errors.GF_WORKER_MARKED_LOST": "经你确认，模型工作进程已被标记为丢失。该 Run 记为失败，可从已核验的年度检查点继续。",
  "errors.GF_WORKER_TERMINATED": "模型工作进程在 Run 结束之前被终止。",
  "errors.GF_WORKER_SPAWN_FAILED": "VALUE 无法为此 Run 启动模型工作进程。请用环境诊断检查后再启动。",
  "errors.GF_WORKER_ALIVE": "此 Run 的模型工作进程仍在运行；请等它停止后再执行此操作。",
  "errors.GF_RUN_CANCELLED_SAFE_BOUNDARY": "按你的请求，Run 已在安全边界处取消；取消前完成的年份仍可读取。",
  "errors.GF_RUN_CANCELLED_BEFORE_WORKER": "Run 在模型工作进程启动之前被取消，没有进行任何计算。",
  "errors.GF_RUN_PREPARATION_FAILED": "准备 Run（冻结输入）失败，模型没有启动。下方消息说明了原因。",
  "errors.GF_RUN_START_FAILED": "Run 无法启动。下方消息说明了原因；Study 没有改变。",
  "errors.GF_INPUT_SNAPSHOT_FAILED": "无法冻结此 Run 的输入快照，模型没有启动。",
  "errors.GF_RUN_RESERVATION_LOCK_TIMEOUT": "VALUE 正忙于对同一批记录的另一项修改；请稍后重新启动 Run。",
  "errors.GF_LOCK_TIMEOUT": "VALUE 正忙于对同一批记录的另一项修改；请稍后重试。",
  "errors.GF_RUN_START_STUDY_CHANGED": "就绪检查之后 Study 发生了变化。请重新检查就绪情况，再启动 Run。",
  "errors.GF_PREFLIGHT_REFUSED": "就绪检查发现错误，因此没有启动 Run。请修正列出的问题，再重新检查。",
  "errors.GF_RUN_SOURCE_STUDY_MISSING": "此 Run 的来源 Study 已不存在；Run 的结果仍可读取。",
  "errors.GF_RUN_SOURCE_STUDY_IN_TRASH": "此 Run 的来源 Study 在回收站中。要继续或从它创建 Run，请先恢复它。",
  "errors.GF_RUN_NOT_TERMINAL": "此 Run 仍在进行；请先取消它，再执行此操作。",
  "errors.GF_RUN_NOT_FOUND": "VALUE 没有这个 ID 的 Run；它可能已被移除。",

  // ------------------------------------------------- 验证与发布
  "errors.GF_VALIDATION_GATE_FAILED": "验证门槛（运行不变量、能量平衡或储能限值）未通过，因此不发布年度结果。",
  "errors.GF_VALIDATION_CONTRACT_OR_MECHANISM": "必需的契约或解析不变量检查未通过，因此不发布年度结果。",
  "errors.GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED": "此复现 Run 的某个原始不变量未通过，因此年度结果不在结果页发布；“检查”页和导出仍保留它们。",

  // ----------------------------------------------------- Study 与修订
  "errors.GF_STUDY_INVALID": "Study 设置被拒绝。下方消息指出了需要改正的设置。",
  "errors.GF_PROJECT_REVISION": "你打开此 Study 之后，它在别处被保存过。请重新读取后再修改。",
  "errors.GF_STUDY_TRASH_CONFIRMATION_REQUIRED": "把 Study 移入回收站需要输入它的准确名称来确认。",
  "errors.GF_SOLVER_CONTRACT_ACK_REQUIRED": "保存 Study 之前必须确认自定义的求解器契约。",

  // ------------------------------------------------- 模块与扩展
  "errors.GF_MODULE_QUARANTINED": "所选模块的文件未通过检查，已被隔离。运行之前请在“模块”页修复或移除它。",
  "errors.GF_MODULE_NOT_READY": "有所选模块尚未就绪，无法运行。“模块”页列出了每个模块还需要什么。",
  "errors.GF_MODULE_TRUST_REQUIRED": "安装模块会运行其中的 Python 代码。请确认该包来自你信任的来源。",
  "errors.GF_MODULE_IN_USE": "该模块被已保存的 Study 或 Run 使用，不能这样修改。",
  "errors.GF_MODULE_LIFECYCLE_RUNS_PENDING": "使用这些代码的 Run 尚未结束。确认后仍可修改已安装的代码；排队中的 Run 随后会在启动前停止。",
  "errors.GF_MODULE_CATALOG_STALE": "模块目录无法刷新；启动 Run 之前请重新扫描模块。",
  "errors.GF_EXTENSION_IN_USE": "该扩展被已保存的 Study 或 Run 选用，不能这样修改。",
  "errors.GF_EXTENSION_TRUST_REQUIRED": "安装扩展会运行其中的 Python 代码。请确认该包来自你信任的来源。",
  "errors.GF_PREFLIGHT_MODULE_SOURCE_CHANGED": "某个模块安装之后其源代码文件发生了变化。依赖其结果之前请先核对这一变化。",

  // ---------------------------------------------------------------- 数据
  "errors.GF_DATA_PACK_UNKNOWN": "VALUE 没有这个 ID 的数据包；它可能尚未安装。",
  "errors.GF_DATA_BUNDLE_RIGHTS_ACK": "安装数据包之前，请确认数据许可和署名要求。",
  "errors.GF_DATA_PACK_FREEZING": "此数据包正为一个正在启动的 Run 冻结；请等该 Run 启动后再试。",
  "errors.GF_UPLOAD_SIZE": "文件为空，或超过了上传上限。",
  "errors.GF_MAPPING_FX": "以欧元计价的价格列需要填写汇率、汇率口径和年份，才能预览。",

  // ------------------------------------------------------- 本地会话
  "errors.GF_SESSION_REQUIRED": "本页面不是通过 VALUE 启动器打开的。请用启动器启动 VALUE。",
  "errors.GF_SESSION_INVALID": "页面的会话与正在运行的 VALUE 不一致。请用启动器重新启动 VALUE。",
  "errors.GF_HOST_REJECTED": "VALUE 只应答发往 127.0.0.1 或 localhost 上其自身端口的请求。",
};
