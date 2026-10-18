# 直播 v2 — 接口契约

2026-10-02 上游兼容调整：本模块使用 `/api/v1/live/v2`、`live_v2_*` 表和 `live:v2:*` Redis 频道。上游原有直播接口、数据表及 `TENCENT_LIVE_*` 配置保留不变；本次未迁移或修改正式数据。历史验收不能替代整合版验收，最新结果见 [整合记录]( ../upstream-integration-20261002.md )。

2026-09-10 新增，2026-09-27同步真实业务演练。新增搜索、名单编辑、控场、日志的完整参数见 [live-v2-business.md](live-v2-business.md)。基础路径 `/api/v1`；`https://api.example.test` 仅为示例，须替换测试地址。JSON为snake_case，时间为UTC Unix秒。不存在客户端可信的免费、角色或媒体开关。

所有 HTTP 接口要求 `Authorization: Bearer <当前账号的 access_token>`；POST 使用 `Content-Type: application/json`，响应均为 JSON。认证、手机号、实名沿用当前账号体系，不使用文档示例账号代替真实用户。详细类型、上下限、默认值和字段含义见 [字段字典](live-v2-fields.md)，机器契约见 [OpenAPI](live-v2.openapi.json)。

## 1. 端点总表

| Method 与完整 URL | 权限 | 请求 | 成功响应 |
| --- | --- | --- | --- |
| GET https://api.example.test/api/v1/live/v2/resources | 已登录 | 无请求体，无 query | 200 LiveResources |
| GET https://api.example.test/api/v1/live/v2/sessions | 已登录，只查本人受邀场次 | 无请求体，无 query | 200 LiveList |
| POST https://api.example.test/api/v1/live/v2/sessions | 当前有效 admin 角色 | LiveCreateRequest，见创建示例 | 201 LiveSnapshot |
| GET https://api.example.test/api/v1/live/v2/accounts | 当前有效 admin 角色 | q、page、page_size，见增量契约 | 200 LiveAccountList |
| PUT https://api.example.test/api/v1/live/v2/sessions/1 | 本场运营，未开场 | LiveUpdateRequest：完整名单＋expected_revision | 200 LiveSnapshot |
| GET https://api.example.test/api/v1/live/v2/sessions/1/actions | 本场运营、主持、红娘 | page、page_size，见增量契约 | 200 LiveActionList |
| GET https://api.example.test/api/v1/live/v2/sessions/1 | 场内未被移出成员 | sid 为正整数；无请求体 | 200 LiveSnapshot |
| POST https://api.example.test/api/v1/live/v2/sessions/1/commands | 本人/本场工作人员，见命令表 | LiveCommand | 200 LiveSnapshot |
| POST https://api.example.test/api/v1/live/v2/sessions/1/credentials | trtc有效房间，成员资格见第5节；disabled拒绝 | sid 正整数；无请求体 | 200 LiveCredentials |
| GET https://api.example.test/api/v1/live/v2/sessions/1/results | 本场成员，仅本人；移出不抹除已完成机会 | sid 正整数；无请求体 | 200 LiveResults |
| POST https://api.example.test/api/v1/live/v2/sessions/1/reports | 场内未被移出成员，不额外要求实名 | LiveReportRequest | 201 LiveReport |
| GET https://api.example.test/api/v1/live/v2/sessions/1/reports | 主持或场次创建者 | sid 正整数；无请求体 | 200 LiveReport 数组 |
| POST https://api.example.test/api/v1/live/v2/sessions/1/reports/2/resolve | 主持或场次创建者 | report_id 正整数；LiveReportResolution | 200 LiveReport |
| POST https://api.example.test/api/v1/discovery/applications/8 | 原申请资格 + 本人有效机会 | ApplicationCreateRequest 新增可选 live_opportunity_id | 201 原 ApplicationResponse 新增机会 ID |

列表没有分页参数：试点场次列表最多返回本人最近 50 场，按 scheduled_at 倒序；举报列表最多最近 100 条，按 id 倒序。空列表为 `[]`，不把有限列表描述成全量历史检索。

## 2. 创建场次

Header 示例适用于本文所有请求：

