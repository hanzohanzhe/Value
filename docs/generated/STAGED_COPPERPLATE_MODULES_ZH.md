# 分阶段铜板市场模块

FORCE 现在提供一条可替换的“两阶段全国市场”运行路径。这是可选模型，原始
Scheme C 复现路径没有被修改。

在同一个 Study 中同时选择：

```json
{
  "psm": "force-staged-bid-at-cost-psm",
  "balancing": "force-copperplate-balancing",
  "storage_cost": "dynamic-annual-storage-cost"
}
```

PSM 先冻结只包含预测信息的 `AheadMarketInput`，按照 bid-at-cost 完成全国
日前出清并记录哈希。之后，balancing 模块才能取得真实需求、本期可用容量、
带符号的调节报价和期初 SOC。平衡结果同时链接日前结果哈希及自身输入哈希；
同一份平衡输入不能执行两次。

## 物理与结算规则

- 全国日前市场按统一出清价结算；
- 本期平衡按 pay-as-bid 结算；
- 日前成交仍按全国价格结算，平衡调整现金流单独记账；
- 储能 SOC 和年度实际售电量只使用最终调度量，不使用被取消的日前计划；
- interconnector 正值是进口包络，负值是出口包络，本期不能越过零点反向；
- 未供电量按照 Study 中的 VOLL 计价；
- 最终物理资源成本根据最终调度计算，不与市场支付混为一个账本。

权威逐期记录是 `market/staged-market.jsonl`。每一期依次写入
`AheadMarketInput`、`AheadMarketResult`、`BalancingInput` 和
`BalancingResult`。年度哈希索引位于
`market/staged-market-year-<year>.json`。

## 兼容边界

Scheme C 来源的需求和 interconnector CSV 每行实际是 MW，而 typed PSM
契约要求 MWh/period。唯一的 canonical adapter 执行一次
`MW × period_hours` 转换，并在 chronology 证据中记录
`force.scheme-c-source-power-to-energy/v1`。原始 kernel 仍读取未修改的文件，
并在自己的兼容边界内完成同样换算。

Prompt 95 已在同一个 Castle 数据包上验证：纯火电两期结果与 live monolithic
模块的发电量及运行成本精确一致；另外覆盖了手算 VRE、储能、进出口、预测误差
和 24 小时凸调度算例。这不表示新模块复制了 Scheme C 的所有历史启发式逻辑。
博士论文原始结果仍由 `scheme-c-psm` 复现；分阶段市场和未来 zonal balancing
使用各自独立的模块身份与结果来源记录。

