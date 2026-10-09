# VALUE Read me

VALUE 用于研究电力系统运行与投资演化。你可以使用已有研究，换入自己的数据，修改模块，并比较不同情景的结果。

## 选择你的任务

| 入口 | 你可以做什么 |
| --- | --- |
| **Reproduce from existing data** | 使用已有数据与模型设置，复现一项研究。 |
| **Add your new data** | 导入并校验自己的数据，保留方法，比较变化。 |
| **Edit a module** | 修改现有模块的公式、算法或规则，并测试影响。 |
| **Add a new function to VALUE** | 增加模型能力，同时补齐所需数据、模块和验证。 |

按当前任务选择即可，四条路径可以切换，无需逐级解锁。

## 第一次使用

1. 从首页选择 **Reproduce from existing data**，选择基线并为副本命名；没有基线时，先在 **Learn → VALUE 101** 创建教学研究。
2. 若使用自己的数据，选择 **Add your new data**，复制基础数据包，在 **Data** 选择数据角色，上传标准文件，或为受支持的 CSV 选择来源列和单位，审阅校验报告后提交。校验成功后返回；也可选择其他已安装的基础数据包。新 Study 沿用基线的方法与参数。
3. 核对配置并创建独立 **Study**。随后在 **Runs → Check for** 选择运行范围，点击 **Check readiness**，核对时段数，再点击 **Run selected scope**。检查和启动使用同一范围。
4. 从新 Study 的来源提示打开基线 Runs，选择两次运行进行比较；先核对范围和变化维度，再解读结果。

**Study** 保存研究配置；**Run** 保存一次运行及其结果。创建副本不会启动计算。当前引导使用基线已保存的配置；历史 Run 的精确复现还需要对应的历史输入与方法版本。

数据副本被保存的 Study 引用后，请再次复制再修改。要修改网络，在 **Data Workbench → Network overlay editor** 复制覆盖包、下载并替换角色文件、校验后安装新 ID，再到 **Studies → Model chain → Network overlay** 选择它。基础数据与网络包分别选择。

需求标准文件 demand.forecast / demand.real 使用每半小时平均功率 MW。自有数据若为 MWh/period，在 CSV 映射中明确选择该来源单位，按 30 分钟转换为 MW（60 MWh → 120 MW），核对预览后提交；运行结果按 0.5 小时得到 60 MWh。旧文件标签的兼容警告不表示新上传可以猜测单位。

## 当前支持的修改方式

**Edit a module**：在作者工作台选择槽位，查看输入输出、状态责任与源码；下载模板，在本地实现并打包。使用新的模块 ID 和 Python 包名安装，再选择基线 Study，检查兼容性并创建独立的方法对照。每次只替换一个已有槽位，原 Study 保留，保存不会运行。

版本对照显示声明和源码身份差异，契约报告与科学验证分开。模板中的通用方法需要补写；固定储能报价示例可用于接线验证。参数与有限公式调整继续在 Studies 中进行。

**Add a new function to VALUE**：

1. 在提案生成器填写问题、验证并下载演示扩展包；安装后，在独立 Study 草稿的 **Optional domains** 中启用 experimental 扩展并确认声明。
2. 打开 **Data**，选择 **Current unsaved Study draft**。在 **Data pack for this draft** 核对基础包，填写 **Independent data pack name**，点击 **Copy data pack for this draft**。副本自动用于当前草稿，已选方法与扩展保留。
3. 按扩展角色用 **Choose file** 绑定文件；CSV 映射须审阅并提交。等待 **required inputs ready** 更新，然后点击 **Return to Study Review**，解决剩余问题并保存独立 Study。保存不会运行。
4. 在 **Runs → Check for** 选择 **Two-period wiring check**，点击 **Check readiness**，核对 2 periods 后点击 **Run selected scope**。完成后在 **Inspect artifacts** 查看扩展 summary、年份和输入身份。

生成的 observer 只记录年份与输入身份，以上短 Run 验证接线。安装或结构契约通过、真实运行完成、科学验证是不同层级；新增物理算法仍需本地实现并验证。

安装完成后，继续检查兼容性、所需数据和运行条件，再启动研究。

## 查看结果与解决问题

遇到问题，先查看检查报告中标出的数据或模块。**运行完成不等于科学验证通过**；阅读结论时同时查看实际覆盖范围和验证状态。

**VRE & curtailment** 可按来源查询最终弃电归因：SQLite 支持已记录的逐时数据与分页，compact 文件只支持年度汇总。缺失维度显示不可用，不补零。比较前查看五项冻结身份核对；记录缺失时不能认定为单因素实验。

历史运行可在 **Runs** 审阅冻结输入完整性及执行身份差异，再选择 **strict** 严格核对或 **migration** 按当前方法迁移。严格核对要求相应身份记录，缺失证据会显示阻断；迁移明确保留规范数据并使用当前方法，不代表历史环境已恢复。确认后只保存独立 **Study**，保留来源 Run 和锁定范围，不自动运行或恢复旧检查点。随后选择该 Study，核对范围并完成 **Check readiness**，再明确启动新的 **Run**。

## 归档方法工作区

当前方法已变化且历史归档齐全时，在 **Runs → Run with the archived method** 查看命令。在终端进入源码根目录（安装版为安装目录的 `app`），替换绝对路径，先执行 `python3 scripts/prepare_archived_workspace.py review` 并核对报告；复制报告的 `review_sha256`，信任归档代码后执行 `prepare --review-sha256 'REVIEW_SHA256_FROM_REPORT' --acknowledge-code`，源身份变化须重新审阅。它复制历史源码、Python 和规范输入到独立工作区，保存新 Study，不启动 Run。先停止当前实例，再按生成说明启动新工作区（8766 端口互斥），完成 Check readiness 后明确运行。缺失归档会拒绝；宿主库与 locale 仍依赖原 Linux，不支持完全离线或跨平台恢复。

Learn、Data、Modules、Studies 和 Runs 继续提供相应的教学、数据、模块、研究配置和运行功能。
