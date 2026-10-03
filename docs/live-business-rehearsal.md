# 直播 v2 — 独立真实业务演练

2026-10-02 上游兼容调整：本模块使用 `/api/v1/live/v2`、`live_v2_*` 表和 `live:v2:*` Redis 频道。上游原有直播接口、数据表及 `TENCENT_LIVE_*` 配置保留不变；本次未迁移或修改正式数据。历史验收不能替代整合版验收，最新结果见 [整合记录]( ./upstream-integration-20261002.md )。

更新：2026-09-27。适用独立开发／测试环境，不是正式上线说明。产品规则以相邻前端工作区 `PRODUCT.md` 为准。接口见 [增量契约](api/live-v2-business.md)、[字段字典](api/live-v2-fields.md) 和 [OpenAPI](api/live-v2.openapi.json)。

## 1. 三种场景

| 场景 | 数据与登录 | 媒体 |
| --- | --- | --- |
| 前端 `mode=demo` | 本机虚构状态，可切角色，不调用后端 | 不连接 |
| 本文业务演练 | 正常登录会话、真实 API、独立 MySQL、真实 Redis | 服务端 `LIVE_MEDIA_MODE=disabled`，没有凭证或假推流地址 |
| 正式直播 | 正式账号、数据库和业务流程 | `LIVE_MEDIA_MODE=trtc`，仍需资源、权限、真机与留存验收 |

默认媒体模式仍为 `trtc`。场次创建时把模式写入场次状态，客户端 query/body 不能改模式；历史记录缺省为 `trtc`。`staging` / `production` 配置 `disabled` 会启动失败。不能把正式环境改名为 testing 来绕过开播条件。

## 2. 现在需要填写什么

不要覆盖现有 `.env`。为独立测试服务从 `.env.example` 准备配置，真实值只写被忽略的服务端文件或部署环境变量。

| 配置 | 用途与填写要求 | 验证 |
| --- | --- | --- |
| ENVIRONMENT | `testing`；调试才使用 `development` | 启动配置校验 |
| DATABASE_URL | 指向专用 MySQL 测试库，不是业务正式库 | 健康检查＋写入合成场次 |
| REDIS_URL | 指向独立 Redis；会话、限流、实时版本分发使用真实连接 | PING＋多账号 WS 测试 |
| SECRET_KEY | 此测试环境独立的强随机 JWT 密钥 | 正常登录、会话撤销测试 |
| LIVE_MEDIA_MODE | 明确 `disabled` | 已登录 GET `/api/v1/live/v2/resources` |
| SMS_PROVIDER / WECHAT_PROVIDER | 沿用仅开发／测试允许的 `mock` Provider | 实际短信发送、手机号登录或测试微信登录接口 |
| AUTO_INIT_DB | 长期测试服务建议 false，由维护者应用现有迁移 | 不在服务启动时向未知数据库灌测试数据 |

Mock 仅替换短信／微信平台凭据，不替换直播 API、数据库或权限判断。测试验证码遵循 `SMS_MOCK_CODE`；客户端仍走正常登录，不手工伪造 JWT。没有新增测试专用绕过实名的接口；合成账号由隔离测试夹具准备，正式参与仍校验账号、成年、手机和实名，学历认证不是门槛。

长期测试库复用现有基础结构及 `migrations/20261002_live_v2_trial.sql`。本轮新增字段在既有场次 JSON 内，不新增数据表或重复保存业务状态。旧式运营兼任主持等席位的未开场场次，要先用编辑接口调整完整名单；不重算已结束记录和机会。

启动：在本项目中执行 `.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`。跨设备访问需部署专用测试 HTTPS/WSS 和合法域名；本机地址不能直接用于手机真机。

## 3. 后续腾讯云位置（现在全部可留空）

| 服务端配置 | 用途 | 后续验证 |
| --- | --- | --- |
| LIVE_SDK_APP_ID / LIVE_SDK_SECRET | TRTC 应用、短期 UserSig 与房间权限票据签名 | 真实进房、角色接收／发布权限 |
| LIVE_CLOUD_SECRET_ID / LIVE_CLOUD_SECRET_KEY / LIVE_CLOUD_REGION | 云端混流、转推及清理 API | Start/StopPublishCdnStream、DismissRoom |
| LIVE_CDN_PUSH_DOMAIN / LIVE_CDN_PUSH_KEY | 云直播推流域名及鉴权 | TRTC 混流转推成功 |
| LIVE_CDN_PLAY_DOMAIN / LIVE_CDN_PLAY_KEY | 观众播放域名及鉴权 | 观众实际播放、过期地址失效 |
| WECHAT_APP_ID / WECHAT_APP_SECRET | 正式微信登录 | 正式 Provider 登录，禁止 mock |
| LIVE_WECHAT_AV_VERIFIED / LIVE_PRIVATE_MAP_KEY_ENABLED | 已人工核实的小程序音视频、高级房间权限 | 控制台＋真机核验后才填写 true |
| LIVE_DEVICE_PILOT_VERIFIED / LIVE_TRIAL_ENABLED | 真机试点验收、正式开放 | 先验收再开放，不用开关伪造通过 |
| LIVE_RETENTION_NOTICE | 业务主体确认的必要审核留存说明 | 确定实际采集、权限、期限和删除方式；不是录制已接入的证明 |

