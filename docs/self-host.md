# 自托管
```bash
docker compose up -d          # 后端+前端同域单端口
```
- 数据：`backend/data/wealth.db`（WAL）；备份：设置页「加密备份」
- 反代：任何静态托管即可，API 同域 `/api/*`
- 部署形态无关：云端 API / 自托管 / 桌面单机同一套核心
