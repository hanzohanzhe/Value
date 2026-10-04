# 分阶段市场模块契约

契约族：`force.staged-market-contracts/v1`

本页说明全国日前/前置市场 PSM 与可替换的当期平衡模块之间的公开边界。
机器可读的权威定义位于
`gridform_core/data/contracts/staged-market-v1.schema.json`。

## 组合规则

凡是提供 `market.ahead-schedule/v1` 的 PSM，都必须且只能搭配一个
`balancing` 槽位模块。该模块使用 `force.balancing-module/v1`，提供
`market.balancing/v1`，并实现：

```python
def clear(model_input: BalancingInput) -> BalancingResult:
    ...
```

原有一体式 PSM 不选择 balancing 模块；旧 Study 的保存内容、模块图哈希和
执行路径均不改变。

## 公开契约

| 类型 | Schema 标识 | 用途 |
| --- | --- | --- |
| `AheadMarketInput` | `force.ahead-market-input/v1` | 单期预测需求、报价、期初储能状态 |
| `AheadMarketResult` | `force.ahead-market-result/v1` | 不可变的全国计划、出清价、结算电量和计划储能动作 |
| `FlexibilityBid` | `force.flexibility-bid/v1` | 带方向、价格、容量、物理成本和来源的平衡报价 |
| `BalancingInput` | `force.balancing-input/v1` | 日前结果哈希，以及实际需求、可用率、SOC、报价、时长和 VOLL |
| `BalancingResult` | `force.balancing-result/v1` | 平衡输入哈希、接受的调整、最终出力/SOC、弃电、停电、现金流、资源成本和残差 |
| `StagedMarketYearResult` | `force.staged-market-year-result/v1` | 每期两阶段结果哈希及所选模块身份 |

`AcceptedAdjustment` 是 `BalancingResult` 内的强类型记录，不是另行版本化
的顶层契约。

## 信息边界

前置市场输入和结果必须声明 `information_scope="forecast_only"`。这一阶段
不得出现实际需求、实际可用率或最终出力。前置结果冻结后，平衡模块才收到
这些实际信息，并用 `ahead_result_sha256` 与原结果绑定。
每份平衡结果还记录 `source_input_sha256`，从而把实际输入与报价纳入重放身份。

## 报价与结算符号

- `direction` 只能是 `up` 或 `down`；
- `available_mw` 必须大于零；
- 报价可以为有限的正数、零或负数；
- 同一期的 `bid_id` 不得重复，也不能串期；
- 被接受的调整量用带符号 MWh 表示；
- `cashflow_to_agent_gbp = accepted_delta_mwh × bid_price_gbp_per_mwh`。

## 重放身份

契约哈希采用 UTF-8、键排序且禁止非有限数的规范 JSON。分阶段 Study 的
运行快照和年度 checkpoint 同时记录 PSM 与 balancing 模块身份，因此替换
任一模块都会形成新的科学运行身份。一体式 PSM 不会被补入虚假的 balancing
槽位。

## 外部模块 manifest

```json
{
  "slot": "balancing",
  "contract_version": "force.balancing-module/v1",
  "provides_capabilities": ["market.balancing/v1"],
  "implementation": "your_package.module:YourBalancingModule"
}
```

正常的 FORCE `module.zip` 安装流程会检查实现中是否存在可调用的 `clear`
方法。网络等特定领域输入放入带类型的 `domain_payload`，不应改变通用平衡
契约。