模板里没有真实值。此前在聊天中出现的密钥不直接复用，上线前轮换并安全注入；密钥永不写前端、截图或操作记录。`resources` 只报告缺项名称，不报告值；`business_ready` 不是数据库健康检查，`media_ready` 不是音视频验收证书。完整媒体接入契约继续见 [live-trial.md](live-trial.md)。

## 4. 业务链与权限

1. 有效管理员搜索现有账号，创建完整草稿；创建者成为唯一场次运营，不能出现在主持、红娘、嘉宾或观众席位中。其他管理员没有跨场访问特权。
2. 运营排期。各人独立确认或拒绝邀请，观看预约另外记录；确认者填写本人授权称呼和介绍。通知复用既有站内通知及用户通知偏好，不依赖短信／订阅消息。
3. 未开场时运营可携版本编辑。角色、席位、主嘉宾顺序变化者重新确认签到；时间或告知变化，全员重新确认。仅改标题保留确认。成员索引、状态、通知、日志在同一事务内更新。
4. 业务签到没有设备检测成功记录。11 位互动人员均确认、签到且未离场，才能开场；观众不阻塞开场。最多 8 个逻辑舞台席位不代表 8 路真实出镜。
5. 唯一有效控场者管理环节、暂停／恢复、时长、发言和上下台。默认主持；运营填写原因接管／交还。接管不更改主持公开角色、不自动上台，不授予选择权。主持不能移出运营；运营不能代亮灯、代选择、代申请或代答复。
6. 问答仅红娘与本轮有效候选可举手、撤回；主嘉宾和候场嘉宾不能举手。切环节清理举手／旧发言。暂停禁止新选择和推进，保留退出、离场和撤回公开意向。
7. 亮灯不绑定私密选择，特别心动不插队。选择截止由服务端时间判断，截止前可修改；按候选席位计算互选队列，不补配、不任意调序。主动离场／移出撤销未完成交流，已完成记录保留；主嘉宾离场需控场者填写原因确认跳轮。
8. 四轮结束后，每对已完成交流者产生共享一次、72 小时有效的免费机会。沿用原申请、关系与聊天；实际发送才使用机会，双方同时发起归并同一申请。免费不绕过实名、资料、封禁、拉黑及其他关系限制；拒绝不恢复机会、不退日常次数。

## 5. 为什么这样划分

- `live_permissions.py`：一份策略计算角色、阶段、资格和对象范围，同时用于命令鉴权与快照能力；页面按钮不作为安全边界。
- `live_domain.py`：场次状态转换、名单变更、选择和交流；不访问云、数据库或 Redis。
- `live_v2.py`：数据库锁行事务、版本与幂等、成员索引、通知、审计及机会。复用小场次 JSON 聚合，不引入通用工作流引擎。
- `live_media.py`：媒体准备、签名、混流和清理。disabled 路径不签名、不生成媒体房间、不启动清理云调用。

公开快照是字段白名单，只含 `me.selection` 和截止后的互选；共享 Redis 通道只有版本号。每个 WS 连接按当前账号重新生成快照，定期检查会话；账号撤销、成员移出会断开。断线不记为离场，不自动转移主持权限，不重放操作。

接管、交还及被拒绝的过期控场操作留痕。分页日志只含动作、执行结果、必要目标和原因，不含单方选择、签名、密钥。命令旧版本409，由本人刷新后重新确认；没有静默重试或代提交。

## 6. 可复现验收

```powershell
.venv/Scripts/python.exe -m pytest tests/test_live_business_domain.py tests/test_live_domain.py tests/test_live_media.py tests/test_live_disabled_media.py -q
.venv/Scripts/python.exe scripts/verify_parent_mbti_mysql.py --mysqld 'C:/Program Files/MySQL/MySQL Server 8.0/bin/mysqld.exe' --artifacts 'C:/Users/Administrator/AppData/Local/Temp/xsa-live-business-verification' --live-business --tests tests/test_live_business_mysql.py tests/test_live_business_ws.py
.venv/Scripts/python.exe scripts/export_live_api_docs.py
```

执行器只创建自己的随机端口 MySQL 和 WSL `Ubuntu` 中的 Redis 进程，独立随机密码，无需改现有 `.env`；结束后停这些进程，删除本次临时凭据文件，保留合成库与脱敏诊断。若本机发行版不同，使用 `--redis-wsl-distro`。不会安装或操作云资源。

UI 验收可在上面命令增加 `--serve-port 8000 --serve-seconds 600`。测试成功后临时 API 最多运行10分钟，只绑定127.0.0.1；端口被占用会失败，不停止已有服务。它不替换业务接口，可配合前端 `scripts/verify-live-business-devtools.cjs`，通过测试账号的正常登录使用真实接口。示例账号1020是夹具创建的合成运营，手机号13900001020；不是正式用户。不要把夹具导入正式库。

四轮 API 集成只替换业务时钟以跳过约64分钟等待，真实登录、鉴权、MySQL、Redis、事务和通知均执行；云边界放置“触发即失败”的守卫，不返回假云成功。TCP WebSocket 测试运行实际 uvicorn，7路连接，不替换时钟或实时链路。

本轮结果与未验证事项统一记录于前端 `docs/verification/live-business/README.md`。真实音视频、目标HTTPS/WSS、iOS/Android及正式上线不属于本阶段完成声明。
