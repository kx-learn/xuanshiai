# 2026-10-02 上游整合与直播 v2 验收

## 范围与结构

以 `kx-learn/xuanshiai` 的 `main`（`50c8001fc3192548747f5368f60e327c87f68d95`）为基线，合入本地父母授权、消息、MBTI 与四轮直播业务。在 `feature/integrate-live-business` 提交，不修改主线，不访问正式数据库或云控制台。

| 能力 | 上游原有实现 | 四轮相亲与无媒体演练 |
| --- | --- | --- |
| HTTP 基址 | 原 `/api/v1/live` 等接口保持原样 | `/api/v1/live/v2` |
| 路由、模型、事务服务 | `live.py` | `live_v2.py` |
| 业务表 | 原 `live_*` 表保持原样 | `live_v2_session/member/action/opportunity/report/media_cleanup` |
| 云配置 | `LIVE_ENABLED`、`TENCENT_LIVE_*` | `LIVE_MEDIA_MODE`、`LIVE_SDK_*`、`LIVE_CLOUD_*`、`LIVE_CDN_*` |
| 前端调用 | `api/live.uts` | `api/live-v2.uts` |

v2 的领域状态、统一权限和媒体分别位于 `live_domain.py`、`live_permissions.py`、`live_media.py`。Redis 更新通知使用 `live:v2:{场次ID}:revision`，站内通知对象使用 `live_v2_session`。不在原表内混放不兼容 JSON，不迁移或重算原直播记录。

## 运行与接入

1. 仅在独立开发／测试库准备现有基础表及 `migrations/20260906_parent_delegation.sql`、`migrations/20261002_live_v2_trial.sql`。这不是授权对正式库执行迁移。
2. 配置 `ENVIRONMENT=testing`、独立 `DATABASE_URL`／`REDIS_URL`、服务端 `SECRET_KEY`、`LIVE_MEDIA_MODE=disabled`；测试短信、微信 Provider 沿用原登录接口。
3. 启动 FastAPI，通过正常登录获取会话。登录后读取 `GET /api/v1/live/v2/resources`；只返回缺项名称，不返回密钥。
4. 运营搜索真实测试账号并建立名单。完整接口见 [v2 接口](api/live-v2.md)、[业务增量](api/live-v2-business.md)、[字段字典](api/live-v2-fields.md)、[OpenAPI](api/live-v2.openapi.json)。

长期环境必须先完成迁移再部署依赖新机会表的申请代码；不能只部署前端。隔离执行器会创建临时 MySQL，业务模式另起独立 Redis，停止后保留诊断数据。不要把执行器改成连接正式库。

```powershell
.venv/Scripts/python.exe scripts/verify_parent_mbti_mysql.py --mysqld 'C:/Program Files/MySQL/MySQL Server 8.0/bin/mysqld.exe' --artifacts C:/Users/Administrator/AppData/Local/Temp/xsa-integration-20261002 --live-business --tests tests/test_live_business_mysql.py tests/test_live_business_ws.py
```

MySQL 的临时目录使用 ASCII 路径；可加 `--serve-port 8000 --serve-seconds 900` 供微信工具连接，自动关闭。父母／MBTI 与媒体事务两套夹具分别运行，避免固定账号 fixture 互相污染。

所有云密钥在 `.env.example` 保留空位。签名、服务端 API、推／播放鉴权是不同用途；真实值只能注入忽略的服务端环境文件或部署变量。聊天中曾公开的密钥不复用。`disabled` 不提供虚假凭证；`trtc` 仍要求平台权限和真机验收。

## 本次维护重点

- 上游手机号、实名、账号可见性、资料、拉黑与关系限制继续生效，直播机会只免日常申请次数。
- 免费机会与申请在同一事务完成；并发重放使用锁定读取取得 MySQL 最新申请，避免重复读快照错过刚提交的记录。
- 社区申请失败只补偿实际扣除的日常次数；未扣不补，补偿异常不覆盖原异常。
- 普通消息答复使用实名依赖；父母代聊必须绑定有效子女授权，撤销后不可发送或修改子女黑名单，按父母身份举报仍可用。
- 媒体上传复用上游审核任务与审核状态，不用新消息入口绕过审核。父母端仍限制文本、保护照片与联系方式。
- 后端学历字典按最新资料枚举映射，未重复引入旧昵称校验与更新函数。

## 实际验证

| 检查 | 结果 |
| --- | --- |
| v2 领域、权限、禁用媒体、版本隔离、兼容与社区定向单元测试 | 158 passed / 4 skipped；跳过的是社区外部实例测试 |
| 真实 MySQL + Redis + HTTP + WebSocket | 2 passed；四轮、接管、名单、并发申请、拒绝、聊天门槛及实时同步 |
| 父母／MBTI 独立 MySQL | 1 passed；授权、并发、幂等、撤销、持久化 |
| 媒体契约 MySQL | 1 passed；云调用使用测试替身，不是真实 TRTC 验收 |
| 全量无外部服务单元回归 | 2388 passed / 8 failed / 4 skipped |
| v2 源码与新增兼容测试 Ruff | 通过 |

全量八项失败均在未修改的上游快照复现：七项依赖外层产品／架构文档或相邻前端目录，一项是 AI 草稿相同 `updated_at` 时间的排序不确定性（查询也缺少稳定第二排序键）。这些仍是失败，不作为已通过或无害项处理；本次未顺便改动 AI 画像业务。

测试环境均为合成账号，真实数据库为本地临时实例；未访问正式用户数据。完整本机证据：`C:/Users/Administrator/AppData/Local/Temp/xsa-unit-review-20261002-1745/`、`xsa-integration-20261002/`、`xsa-live-targeted-20261002.xml`。

前端编译、微信交互、包体和合并后遗留问题见前端 `docs/verification/upstream-integration-20261002/README.md`。不能把这些业务检查写成真实连麦、上下台、混流、CDN、平台权限或正式上线已完成。

## 发布方式

提交任务分支并推送个人仓库；上游后端无直接写权限，通过个人分支的 Draft PR 交付上游。需要维护者审查遗留失败和数据库发布顺序后才能合入；不自动合并、不强推、不删除已有分支或备份。
