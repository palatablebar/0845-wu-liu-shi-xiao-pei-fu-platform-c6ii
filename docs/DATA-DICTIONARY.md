# 字段定义

| 字段 | 类型 | 说明 |
|---|---|---|
| `waybill_id` | text | 主键 |
| `pickup_at` | datetime | 业务字段 |
| `deadline_at` | datetime | 业务字段 |
| `delivered_at` | datetime | 业务字段 |
| `paused_hours` | int | 业务字段 |
| `declared_value_cents` | int | 业务字段 |
| `invoice_cents` | int | 业务字段 |

空字符串、`-`、`NA`、`null` 和 `未提供` 按空值处理。金额字段在整理层转为整数分或整数最小单位；日期按 ISO 日期解析；带时间的字段按本地时间解析。标识字段保持为文本，前导零不会被去除。

## 暂停凭据

| 字段 | 类型 | 说明 |
|---|---|---|
| `waybill_id` | text | 凭据对应的运单号 |
| `paused_hours` | int | 覆盖该行的有效暂停小时数，必须为非负整数 |
| `ref` | text | 凭据号，可选，参与凭据摘要 |

## 批次派生字段

| 字段 | 说明 |
|---|---|
| `source.digest` / `source_digest` | 来源摘要：来源字节 + 规则 + 有效暂停凭据 |
| `source.pause_digest` | 凭据摘要，顺序无关 |
| `source.pauses` / `source.invalid_pauses` | 有效暂停条目 / 无效暂停条目及原因码 |
| `calculation.version` / `calc_version` | 计算版本，形如 `calc-<摘要前缀>` |
| `generation` | 计算代次，草稿每次因来源变化重算递增 |
| `frozen` | 是否为已签发冻结的快照 |
| `blockers` | 阻止签发的阻断原因码 |
