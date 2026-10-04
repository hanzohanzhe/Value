# FORCE 分区网络数据契约

## 适用范围

`force.zonal-network-pack/v1` 是可选“固定、无损、分区再调度”方法的数据入口。
它描述资源分区、计算走廊和带符号的 ETYS 式 cut set，不代表实际输电线路，也不
声称模拟 AC/DC 潮流、N-1 安全、电压、网损或输电扩建。

只有用户选择分区再调度扩展时，Data 页面才要求以下 8 类数据。原有铜板模型的
25 个输入和 Prompt 67 的 DC/AC 契约保持不变。

## 需求权威

每个分区 Study 必须明确选择一种模式。`scenario_scaled_zonal_shares` 先按网络包
计算每期份额 \(s_{z,t}=D^{network}_{z,t}/D^{network}_{GB,t}\)，再用研究数据包
的全国需求构造 \(D^{run}_{z,t}=s_{z,t}D^{research}_{GB,t}\)。因此全国实际和预测
需求仍由研究数据包决定。`network_pack_absolute_demand` 则直接采用网络包的分区
与全国需求，并沿用研究数据中的预测/实际比例来形成预测值；这是独立需求研究，
不能把它与情景需求铜板 run 的全部差异归因为网络约束。

当前 GB benchmark 固定使用 2024 年 DESNZ 邮编需求权重。以后可换成逐期或逐年
份额，但必须给出唯一且严格对齐的 period ID，并逐期守恒；不得循环重复、插值或
在数据缺失时静默平均分区。

## 字段字典

| 契约 / 字段 | 含义 | 校验边界 |
| --- | --- | --- |
| `network_pack_id` | 整套分区数据的稳定身份 | 声明 Study 后不得变化 |
| `scientific_sha256` | 拼装并类型化后的整包哈希 | 任一数据角色变化都必须重新核对 |
| `zone_id` | 稳定的科学分区 ID | 必须唯一；显示名称和地图不能替代它 |
| `display_name` | 前端显示名称 | 仅用于展示 |
| `dso_owner` | 数据构造时关联的 DSO | 是来源标签，不宣称排他的法律边界 |
| `nation` | 资源分区所在的 GB 国家 | v1 拒绝北爱尔兰内部节点 |
| `is_unconstrained_fallback` | 无法定位资产使用的英格兰兜底区 | 必须明确标记并单独审计 |
| `corridor_id` | 计算用路由边 ID | 必须唯一，不能同时作为互联线资产 |
| `from_zone_id`, `to_zone_id` | 走廊两端分区 | 两端都必须存在，不能自环 |
| `positive_direction` | 走廊潮流正方向 | 固定为 `from_to_positive` |
| `purpose` | 走廊的科学含义 | 固定为 `computational_routing`，禁止称为物理线路 |
| `boundary_id` | ETYS 式 cut set 的稳定 ID | 必须唯一 |
| `members[].coefficient` | 走廊对边界流量的符号贡献 | 只能是 `+1/-1`，同一走廊不能重复 |
| `forward_limit_mw` | 正方向边界容量 | 有限且非负 |
| `reverse_limit_mw` | 反方向边界容量绝对值 | 有限且非负；可与正方向不同 |
| `reverse_limit_method` | 反向容量的证据来源 | 独立数据或明确声明的对称假设 |
| `rating_profile_id` | 可选维护降额曲线 | 必须引用已声明曲线 |
| `multipliers` | 每期可用容量比例 | `0..1`；与需求时钟一致；v1 中跨年份固定 |
| `asset_id`, `zone_id`, `share` | 固定资产—分区分配 | 覆盖全部活动资产；每项资产份额之和为 1 |
| `mapping_method` | 坐标、区域比例、登陆点或兜底规则 | 写入审计；Study 中途不得换区 |
| `demand_mwh_by_zone` | 按 Study 模式作为绝对需求或分区份额来源 | 非负，且必须覆盖全部分区 |
| `national_demand_mwh` | 用于核对的全国需求 | 每期分区合计残差不得超过 `1e-8 MWh` |
| `interconnector_id`, `asset_id`, `zone_id` | 外部进口/出口报价的登陆区 | 保留有符号 profile 上限，不得当作内部走廊 |
| `capacity_mw_by_technology` | 空间分配前的技术容量 | 必须在容差内与映射后容量一致 |
| `fallback_asset_ids` | 放入英格兰兜底区的资产 | 必须报告，不得静默隐藏 |
| `loss_capability_absent_reason` | 明确表示没有网损计算 | 固定为 `lossless_v1`，不伪造“网损为零”的结果 |

## 数据角色和失败方式

必填角色为 `force.zonal.zones`、`corridors`、`cutsets`、`asset-map`、
`demand`、`ratings`、`interconnector-landings` 和 `spatial-audit`；可选
`force.zonal.geometry` 只用于地图显示。`examples/zonal-network-pack` 是 CC0
格式模板，不是英国网络数据。

每个文件由 SHA-256 绑定，拼装后的科学契约还有第二层哈希。未知分区、悬空或无
解释的孤岛、非法容量、漏映射资产、需求/容量不守恒以及互联线重复计数都会在
求解前失败。本契约不会在运行时下载数据。
