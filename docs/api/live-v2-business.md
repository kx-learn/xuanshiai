# 直播 v2 — 真实业务增量契约

2026-10-02 上游兼容调整：本模块使用 `/api/v1/live/v2`、`live_v2_*` 表和 `live:v2:*` Redis 频道。上游原有直播接口、数据表及 `TENCENT_LIVE_*` 配置保留不变；本次未迁移或修改正式数据。历史验收不能替代整合版验收，最新结果见 [整合记录]( ../upstream-integration-20261002.md )。

本页补充 live-v2.md，字段明细与实际 OpenAPI 由 export_live_api_docs.py 同步生成。统一前缀 `/api/v1`，HTTP JSON；需 `Authorization: Bearer <正常登录获得的访问令牌>`。无媒体演练不使用客户端伪造身份，不修改正式库。

## 新增接口

| 方法及路径 | 权限 | 请求与成功响应 |
| --- | --- | --- |
| GET /live/accounts?q=林&page=1&page_size=20 | 当前平台管理员；只用于名单选人 | 无请求体。q 为 1—64 字符昵称子串或精确账号 ID；page ≥1，page_size 1—50。返回 items、page、page_size、total、has_more |
| PUT /live/sessions/{sid} | 本场 owner，未开场 | 完整 LiveCreateRequest + expected_revision ≥0，返回 LiveSnapshot。sid 为正整数；服务器锁行同时更新成员索引和状态 |
| GET /live/sessions/{sid}/actions?page=1&page_size=20 | 本场运营、主持、红娘 | 无请求体；分页同上。记录字段 id、user_id、action、revision、outcome、target_id、reason、created_at（Unix秒） |

选人 items 每项为 user_id（正整数）、nickname（基本昵称）、gender（1男/2女/其他未完善）、eligible（布尔）、missing（资格缺项名称数组）。不含手机号、证件、密钥或未授权个人介绍。例如：`{"items":[{"user_id":4,"nickname":"林屿","gender":1,"eligible":true,"missing":[]}],"page":1,"page_size":20,"total":1,"has_more":false}`。空查询结果 items=[]、total=0、has_more=false。q 为空、page=0、page_size=51 均为 422。

更新示例：`{"title":"受邀业务演练","scheduled_at":1800000000,"host_id":1,"matchmaker_ids":[2,3],"male_ids":[4,5,6,7],"female_ids":[8,9,10,11],"main_order":[4,8,5,9],"spectator_ids":[12],"notice":"仅在测试环境展示本人授权资料，未启用音视频。","expected_revision":3}`。四轮名单、长度及唯一约束沿用创建模型；运营不得出现在任何席位。重复提交旧版本返回409，不静默合并。身份、席位、主嘉宾安排改变者重新确认签到；时间/notice 改变全员重新确认；仅改标题不清空确认。

## 命令和快照变化

原 POST /live/sessions/{sid}/commands 新增 decline、take_control、return_control、skip_round。接管、交还、跳轮携带非空 reason（≤255字）；不添加客户端 role 或 actor 参数。权限由会话登录账号决定。唯一 controller_id 是场次权限，不修改永久身份，接管不自动上台。

快照新增 media_mode（disabled/trtc）、owner_id、controller_id、main_order、can_edit、can_read_actions、allowed_targets（stage_ids/speaker_ids/remove_ids/interest_ids/choice_ids）。me 和 members 新增 invitation（pending/accepted/declined）；members 增加 checked_in、removed。allowed_actions 现在是当前状态下有效动作，仍需请求时核验版本和时间，不是仅角色静态权限。

列表项SessionSummary及本人LiveResults同样返回media_mode。被移出者不能回房间，但仍可访问本人结果和已经完成交流获得的机会；不会因此绕过原申请的账号与关系限制。

GET /live/resources 保留 ready/missing，新增 business_ready/business_missing、media_ready/media_missing、media_mode。business_ready 只表示环境配置允许业务运行，不代表数据库或 Redis 已实测。disabled 时 ready 不依赖云密钥，但 media_ready=false。POST credentials 返回409 `{"detail":"当前环境未启用音视频"}`；不产生空签名或假推流地址。

## 错误、隐私和兼容

401 会话无效，重新登录；403 无角色/对象权限、已移出或实名等资格不满足；404 未受邀/资源不存在；409 旧版本、状态冲突、截止或媒体关闭，刷新后由本人重新确认；422 参数、名单或原因不合法，修正输入；503 TRTC 资源缺项，交由工作人员配置。错误沿用 `{"detail":"原因"}`，Pydantic 参数错误 detail 为数组。

幂等命令继续以 command_id 唯一，同键不同内容409。同键重试返回当前本人快照；已记录拒绝的控场命令重试继续返回原拒绝，不变成成功。操作日志仅白名单输出，不包含 targets、selection、签名和密钥。共享 Redis 只发布版本号，HTTP/WS 快照仅返回本人选择及截止后的互选。

旧场次 media_mode 缺省 trtc，controller 缺省原主持，invitation 按 accepted 推导；不重算已结束的结果和机会。旧式运营兼任席位的未开场场次须先更正名单。旧客户端需升级才能展示新的控场和对象范围；旧按钮不得绕过服务端校验。不删旧接口。
