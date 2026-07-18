# Xuanshi AI API

这是一个基于 FastAPI 的后端项目基础骨架，当前已包含应用入口、环境配置、健康检查、测试和后续业务模块预留目录。

## 环境要求

- Python 3.11+
- MySQL 8+
- Redis 7+

## 本地启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
python main.py
```

服务启动后访问：

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/api/v1/health`
- `http://127.0.0.1:8000/docs`

## 配置说明

`.env.example` 是带注释的配置模板，`.env` 是本地开发配置。部署到测试或生产环境时，请通过部署平台的环境变量注入配置，尤其要替换 `SECRET_KEY`、数据库密码和 Redis 连接信息。

## 测试

```powershell
pytest
```

## 目录说明

```text
app/
  api/       HTTP 路由和 API 聚合
  core/      配置和基础设施
  db/        数据库连接与会话
  models/    ORM 模型
  schemas/   Pydantic 请求/响应模型
  services/  业务服务层
tests/       自动化测试
storage/     本地运行时文件
logs/        本地日志目录
```
