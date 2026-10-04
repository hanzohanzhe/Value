# FORCE 空间资产与天气预处理

## 这一阶段做什么

Prompt 97 在全国经济 agent 和分区物理 tranche 之间增加离线转换，但不会把每座
电站或每条 REPD 记录变成竞价者。投资、利润与现金流仍属于原经济 owner；网络
注入和天气可用率则按 `owner × technology × zone` 聚合后进入模型。

全国技术容量仍是权威总量。Scheme C 风电 `capacity_multiplier` 明确按每单位
`20 MW` 转换，然后各分区 tranche 会重新缩放到已接受的全国容量；映射残差超过
`1e-8 MW` 就失败。

## 分区份额优先级

抽象经济 agent 的份额依次取自：

1. 同技术已投运项目在各 zone 的 MW；
2. 同技术活动 planning pipeline 在各 zone 的 MW；
3. 用户明确输入的权重；
4. 如果仍无可用位置证据，则进入 `ENGLAND_FALLBACK`。

份额绑定数据包 revision，内生新增容量只能继承，不会反过来重算权重。有坐标或
已声明并网区的 REPD 项目保持单一区域，投产时完整继承 CAPEX、FOM、寿命和
owner 身份。

北爱尔兰项目不进入 GB 内部容量；爱尔兰交换仍只作为外部 interconnector 报价。
审计会列出被排除 ID、fallback MW，以及各技术 fallback 是否超过 1%。

## 坐标与海上风电

英国国家格网坐标在离线阶段由 `EPSG:27700` 转成 `EPSG:4326`，并保留原始
easting/northing、CRS 和 pyproj 转换说明。海上风电的天气位置使用海上坐标；
网络注入优先使用真实 connection/landfall override，否则确定性地选择最近海岸
DSO 参考点，并标为 `inferred_nearest_coast_dso`。缺少坐标时进入英格兰兜底区，
绝不把推断位置写成真实并网点。

## 两种可替换天气方法

- `force-representative-point-weather`：沿用 Scheme C 区域代表点曲线，并复制给
  该经济 agent 的各分区 tranche；
- `force-repd-era5-aggregated-weather`：离线读取已安装天气包在 REPD 位置的
  profile，再按 MW 聚合为 `owner × technology × zone` 曲线。

两者都输出 `force.zonal-availability-profile/v1`。年度运行只读取预先聚合好的
工件，不在竞价时做坐标转换、GIS 查询或逐资产读取 REPD/ERA5。Prompt 98 构造
正式分区数据包时，必须把所选方法和输出哈希写入数据包身份。

## 兼容边界

原有单体/铜板模块图身份保持不变。只有数据包绑定 `force.zonal.asset-map` 时，
初始状态才附加空间元数据。旧 planning/transition 会保留冻结份额；typed planning
原本就会把 project extensions 原样带入投产资产。本 Prompt 不加入输电求解器。
