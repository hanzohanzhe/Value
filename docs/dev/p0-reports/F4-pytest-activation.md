# F4-pytest-activation 施工报告

单元：用作者批准的 gate venv 激活 139 个（静态计数）pytest 风格测试。
分支：`fix/review-2026-10-04`（INTEG）。日期：2026-10-06。

## 1 结论

- 两个棘轮（unittest、pytest）现在都在 gate venv 中运行。gate venv 是以 INSTALLED 的 Python 3.10.18 为只读基础、带 `--system-site-packages` 的叠加 venv，只额外装了 `requirements/value-test-py310.lock` 中锁定的包。
- pytest 风格测试：静态 139 个函数，参数化展开后共 196 个 id。首次运行有 45 个失败，在 `git archive 35aadb3` 副本中复跑也是同样的 45 个，都是 35aadb3 已有的问题。逐个核查后，没有一个是产品缺陷，全部属于过期测试，或者依赖公开源码中没有的本地文件。修正后为 158 通过、38 跳过、0 失败。新建的 pytest 基线 `tests/baselines/known-failures-pytest-linux-py310.txt` 只有指纹，没有条目。
- 隔离区中 6 条 `owner=X0-gate-venv, expires=M7` 的 IMPORT 条目已删除。这些模块在 venv 中可以正常导入，由此暴露的 3 个 PDF 测试失败已处理（见 3.4）。
- unittest 基线在 venv 中重新记录了指纹。条目数不变，仍为 107 条（无新增，无删除）。
- `p0_gate quick` passed（137 s，16 个结果全部为 passed，`installed_inventory` 与 `network_guard` 也通过）。`p0_gate full --only pytest_ratchet` 中 pytest 步骤 passed（因为用了 `--only`，整体结果按规则是 waiver）。

## 2 提交

| 提交 | 内容 |
|---|---|
| `8f5ff8c` test(f4): bring the never-run pytest-style and pypdf tests up to the 35aadb3 contract | 修正过期测试；依赖本地专有输入的测试改为按条件跳过 |
| `d22e526` build(f4): gate venv with pinned pytest/pypdf is the canonical test environment | 锁文件、运行器与门禁改造、隔离区、两份基线、文档 |
| （本报告） | docs(p0): F4 report |

## 3 步骤与文件

### 3.1 锁文件 `requirements/value-test-py310.lock`

精确锁定以下版本：exceptiongroup 1.3.1、iniconfig 2.3.0、pluggy 1.6.0、pygments 2.21.0、pypdf 6.1.1、pytest 8.4.2、tomli 2.4.1、typing_extensions 4.16.0。packaging 25.0 已由运行时锁定，这里不重复；colorama 只在 Windows 上需要，不进 Linux venv。每一行注释记录参考 venv 中已安装 `dist-info/RECORD` 的 sha256。RECORD 本身列出了每个已安装文件的 sha256，可以用来逐文件核对。

### 3.2 `scripts/run_backend_tests.py`

- `--python` 的默认值改为 `$VALUE_GATE_VENV/bin/python`；未设置该变量时用当前解释器。
- 环境指纹改为描述测试解释器本身：如果与编排进程不是同一个解释器，就在子进程中探测。路径比较不做 resolve，因为 venv 的 python 是指向基础解释器的符号链接，resolve 之后两者无法区分。
- `installed_root()` 增加经 `sys.base_prefix` 查找 INSTALLED 的路径。不加这一条的话，在 venv 下运行时会找不到受管安装，guard 和 installed_inventory 检查会悄悄失效。
- junit id 映射改为找出最长的、实际存在的文件前缀。修正前，`tests/data_workbench/test_official_gb_candidate.py` 中 unittest 类的 id 会错映射成 `.../test_official_gb_candidate/OfficialGbCandidateTests.py::...`。
- 新增 `read_test_lock`（只接受 `==` 精确版本）和 `locked_package_mismatches`。

### 3.3 `scripts/p0_gate.py`

- `--python` 的默认值同样取 gate venv；`backend_ratchet` 和 `pytest_ratchet` 都把 `--python` 显式传给运行器。
- 新增强制步骤 `test_environment`（quick 档）：测试解释器中任一锁定包的版本不符即失败，并在报告中说明怎样设置 `VALUE_GATE_VENV`。
- `pytest_ratchet` 改为强制步骤（full 档）。pytest 不可导入时直接失败，不再跳过。
- 施工 wrapper `build/bin/vpy`（scratch 内，不在仓库里）导出 `VALUE_GATE_VENV=<scratch>/build/gate-venv`（仅在该变量未设置时生效），所以 `vpy scripts/p0_gate.py quick` 会自动使用 venv。

### 3.4 过期测试（提交 8f5ff8c）

