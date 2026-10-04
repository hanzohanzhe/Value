# Experimental AC feasibility / 实验性 AC 可行性检查

## English

`force-reference-ac-feasibility` checks whether a **declared active-power
schedule** admits a locally converged AC power-flow solution. It is not an AC
optimal-power-flow market and does not replace the DC or single-node clearing
modules.

For each bus, the implementation evaluates

\[
P_i + jQ_i = V_i\,\overline{\sum_j Y_{ij}V_j}\,S_{base}.
\]

Non-slack active injections and PQ reactive injections are fixed by the input.
PV buses fix active power and voltage magnitude. Every connected island has one
declared slack asset, whose active output supplies the network losses and any
small schedule imbalance. Generator P/Q limits, bus voltage bounds, branch MVA
limits, resistance, reactance, charging, fixed tap ratios, phase shifts and
shunts are checked explicitly.

The implementation uses polar variables with SciPy bounded nonlinear least
squares. Validation uses a separate rectangular-coordinate `scipy.root`
formulation. Agreement supports the label `LOCAL_SOLUTION_VALIDATED`; it is not
a global certificate. AC OPF, N-1 contingencies, discrete tap control, reactive
storage support and nodal pricing are `NOT_EVALUATED` or `NOT_SUPPORTED` and are
never represented by zero-valued fake results. Failure to converge or a limit
violation fails the run. There is no fallback to DC.

Required data roles are:

- base network buses, branches, asset mapping and nodal active demand;
- `force.network.ac.generators`: P/Q limits, voltage setpoints and one slack
  asset per island;
- `force.network.ac.reactive-demand`: long-form `period_id,bus_id,reactive_demand_mvar`;
- `force.network.ac.active-schedule`: long-form
  `period_id,asset_id,active_schedule_mwh`;
- optional `force.network.ac.initial-voltage` JSON.

Install with `pip install -e ".[ac]"`. This experimental module is optional and
does not enter the default open-core dependency set.

## 中文

`force-reference-ac-feasibility` 用来检查一套**事先声明的有功计划**能否得到
局部收敛的 AC 潮流解。它不是 AC-OPF 市场，也不会替代单节点或 DC 出清模块。

模型显式检查母线 P/Q 平衡、电压上下限、机组 P/Q 上下限、线路两端 MVA、网络
损耗、线路电阻/电抗/充电电纳，以及固定的变压器 tap 和相移。每个电气孤岛必须
声明一个 slack 机组，用来承担损耗和微小的计划不平衡。

生产实现采用极坐标非线性最小二乘；独立验证器采用直角坐标 `scipy.root`。
因此成功状态只能写作 `LOCAL_SOLUTION_VALIDATED`，不能声称全局最优。AC-OPF、
N-1、离散 tap 控制、储能无功支持和节点价格均明确标记为未评估或不支持；不会
用零值假装已经计算。若不收敛或违反设备约束，运行直接失败，也绝不静默退回 DC。

该模块使用独立的 `ac` 可选依赖安装，不进入 FORCE 默认安装。