```http
POST /api/v1/live/v2/sessions HTTP/1.1
Host: api.example.test
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{"title":"周末受邀相亲场","scheduled_at":2000000000,"host_id":1,"matchmaker_ids":[2,3],"male_ids":[4,5,6,7],"female_ids":[8,9,10,11],"main_order":[4,8,5,9],"spectator_ids":[12],"notice":"本场仅向受邀人员展示已授权资料及音视频，不提供公开回放。实际必要审核留存规则须由业务主体明确。"}
```

名单所有账号须有效、成年、绑定手机、实名且不得兼任；男女组别匹配账号资料。main_order是名单内不重复的2男2女；嘉宾数组顺序决定席位。scheduled_at须在未来。创建者成为独立运营，出现在任何其他席位时返回422，不再允许兼任。

返回 LiveSnapshot；初始 status=draft、revision=0、round_index=0、phase=intro、deadline=null、exchanges=[]。创建不会自动预约、代替嘉宾授权或启动音视频。字段逐项见第 4 节。

## 3. 命令接口

通用请求示例：

```http
POST /api/v1/live/v2/sessions/1/commands HTTP/1.1
Host: api.example.test
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{"command_id":"live_click_000001","expected_revision":12,"action":"choose","targets":[8,9]}
```

`command_id` 是本次操作的 8—64 位字母、数字、下划线或短横线标识；同一次网络重试使用原 ID 和原请求。同 ID 不同内容返回 409。同 ID 相同内容不再次执行，返回当前快照；新操作必须新 ID。`expected_revision` 与最新快照相等才执行，冲突后刷新并让本人重新确认，禁止客户端自动重放过期意愿。

以下字段在通用三字段外按 action 使用。可选字段不传的默认值在字段字典中给出；不接受未定义字段。

| action | 操作者与状态 | 额外字段及含义 |
| --- | --- | --- |
| accept | 本人，场次未结束；成年/手机/实名有效 | value=true、consent_version=live-trial-v1、非空 display_name；introduction 可空 |
| reserve | 本人，未结束 | value=true 预约，false 取消；不提升资格 |
| check_in | 非运营本人已确认；成年/手机/实名有效 | trtc非观众须device_checked=true；disabled只业务签到、不记设备通过 |
| leave | 本人，未结束，暂停也可 | 无；退出舞台并撤销未完成交流，不自动发申请 |
| schedule | 场次创建者，draft | 无；变为 scheduled |
| rehearse | 有效控场者，draft/scheduled，11位互动人员确认签到 | 仅trtc且演练资源齐备；不开始轮次计时 |
| start | 有效控场者，draft/scheduled，11人确认签到未离场 | disabled只开始业务；trtc额外检查正式媒体资源标记 |
| pause / resume | 有效控场者；live / paused | 保存/恢复剩余秒数 |
| extend | 有效控场者，live且截止前 | seconds默认60，范围1—600；不重新开启已截止选择 |
| advance | 有效控场者，live | choice/exchanges不提前截止；主嘉宾离场须先明确skip_round |
| stage | 有效控场者，live或已开启媒体演练 | target_id在allowed_targets.stage_ids；value上下台；最多8个逻辑席位 |
| speaker | 有效控场者，live或媒体演练 | target_id在allowed_targets.speaker_ids，已上台且本环节可发言 |
| hand | 问答截止前、在场红娘或本轮候选人 | value申请/撤回；无关候场嘉宾、主嘉宾不可举手 |
| light | 本轮主嘉宾/候选人，interest 截止前 | target_id、value=true 亮灯；value=false 撤回本人亮灯，撤回允许跨环节和暂停 |
| special | 本轮主嘉宾/候选人，interest 截止前 | target_id、value=true 消耗本场一次；false 撤回但不恢复，撤回允许跨环节和暂停 |
| choose | 本轮本人，choice 截止前，live | 主嘉宾 targets 为 0—3 个不同有效候选 ID；候选人 value=true 愿意/false 暂不交流 |
| withdraw_exchange | 互选组合本人，live/paused | 无；撤销本人未完成的交流；若为当前组合则进入下一组 |
| remove | 本场运营或仍有控场权的主持 | 目标须在remove_ids；主持不能移出运营；target_id、非空reason |
| end | 有效控场者或本场运营，未结束 | 仅已完成交流发机会；接管后原主持不能结束 |
| cancel | 创建者，draft/scheduled | 无；取消，不发机会 |
| decline | 非运营本人，开场前 | 拒绝邀请，清理确认和签到，观看预约独立保留 |
| take_control / return_control | 本场运营 | 非空reason；接管不自动上台，交还须主持在场 |
| skip_round | 有效控场者，live，主嘉宾已离场/移出 | 非空reason，进入轮换，保留已完成交流 |

