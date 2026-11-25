# 接口

- `GET /`：工作台。
- `GET /api/catalog`：阶段、字段和样例。
- `POST /api/stages/{stage}`：按阶段返回处理结果；可带 `credentials` 观察补录后的阶段结果。
- `POST /api/runs`：执行完整批次并保存草稿；同一来源复用原批次，可带 `credentials`。
- `GET /api/runs/{id}`：读取批次，含来源摘要、计算版本与签发冻结状态。
- `POST /api/runs/{id}/credentials`：补录暂停凭据，提交 `credentials`；草稿原地重算，已签发版本冻结。
- `POST /api/runs/{id}/review`：签发或暂缓，提交 `decision`、`comment`、`expected_revision`。
- `GET /api/runs/{id}/evidence`：下载已签发证据；同一签发版本重复下载结果一致。
- `GET /api/examples/{profile}`：下载样例。
- `GET /healthz`：健康检查。
