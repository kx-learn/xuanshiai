# 直播 v2 — TRTC 接入与试点准备

2026-10-02 上游兼容调整：本模块使用 `/api/v1/live/v2`、`live_v2_*` 表和 `live:v2:*` Redis 频道。上游原有直播接口、数据表及 `TENCENT_LIVE_*` 配置保留不变；本次未迁移或修改正式数据。历史验收不能替代整合版验收，最新结果见 [整合记录]( ./upstream-integration-20261002.md )。

2026-09-10。本期本地实现可联调，不代表企业小程序权限、云服务、业务资质或真机演练已通过。未修改线上数据库、未开通云服务、未进行 GitHub 操作。

## 2026-09-27 无云资源业务增补

独立测试环境已支持 `LIVE_MEDIA_MODE=disabled`，真实登录、MySQL、Redis、多人WS和既有申请／聊天可以独立验证；不要为消除缺云资源报错填写假Key。新增独立运营、版本名单维护、统一权限与对象范围、单控场者接管／交还及跳轮；完整运行、密钥预留和验收命令见 [无音视频真实业务演练](live-business-rehearsal.md)。默认trtc及下文真实媒体接入契约保留。以下2026-09-10 Redis替身等验证说明是历史记录，本轮真实Redis/TCP已另行验证，不代表目标WSS和云媒体已通过。

## 1. 安装及数据迁移

沿用现有 FastAPI、MySQL 8、Redis 和 JWT/用户会话。新增两个官方依赖，未升级或删除已有依赖：`tls-sig-api-v2>=1.1,<2`（MIT，实际 1.1），`tencentcloud-sdk-python-trtc>=3.1.173,<4`（Apache-2.0）。安装信息已写 pyproject.toml 和 uv.lock。

```powershell
uv sync --extra dev
```

仓库 .python-version 为 3.11。本机验证实际使用已有 Python 3.12.4，以 `uv sync --python 3.12 --extra dev` 建立独立 .venv；没有改系统 Python 或 .python-version。生产仍按团队运行时安装锁文件并验收。

目标数据库须由有权限的维护者审核并执行 `migrations/20261002_live_v2_trial.sql`。这是六张新增表：场次、成员、操作、场后机会、举报、旧媒体清理任务；不删改既有用户、申请、关系或聊天表。现有初始化器也会读取该文件，但已有库部署推荐只执行本次增量迁移，不运行合成测试初始化器。部署包应保留 migrations/ 文件。

回退时先关闭正式试点入口与开播开关，保留场次、已发申请、机会及审核记录；不要通过删表撤销已发生的双方同意。已开始的云转推任务需要停止，不能仅停进程。

## 2. 准备腾讯云与微信资源

1. 确认实际企业小程序主体、音视频业务类目/组件权限及适用资质。审核结果由业务主体确认，不通过客户端代码或勾选按钮替代。
2. 创建腾讯云 TRTC 应用，开启高级权限控制，使进房及发布必须核验 PrivateMapKey。记录 SDKAppID，SDK 密钥只进入服务端密钥配置。
3. 配置独立的腾讯云 API 凭据，并授权所需动作：StartPublishCdnStream、StopPublishCdnStream、DismissRoom。不要把控制台主账号长期密钥放在客户端或文档。
4. 配置腾讯云直播推流域名、HTTPS 播放域名、推拉流鉴权密钥，完成域名备案、证书和 CNAME 等实际要求。观众使用混流 FLV 播放地址，接口不会创建或购买域名。
5. 部署 API HTTPS 与 WebSocket WSS；微信后台配置请求、Socket、音视频所需合法域名。实时订阅使用 Authorization Header，不能把访问令牌放在 URL。
6. 确定工作人员安排及本场展示/审核留存告知，明确主体、用途、期限、可访问人员和删除流程。当前仅实现业务、同意和处置记录；音视频录制及到期删除必须按最终规则另行接入。本期不提供用户公开回放。