所有成功命令返回调用者新快照，revision 增加。同一对已完成交流后，即使另一轮反向互选，也不重新安排或发机会。后台超时本身不自动推进，主持仍须确认下一环节。

## 4. 快照与公共字段

下例展示无音视频业务演练中，主嘉宾在私密选择阶段的响应结构；members 为便于阅读仅示例一位，实际接口返回完整本场名单：

```json
{"id":1,"title":"周末受邀相亲场","scheduled_at":2000000000,"status":"live","revision":13,"server_time":2000001000,"notice":"本场仅演练业务，展示本人授权资料，不启用音视频。","round_index":0,"main_id":4,"phase":"choice","deadline":2000001060,"pause_remaining":0,"speaker_id":1,"media_epoch":0,"media_mode":"disabled","controller_id":1,"owner_id":13,"main_order":[4,8,5,9],"can_edit":false,"can_read_actions":false,"members":[{"user_id":8,"role":"guest","group":"female","seat":1,"display_name":"本场称呼","introduction":"本人授权公开的介绍","attendance":"onstage","on_stage":true,"hand":false,"light_target":null,"special_target":null,"invitation":"accepted","checked_in":true,"removed":false}],"me":{"user_id":4,"role":"guest","accepted":true,"invitation":"accepted","reserved":false,"checked_in":true,"removed":false,"special_remaining":1,"selection":[8,9]},"allowed_actions":["check_in","choose","leave","reserve"],"allowed_targets":{"stage_ids":[],"speaker_ids":[],"remove_ids":[],"interest_ids":[],"choice_ids":[8,9,10,11]},"exchanges":[]}
```

`me.selection`仅本人；工作人员不能读取单方名单。`allowed_actions`按角色、阶段、资格、时间计算当前能力，`allowed_targets`给出对象范围，提交时仍核验版本。示例没有公开亮灯，故只提供选择等当时可用动作；不可照抄为其他角色的固定权限。`media_epoch`在trtc变化时须重取凭证；disabled的on_stage是逻辑席位，不代表真实发布或设备检测通过，没有假媒体房间或凭证。

| 模型/字段 | 含义 |
| --- | --- |
| SessionSummary.id/title/scheduled_at/status/role | 场次 ID、标题、排期、状态及调用者本场角色 |
| SessionSummary.media_mode / LiveResults.media_mode | 场次创建时固定的disabled/trtc，大厅及结果均可准确标识 |
| LiveList.items/can_manage | 本人场次列表；是否具有创建所需 admin 角色 |
| LiveResources.ready/missing/provider | 当前模式的配置准备状态、缺失名称、固定 tencent-trtc；不是服务健康检查或验收证明 |
| LiveResources.business_ready/business_missing、media_ready/media_missing | 分开报告业务与媒体缺项；disabled不因云缺项阻断业务，media_ready仍为false |
| Exchange.main_id/candidate_id | 互选双方 ID；仅截止后出现 |
| Exchange.status | queued 待交流、active 当前、completed 已完成、withdrawn 退出 |
| Exchange.started_at/ended_at | 实际开始/完成或退出的 Unix 秒，尚未发生为 null |
| LiveResults.session_ended/items | 是否整场已结束及本人专属机会，场前为空数组 |
| LiveOpportunity.id/session_id/peer_id/peer_name | 机会、场次、对方 ID 及本场授权称呼 |
| LiveOpportunity.expires_at/application_id/status | 发起有效期、已用申请 ID 或 null；available/used/expired |
| LiveReport.id/target_id/reason/status/resolution | 举报 ID、被举报账号、原因、open/resolved、处置结论（未处理为空） |

