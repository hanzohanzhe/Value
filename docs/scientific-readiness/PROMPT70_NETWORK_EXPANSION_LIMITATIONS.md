# Transmission expansion lifecycle / 输电扩容生命周期

## English

`reference-transmission-expansion` is a transparent lifecycle reference, not a
recommended GB transmission-planning model. A Study must select the DC network
PSM, the base network contract extension, the network-expansion extension and a
candidate-corridor data role.

The annual order is:

1. complete, fail, delay or retire previously planned network projects;
2. inject commissioned network assets into that year's canonical topology;
3. run the actual selected DC PSM;
4. observe declared corridor congestion and apply the candidate's declared
   benefit/cost screen under one shared system and budget-group envelope;
5. apply the seeded physical planning outcome (circuits are never multiplied by
   a probability);
6. carry active projects into next year's namespaced extension state.

Each commissioned branch inherits stable endpoints, impedance, circuits, MW/MVA
rating, owner/planner, CAPEX, FOM, discount rate, construction/economic life,
carbon factor provenance and project/candidate lineage. A branch enters clearing
once and only after commissioning. Imports remain boundary resources and are not
converted into internal branches.

The resource-cost ledger includes commissioned network annualised CAPEX and FOM.
Policy transfers, congestion rent and residual value are not counted again as
resource cost. Construction embodied carbon is included only when the candidate
provides a factor and source; otherwise the carbon total is `NOT_EVALUATED`.

This reference method uses one-year observed congestion and declared annual
benefit. It has no endogenous multi-year demand forecast, security-constrained
planning, N-1 valuation, strategic ownership or causal claim that a line caused
an observed reliability change. A ten-year endogenous transmission pathway has
not been validated.

## 中文

`reference-transmission-expansion` 是用于验证公共契约和年度生命周期的透明参考
方法，并不是推荐的英国国家输电规划模型。

项目会先完成/延期/失败/退役既有规划线路，再把已经投运的线路注入当年真实 DC
PSM 拓扑；当年出清后才根据候选走廊中预先声明的拥塞触发值、收益/成本筛选、共享
系统预算和分组预算提出新项目。规划成功采用带种子的物理成败，不会把线路回路数
乘以概率。新线路只能在规划完成后进入下一年的实际出清，而且只进入一次。

投运资产完整继承端点、电抗/电阻、MW/MVA、回路数、所有者、规划者、CAPEX、
FOM、折现率、建设期、经济寿命、隐含碳来源以及 candidate→proposal→project→asset
谱系。进口电仍是边界资源，绝不会被误建模成内部输电线。

统一成本账本只计入投运网络资产的年化 CAPEX 与 FOM；政策转移、拥塞租和残值不
重复计入。只有候选数据提供了可追溯的隐含碳因子时才核算建设排放，否则总碳账本
明确标为未评估。目前尚未验证十年内生输电路径。
