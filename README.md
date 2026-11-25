# 物流时效赔付台

干线客服专员处理工作日顺延与赔付阶梯的本地工作台。样例、规则和复核记录都在项目内，不依赖外部服务。

## 启动

```bash
docker compose up --build
```

打开 `http://127.0.0.1:${PORT:-18520}`。默认端口见 `docker-compose.yml`。

## 验证

```bash
docker compose exec -T app pytest -q
docker compose config --quiet
```

## 操作

1. 在左侧选阶段，查看采信、整理、计算、判定和对账结果。
2. 选择 `dirty` 样例观察坏行和隔离原因。
3. 换 `clean` 样例执行批次，核对来源与版本面板；凭据补录后草稿会原地重算。
4. 填写复核意见后签发，下载证据 JSON，核对来源摘要、计算版本、入账行与签发版本。同一来源重跑沿用原批次，已签发版本不再改写。

业务规则见 `docs/BUSINESS-RULES.md`，字段定义见 `docs/DATA-DICTIONARY.md`。