LiveSnapshot、PublicMember 和 LiveMe 每个字段的类型、含义及空值规则均在 [字段字典](live-v2-fields.md) 中直接由 Pydantic 导出，维护时运行 `scripts/export_live_api_docs.py`。

列表与空数据示例：

```json
{"items":[],"can_manage":false}
```

```json
{"ready":false,"missing":["LIVE_SDK_APP_ID","LIVE_SDK_SECRET"],"provider":"tencent-trtc","media_mode":"trtc","business_ready":true,"business_missing":[],"media_ready":false,"media_missing":["LIVE_SDK_APP_ID","LIVE_SDK_SECRET"]}
```

```json
{"items":[],"session_ended":false,"media_mode":"disabled"}
```

## 5. 媒体凭证

`POST /api/v1/live/v2/sessions/1/credentials` 无请求体。disabled明确409“当前环境未启用音视频”，以下凭证只适用trtc：已签到未离场/移出、有效媒体舞台、相关资源完整。首次请求可能启动云混流。云签名均在服务端，前端不可自己构造。

```json
{"mode":"rtc","sdk_app_id":1400000000,"room_id":123456,"user_id":"u4","user_sig":"<短时凭证>","private_map_key":"<房间绑定短时票据>","publish":true,"playback_url":"","expires_at":2000001300,"media_epoch":1}
```

`mode` 为 rtc/cdn。sdk_app_id/room_id/user_id 分别是腾讯 SDK 应用、当前数值房间和服务器生成的用户串；user_sig/private_map_key 是 300 秒凭证；publish 表示本次可发布；expires_at 为凭证到期；media_epoch 对应当前快照。候场嘉宾也用 RTC，但 publish=false 且票据不含发布位。

```json
{"mode":"cdn","sdk_app_id":0,"room_id":0,"user_id":"","user_sig":"","private_map_key":"","publish":false,"playback_url":"https://play.example.test/live/xsa_1_123456.flv?txSecret=<签名>&txTime=<截止>","expires_at":2000001060,"media_epoch":1}
```

观众只使用 playback_url，其他 RTC 字段为空/0。播放签名有效期 60 秒，前端短时刷新。不能记录票据全文或将其作为公共场次信息广播；不得把媒体连接成功等同于用户授权留存。

独立运营同样只取得CDN观看地址，不获取RTC发布凭证，不参加11位互动人员的设备签到；仍须等到有效媒体房间及配置就绪。该契约仅做源码测试，未宣称真实云播放通过。

## 6. 实时事件

`wss://api.example.test/api/v1/live/v2/sessions/1/events`，微信 Socket Header 携带同一 Bearer token。只有场内未移出成员可订阅。服务端持续复核会话和成员资格，不接受 WebSocket 业务命令；命令统一走 HTTP。

```json
{"type":"snapshot","snapshot":{"id":1,"revision":13,"me":{"user_id":4,"selection":[8,9]}}}
```

上例为外层事件示意，实际 snapshot 完整结构与第 4 节相同。心跳示例：

```json
{"type":"heartbeat","server_time":2000001000}
```

快照按调用者过滤；Redis 只传修订号。登录失效关闭 4401，资格失效关闭 4403，Redis 不可用关闭 1013；握手前失败可能体现为握手被拒而非 close 帧。客户端断线重取快照；当前页面另每 5 秒刷新，不自动重放动作。在线记录 TTL 30 秒，心跳约 10 秒。

## 7. 举报与处置

```http
POST /api/v1/live/v2/sessions/1/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{"target_id":8,"reason":"本场发言中出现不适内容，请核实。"}
```

target_id 为本场成员，reason 为 2—500 字符。成功 201：

```json
{"id":2,"target_id":8,"reason":"本场发言中出现不适内容，请核实。","status":"open","resolution":""}
```

工作人员 GET reports 返回此对象数组；无数据 `[]`。`POST /api/v1/live/v2/sessions/1/reports/2/resolve` 请求 `{"reason":"已核实并提醒当事人遵守场次规则。"}`，2—500 字符；响应相同 id/target_id/reason，status=resolved、resolution=所填结论。举报者身份不向被举报者或场次广播。场内移出是独立 remove 命令，需要明确原因，不因为举报自动移出。