| 测试 | 失败数 | 原因与处理 |
|---|---|---|
| `test_market_ledger_v6` | 3 | 35aadb3 的写入器已经是 `value.market-ledger/v8`，v7 只作为旧版写入器保留。v8 的 summary 账本按设计不写 full-only 的 `vre_curtailment_detail`。处理：断言改为 v8；明细复制改在 full trace 上检查；新增一个测试，验证 summary 账本保留期间级归因、不写明细行 |
| `test_run_reproduction` | 2 | 产品在调用模块验证器之前先做 `verify_frozen_input_integrity`。处理：针对验证器的测试把完整性检查替换为桩；新增一个测试，验证未就绪的快照在调用验证器之前就被阻断 |
| `test_prompt107_production_gate` | 38 | 依赖本地专有输入：`tests/fixtures/zonal_solver_failures/period-2025-14.json.gz`（release manifest 按 `.json.gz` 排除；另见 `test_source_release_tree.test_retained_real_prompt107_input_is_local_only`）和未发布的 `publication/prompt104-*.json`。处理：输入缺失时 `skip` 并写明原因，输入存在时照常运行 |
| `test_prompt107_production_gate` | 2 | 测试的可移植性问题：在 POSIX 上用 `os.rmdir` 删除目录符号链接会报 NotADirectoryError。处理：POSIX 上改用 unlink，Windows junction 仍用 rmdir。修正后两例通过，产品行为正确 |
| `test_preflight_documentation`、`test_value_methodology`（unittest，原先因导入失败被隔离） | 3 | 读取 `output/pdf/*.pdf`。这是构建产物，不在公开源码中，渲染器也不随源码发布。处理：PDF 缺失时 `skipTest` 并写明原因；`test_value_methodology` 中针对 Markdown 源文件的检查始终执行 |

### 3.5 隔离区与基线

- `tests/baselines/quarantine.txt`：删除 6 条 X0-gate-venv 条目，更新文件头说明。
- `tests/baselines/known-failures-linux-py310.txt`：在 venv 中执行 `--update-baseline`，只重写指纹（pytest 8.4.2、pypdf 6.1.1、测试锁文件的 sha256），条目不变。
- `tests/baselines/known-failures-pytest-linux-py310.txt`（新建）：只有指纹，没有条目。`append_only` 要求基线只减不增，而这个文件在 `APPEND_ONLY_BASE` 处不存在，所以写入任何条目都会违规。现在零条目，既满足这条规则，也与实际结果一致。

## 4 测试

| 运行 | 结果 |
|---|---|
| `run_backend_tests.py --pytest`（venv，修正前） | 194 个 id：149 通过、45 失败；35aadb3 副本中同样是这 45 个 |
| `run_backend_tests.py --pytest`（venv，修正后，共三次） | 196 个 id：158 通过、38 跳过、0 失败；无 forbidden port 尝试 |
| `run_backend_tests.py`（venv，全量 unittest，修正前） | 新失败 5 个（runner 1、manifest 1、PDF 3），全部已处理 |
| `run_backend_tests.py --modules test_backend_test_runner test_p0_gate test_preflight_documentation test_value_methodology` | 新增测试通过（基线指纹测试在重新记录基线后通过） |
| `p0_gate quick`（d22e526 暂存状态） | passed：backend_ratchet 2369 个 id，148 个失败，全部在基线内，new=0、fixed=0，指纹无差异 |
| `p0_gate full --only pytest_ratchet` | pytest_ratchet passed |

新增或修改的测试：`test_backend_test_runner` 新增 6 个（基线指纹来自锁定的 venv、锁文件精确版本与不符报告、指纹描述测试解释器、`VALUE_GATE_VENV` 默认值、经 venv base prefix 找到 INSTALLED、junit id 映射），并修改了隔离区过期测试；`test_p0_gate` 新增 3 个（test_environment 步骤、pytest 步骤使用门禁解释器并在缺少 pytest 时失败、门禁默认使用 venv）；`test_market_ledger_v6` 新增 1 个；`test_run_reproduction` 新增 1 个。

## 5 执行的决定

- 作者批准 pytest 与 pypdf（DECISIONS，F4 任务）。没有安装任何其他包，也没有下载任何文件。
- 处理过期测试时遵循 P0_CONVENTIONS 的棘轮规则：真回归必须修复，不进基线；golden 测试一概不动。

## 6 偏离

1. 锁文件没有 `--hash=sha256:`（wheel hash）。离线环境中没有 wheel，P0 又禁止下载。作为替代，锁文件记录每个包已安装 RECORD 的 sha256；`test_environment` 步骤只核对版本。下次经批准联网安装时，可以用 `pip hash` 补上 wheel hash。
2. 38 个 prompt107 测试和 3 个 PDF 测试采用条件 `skip`，没有写进基线。原因是 `append_only` 不允许新建的 pytest 基线带条目，也不允许 unittest 基线增加条目。另一方面，这些测试的失败原因是公开源码中本来就没有这些输入，并非测试已经过时或产品有缺陷，所以输入存在时它们仍会运行。
3. 修改了 scratch 中的施工 wrapper `build/bin/vpy`（导出 `VALUE_GATE_VENV`）。它不在仓库里，原文件备份在 `build/f4/vpy.orig`。
4. 没有运行完整的 `p0_gate full`。D4/C5 长 case 与本单元无关；e2e 使用固定端口，需要跨 lane 串行。full 档中只用 `--only` 单独验证了 `pytest_ratchet`。

## 7 未决事项

- `test_prompt116_value_101_docs.test_pdf_has_embedded_fonts_headings_pages_and_links` 同样读取 `output/pdf`，目前仍在 unittest 基线中，标注为 M0 已知失败。可以按同样方式改为条件跳过，再从基线中删除；本单元没有扩大范围去做。
- 审查报告建议把 `package.json` 的 `test:backend` 改为 pytest；本单元未改。
- `tests/baselines/milestone.txt` 仍为 `M0`，由集成者推进；本单元删除隔离区条目不受其影响。
