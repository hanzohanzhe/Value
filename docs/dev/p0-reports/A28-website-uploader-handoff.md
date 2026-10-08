# A28 工作报告：网站上传员交接文档按最终状态重写

- 分支：`fix/review-2026-10-04`（INTEG），依据的代码状态 HEAD `6560189`（之后只有文档提交）。
- 授权：DECISIONS A25（交付文档按最终状态从头重写）、A26（网站方法学描述网上发布的新模型，论文复现口径是兼容口径）、A28（缺陷修好后一次性重写四份文件）。
- 性质：只改文档，不改代码、参数表、golden 或 `website/`。

## 1 完成的步骤

1. 从头重写 `docs/handoff/WEBSITE_UPLOADER_HANDOFF.md`，只写当前状态，没有逐轮历史、已修复问题的叙述或被推翻的做法。
2. 复制到 worktree 根目录 `VALUE_handoff_website_uploader_2026-10-04.md`（被 `.git/info/exclude` 排除，不入库），`cmp` 逐字节相同。
3. 与上一版相比，按当前代码更新的内容：
   - 通用修正加入 `r5.served-energy-net-of-stress-shortfall`（已供电量扣除 stress 缺口）与 `r53.bounded-storage-state-record`（只改完整回放的记录）；
   - 2.6 节重写未供电量：年度卡片 `Unserved demand` 含 stress 缺口并旁注 PSM 记录部分，比较页分两行；VoLL 只给 PSM 记录的切负荷计价；新增未利用 VRE 的显示和跨口径不求差的规则、回放导出的 stress 列、论文口径 Run 进行中的 `Pending`；
   - 2.2 节区分完整标签与界面短名（Study composer 单选框、`Research guide` 第 2 步、Runs `What will run` 用 `Corrected (default)` / `Doctoral reproduction`）；
   - 2.9 节：逐时需求的映射、VALUE 101 需求按 MW 读取、`GF_DATA_DEMAND_SCALE`；同 ID 两份清单、实验性模块计数、完整回放的估算警告；扩展只记录 `after_psm` 产物、停用后重新启用的规则、草稿自动命名、`GF_STUDY_ID_EXISTS`；四角色报告现状（0 高、2 中、6 低）；
   - 第 7 节新增第 10 条（扩展原地改源后能否重新启用，待作者决定），第 7 条补充尚未写进公开文档的行为；
   - 附录 A.3、A.4 相应更新，A.4 新增第 9 问（未供电量与成本）。

## 2 核对依据（只读）

- `git diff 35aadb3 -- website/` 为空，`website/` 的行号抽查与上一版一致；用项目 Python 3.10（`vpy`）`ast.parse` 网站脚本，只有 `content.py` 第 26 行 `SyntaxError`，证实构建需要 3.12+。
- `profiles.json` 与生成的 `METHODOLOGY_PROFILES.md`（13/39 项已应用修正，剩余声明偏差门控为 none）；`gridform_core/methodology.py` 的 `UNIVERSAL_ACCOUNTING_CORRECTIONS`；`P0_GOLDEN_DELTA.md`（15 个用例，D1、D2 轨迹 0 列变化）；`tests/golden/doctoral/D5.json` 各修订说明。
- 界面字符串逐条在 `app/`、`backend/`、`gridform_core/`、`packaging/` 中 grep 核对（约 60 条），包括 R5 新增的 `Unused VRE (PSM boundary)`、`Annual results pending the raw-invariant check`、模块计数徽章、比较页参照句和新指标名。
- 数据映射规则读 `backend/data_mapping.py`（逐时需求、FX、年电量检查）与 `gridform_core/data_pack_validation.py`（需求至少 17,520 期）。
- `CHANGELOG.md`、`docs/VALIDATION_AND_CLAIMS.md`、`docs/USER_GUIDE*.md` 中与当前代码不一致或缺失的条目逐项核对后列入第 7 节第 7 条。
- 实测结果取自 `docs/dev/p0-reports/R5-verify.md`、`r41-golden/D5-gbp1-summary-before-after.json` 与刚提交的 `docs/handoff/FOUR_ROLE_TEST_REPORT.md`（0 高、2 中、6 低）。

## 3 测试与门禁

- `scripts/refresh_source_release_manifest.py --check`：`"stale": false`（`docs/handoff/`、`docs/dev/` 在发布排除清单中，清单不变）。
- 本单元不改代码，未运行模型测试。

## 4 偏差与待办

- 没有重跑模型；GBP1 勘误数字沿用两份已有运行摘要的计算，网站引用前须先写进公开文档（文档第 7 节第 3 条）。
- 没有修改 `CHANGELOG.md`、`docs/VALIDATION_AND_CLAIMS.md`、用户指南，只列为阶段 1 的前提。

## 5 安全核对

- 没有启动服务，没有连接 8766/8800，没有向任何进程发信号；Python 全部经 `vpy` 调用。INSTALLED 的核对结果见最终回报。