## 8. 场后免费申请（兼容新增）

`GET /api/v1/live/v2/sessions/1/results` 示例：

```json
{"session_ended":true,"media_mode":"disabled","items":[{"id":7,"session_id":1,"peer_id":8,"peer_name":"本场称呼","expires_at":2000260000,"application_id":null,"status":"available"}]}
```

用户手动确认后调用既有接口：

```http
POST /api/v1/discovery/applications/8 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{"message":"愿意在场后继续认识。","live_opportunity_id":7}
```

不传 live_opportunity_id 保持既有日常额度申请；传入时必须是这双方的有效机会。每场每对共享一次，整场结束后 72 小时有效。发送后的答复期限沿用现有 48 小时。既有 ApplicationResponse 全字段见字段字典；新增 `live_opportunity_id`（可空，所属专属机会 ID）。原有 id/from_user_id/to_user_id/status/message/时间等语义不变。

成功响应示例（时间沿用既有申请接口的 ISO 8601 格式，不改为直播的 Unix 秒）：

```json
{"id":16,"from_user_id":4,"to_user_id":8,"message":"愿意在场后继续认识。","status":0,"expire_at":"2026-09-12T10:00:00","created_at":"2026-09-10T10:00:00","live_opportunity_id":7}
```

status=0 待处理、1 同意、2 拒绝、3 过期；expire_at 可空，created_at 为创建时间，id 为既有申请 ID。message 是留言，可空，长度沿用 ApplicationCreateRequest 的上限，见字段字典。

同机会重复/双方同时请求返回同一份原申请，不自动创建反向申请或接受；拒绝后同一机会只返回拒绝状态，不恢复机会，不退日常次数。无机会 ID 的原路径不受影响。消息列表额外提供 `liveOpportunityId` 和 `sourceText`（直播来源固定“直播场后专属免费申请”，非直播为空），保留原响应字段。

## 9. 错误契约

业务拒绝使用原项目 HTTPException：`{"detail":"可展示的原因"}`；输入错误 422 使用 FastAPI 结构化 detail 数组。没有新增并行错误码体系。

| HTTP 状态 | 条件 | 前端处理 |
| --- | --- | --- |
| 401 | 未登录、令牌/会话失效 | 走原登录失效流程，清理本场媒体，不重放动作 |
| 403 | 越权、未实名/未成年/未绑手机、未签到、被移出、非本人机会 | 显示原因，不靠界面隐藏继续请求 |
| 404 | 场次不存在或未受邀、举报记录不存在 | 隐藏场次敏感信息，返回列表 |
| 409 | 修订冲突、重复键不同内容、截止/暂停/阶段不允许、特别心动已用、舞台满、已有待处理申请 | 拉新快照，要求重新确认；不自动重试选择 |
| 410 | 未使用机会已过发起期限 | 标记已过期，不扣日常额度 |
| 422 | 字段、名单、重复/越界选择、处置原因等非法 | 按字段/原因修正输入 |
| 503 | 配置/权限核验标记缺失、腾讯云调用未成功 | 展示资源未就绪或可重试错误，禁止假成功 |

示例：`{"detail":"场次已更新，请刷新后重新确认操作"}`。真实云错误只记录动作及错误码，不向客户端透露 SDK 返回内容或密钥。非直播申请原有状态码与门槛保持不变，参阅原 discovery 接口文档。

## 10. 变更记录

2026-09-27：统一场次权限与对象范围、独立运营和唯一控场者，新增无媒体测试模式、搜索选人、版本化名单编辑、邀请拒绝、接管／交还／跳轮、站内通知和脱敏日志；大厅、房间与结果均返回持久化媒体模式。实际验证层级见前端工作区 `docs/verification/live-business/README.md`。

2026-09-10：新增直播路由、明确 Pydantic/UTS 契约、四轮状态、过滤快照、资源/媒体、举报和机会；discovery 申请可选新增 live_opportunity_id，ApplicationResponse 同名字段，消息新增可选 liveOpportunityId/sourceText。新增均兼容原调用，不要求旧客户端传直播字段，不迁移既有申请记录。正式云资源及真机验收另见 [部署说明](../live-trial.md)。