参考：[微信小程序集成](https://cloud.tencent.com/document/product/647/116548)、[高级权限控制](https://cloud.tencent.com/document/product/647/32240)、[UserSig](https://trtc.io/zh/document/34385)、[开始混流转推](https://cloud.tencent.com/document/api/647/81479)。资源、资质和费用以实际主体与控制台为准，本次未作付费操作。

## 3. 环境变量

模板位于 .env.example；真实值写忽略的 .env 或部署系统，不写入仓库。布尔标志表示工作人员已经完成核验，不是自动探测结果。

| 变量 | 含义 |
| --- | --- |
| LIVE_TRIAL_ENABLED | 正式试点开关，默认 false；真机及留存条件通过后才设 true |
| LIVE_WECHAT_AV_VERIFIED | 企业小程序音视频权限已确认，默认 false |
| LIVE_DEVICE_PILOT_VERIFIED | 真实多端演练已验收，默认 false |
| LIVE_PRIVATE_MAP_KEY_ENABLED | TRTC 高级权限控制已在控制台启用并验证，默认 false |
| LIVE_SDK_APP_ID / LIVE_SDK_SECRET | TRTC SDK 应用及签名密钥 |
| LIVE_CLOUD_SECRET_ID / LIVE_CLOUD_SECRET_KEY | 服务端腾讯云 API 凭据 |
| LIVE_CLOUD_REGION | 默认 ap-guangzhou，须与实际应用/API 支持地域一致 |
| LIVE_CDN_PUSH_DOMAIN / LIVE_CDN_PLAY_DOMAIN | 只填写域名，不含协议、路径、查询串 |
| LIVE_CDN_PUSH_KEY / LIVE_CDN_PLAY_KEY | 推流与播放 URL 鉴权密钥 |
| LIVE_RETENTION_NOTICE | 已确认的审核留存说明，非空；不是录制已完成的证明 |

`GET /api/v1/live/v2/resources` 只返回 ready 和缺失变量名称，不返回值。演练需要除正式开关和真机已验收标志外的配置齐备；主持先使用 `rehearse` 验证设备与上下台，不存在“必须先验收才允许演练”的循环。正式 `start` 额外核对这两个标志。

2026-09-14 已建立本地准备用 .env，仅填已取得的非敏感 AppID 与推流域名；密钥、播放域名和各项核验仍待补齐，详见 [平台接入进度与人工确认清单](live-platform-readiness.md)。这不是完整部署配置。不要为消除 503 填入合成密钥或把未经核验的标志设 true。

## 4. SDK 调用与权限

服务端 `TLSSigAPIv2.gen_sig` 签发 300 秒 UserSig；`gen_sig_with_userbuf` 签发房间绑定 PrivateMapKey。Python 官方库不提供 Node 版 genPrivateMapKey，项目只按官方数值房间 UserBuf 格式打包字段，签名和压缩仍交官方库。发布权限位为 63；候场接收权限位为 42，不含发布音视频位。SDK 秘密不出服务端。

首次有效媒体凭证请求启动 `StartPublishCdnStream`，由 SDK 构建腾讯云 API 请求。默认 720×1280、15fps、视频 1400kbps、音频 64kbps、自动九宫格，转推腾讯 CDN。观众凭证仅有短时签名 HTTPS FLV 地址，不含 RTC 发布凭证。

云端 AgentParams 按当前官方 SDK 只接受 UserId/UserSig/MaxIdleTime，不添加 SDK 未声明的 PrivateMapKey 字段。启用高级权限后的云端机器人进房、转推实际结果须在资源准备阶段与腾讯云实际应用联合验证；若不兼容，先向云方核实受支持方式，不通过关闭房间权限控制来绕过。

舞台人数上限由服务端状态控制。上下台、轮换或结束使媒体房间换代，客户端重新获取新房间凭证。旧发布凭证无法加入新舞台；旧房间及任务写 SQL 清理队列，后台执行 StopPublishCdnStream 与 DismissRoom。已结束任务/不存在房间按完成处理；其他 SDK 错误保留任务并重试，不伪装成功。

重要取舍：轮换房间导致全体互动端重新进房，CDN 观众重新切流。当前实现优先保证旧凭证无法重返当前舞台，不声称无缝切换。真实 8 台设备的中断时长、音量/摄像头恢复和观众体验必须验收；不满足试点体验就先调整媒体方案，不能直接开放正式开关。

## 5. 状态和申请事务

小场次作为一个 MySQL JSON 聚合保存，业务命令锁定场次行后执行。修订号和幂等键防止过期操作、重复执行；没有通用工作流框架。Redis 只广播修订号，各订阅者重新读取并生成自己的快照，数据库是最终依据。

私密选择不进入操作日志或共享消息；公开快照只含本人选择与截止后互选。日志保存动作、版本、同意版本、必要处置原因，不记录凭证。WebSocket 持续检查登录会话及场次资格，断线客户端取最新快照，不重放选择。

场后每对一次机会以有序双方 ID 唯一约束。沿用现有用户对行锁，将创建 match_apply 与占用 live_v2_opportunity 放在同一事务。没有前端免扣声明，不扣日常申请额度；拒绝时不退日常次数。双方同时提交返回同一申请；复用已经使用的机会只返回原申请状态，不重新发送。

## 6. 验证

```powershell
.venv/Scripts/python.exe -m pytest tests/test_live_domain.py tests/test_live_media.py -q
.venv/Scripts/python.exe scripts/export_live_api_docs.py
.venv/Scripts/python.exe -m pytest -q
git diff --check
```

真实 MySQL 测试必须使用隔离执行器，不指向现有业务库：

```powershell
.venv/Scripts/python.exe scripts/verify_parent_mbti_mysql.py --mysqld 'C:/Program Files/MySQL/MySQL Server 8.0/bin/mysqld.exe' --artifacts 'C:/Users/Administrator/AppData/Local/Temp/xsa-live-verification' --tests tests/test_live_mysql.py
```

脚本创建随机端口和独立合成库，结束后停该临时 MySQL，保留诊断文件，移除临时凭据文件。本机 MySQL 初始化在中文 artifacts 路径失败，使用 ASCII 临时路径后通过。测试含真实用户会话鉴权、4 轮、首轮 3 组、无互选、同对不重复、双方并发申请、日常次数用完、拒绝不退款、过期、非法对象及同意后聊天。腾讯云与 Redis 是外部边界替身，不把此测试称为真实云演练。

完整测试有 4 项既有社区失败（此前已记录于 docs/待完成事项.md），不能称全量全绿；本次直播专项独立通过。真实 Redis 分发、合法域名、iOS/Android 和 80 分钟真人场次仍待验收。

## 7. 下一步

维护者执行目标环境增量迁移、提供真实云配置并确认微信权限。邀请 11 位互动参与人及少量观众，完成告知和设备检查，先用演练模式验收真实连麦与上下台。记录全部角色操作负担和切流表现；留存接入及真机检查完成后，再开正式四轮受邀试点。
