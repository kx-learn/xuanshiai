# 直播 v2 试点接口字段字典

由实际 Pydantic/OpenAPI 生成；业务条件、权限和示例见 [live-v2.md](live-v2.md)。

## LiveAccountList

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| items | 是 | `{"items": {"$ref": "#/components/schemas/LiveAccount"}, "type": "array"}` |
| page | 是 | `{"type": "integer"}` |
| page_size | 是 | `{"type": "integer"}` |
| total | 是 | `{"type": "integer"}` |
| has_more | 是 | `{"type": "boolean"}` |

## LiveAccount

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| user_id | 是 | `{"type": "integer"}` |
| nickname | 是 | `{"type": "string"}` |
| gender | 是 | `{"type": "integer"}` |
| eligible | 是 | `{"type": "boolean"}` |
| missing | 是 | `{"items": {"type": "string"}, "type": "array", "description": "账号状态、成年、手机、实名等资格缺项，不返回敏感值"}` |

## HTTPValidationError

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| detail | 否 | `{"items": {"$ref": "#/components/schemas/ValidationError"}, "type": "array"}` |

## ValidationError

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| loc | 是 | `{"items": {"anyOf": [{"type": "string"}, {"type": "integer"}]}, "type": "array"}` |
| msg | 是 | `{"type": "string"}` |
| type | 是 | `{"type": "string"}` |
| input | 否 | `{}` |
| ctx | 否 | `{"type": "object"}` |

## LiveResources

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| ready | 是 | `{"type": "boolean"}` |
| missing | 是 | `{"items": {"type": "string"}, "type": "array"}` |
| provider | 否 | `{"type": "string", "const": "tencent-trtc", "default": "tencent-trtc"}` |
| media_mode | 否 | `{"type": "string", "enum": ["disabled", "trtc"], "default": "trtc"}` |
| business_ready | 否 | `{"type": "boolean", "description": "业务环境配置允许运行；不是数据库/Redis健康探测", "default": true}` |
| business_missing | 否 | `{"items": {"type": "string"}, "type": "array"}` |
| media_ready | 否 | `{"type": "boolean", "default": false}` |
| media_missing | 否 | `{"items": {"type": "string"}, "type": "array"}` |

## LiveList

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| items | 是 | `{"items": {"$ref": "#/components/schemas/SessionSummary"}, "type": "array"}` |
| can_manage | 是 | `{"type": "boolean"}` |

## SessionSummary

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| id | 是 | `{"type": "integer"}` |
| title | 是 | `{"type": "string"}` |
| scheduled_at | 是 | `{"type": "integer"}` |
| status | 是 | `{"type": "string"}` |
| role | 是 | `{"type": "string", "enum": ["host", "matchmaker", "guest", "spectator", "operator"]}` |
| media_mode | 否 | `{"type": "string", "enum": ["disabled", "trtc"], "default": "trtc"}` |

## LiveCreateRequest

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| title | 是 | `{"type": "string", "maxLength": 80, "minLength": 1, "description": "受邀场次标题"}` |
| scheduled_at | 是 | `{"type": "integer", "exclusiveMinimum": 0.0, "description": "计划开场 Unix 秒，UTC"}` |
| host_id | 是 | `{"type": "integer", "exclusiveMinimum": 0.0, "description": "唯一主持的现有账号 ID"}` |
| matchmaker_ids | 是 | `{"items": {"type": "integer"}, "type": "array", "maxItems": 2, "minItems": 2, "description": "两位红娘的现有账号 ID"}` |
| male_ids | 是 | `{"items": {"type": "integer"}, "type": "array", "maxItems": 4, "minItems": 4, "description": "四位男嘉宾 ID，数组顺序即席位顺序"}` |
| female_ids | 是 | `{"items": {"type": "integer"}, "type": "array", "maxItems": 4, "minItems": 4, "description": "四位女嘉宾 ID，数组顺序即席位顺序"}` |
| main_order | 是 | `{"items": {"type": "integer"}, "type": "array", "maxItems": 4, "minItems": 4, "description": "2 男 2 女主嘉宾顺序"}` |
| spectator_ids | 否 | `{"items": {"type": "integer"}, "type": "array", "maxItems": 20, "description": "受邀观众 ID，不获得上台或选择权"}` |
| notice | 是 | `{"type": "string", "maxLength": 2000, "minLength": 10, "description": "展示范围、音视频及必要审核留存告知"}` |

## LiveSnapshot

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| id | 是 | `{"type": "integer", "description": "场次 ID"}` |
| title | 是 | `{"type": "string", "description": "场次标题"}` |
| scheduled_at | 是 | `{"type": "integer", "description": "计划开场 Unix 秒，按本地时区展示"}` |
| status | 是 | `{"type": "string", "description": "draft/scheduled/live/paused/ended/cancelled"}` |
| revision | 是 | `{"type": "integer", "description": "单调递增业务版本，命令提交时必须携带"}` |
| server_time | 是 | `{"type": "integer", "description": "服务端当前 Unix 秒，用于校正倒计时"}` |
| notice | 是 | `{"type": "string", "description": "本场固定的展示、音视频和留存告知"}` |
| round_index | 是 | `{"type": "integer", "description": "当前轮次索引 0—3，显示时加一"}` |
| main_id | 是 | `{"type": "integer", "description": "当前主嘉宾账号 ID"}` |
| phase | 是 | `{"type": "string", "enum": ["intro", "question", "interest", "choice", "exchanges", "transition", "completed"], "description": "当前轮次环节"}` |
| deadline | 是 | `{"anyOf": [{"type": "integer"}, {"type": "null"}], "description": "环节截止 Unix 秒；未开始、暂停或整场结束为 null"}` |
| pause_remaining | 是 | `{"type": "integer", "description": "暂停时剩余秒数，恢复时重新计算 deadline"}` |
| speaker_id | 是 | `{"anyOf": [{"type": "integer"}, {"type": "null"}], "description": "主持安排的发言人 ID，无安排为 null"}` |
| media_epoch | 是 | `{"type": "integer", "description": "媒体房间代数；变化后重新获取凭证和连接"}` |
| media_mode | 否 | `{"type": "string", "enum": ["disabled", "trtc"], "default": "trtc"}` |
| controller_id | 是 | `{"type": "integer", "description": "唯一有效控场者；不改变公开主持角色"}` |
| owner_id | 是 | `{"type": "integer", "description": "本场运营账号；平台管理员不自动获得本场权限"}` |
| main_order | 是 | `{"items": {"type": "integer"}, "type": "array", "description": "已确定的四轮主嘉宾顺序"}` |
| can_edit | 是 | `{"type": "boolean", "description": "仅本场运营、未开场时为 true"}` |
| can_read_actions | 是 | `{"type": "boolean", "description": "本场运营、主持、红娘可读脱敏操作记录"}` |
| members | 是 | `{"items": {"$ref": "#/components/schemas/PublicMember"}, "type": "array", "description": "本场名单与授权公开资料，含已离场人员"}` |
| me | 是 | `{"$ref": "#/components/schemas/LiveMe", "description": "仅调用者自己的意愿与资格，不含他人单方选择"}` |
| allowed_actions | 是 | `{"items": {"type": "string", "enum": ["accept", "reserve", "check_in", "leave", "hand", "light", "special", "choose", "withdraw_exchange", "schedule", "start", "pause", "resume", "extend", "advance", "speaker", "stage", "remove", "end", "cancel", "rehearse", "decline", "take_control", "return_control", "skip_round"]}, "type": "array", "description": "按身份、状态和时间计算的动作；对象见 allowed_targets，提交仍须携带版本"}` |
| allowed_targets | 否 | `{"$ref": "#/components/schemas/LiveTargets"}` |
| exchanges | 是 | `{"items": {"$ref": "#/components/schemas/Exchange"}, "type": "array", "description": "仅本轮截止后互选成功的组合，按候选席位顺序"}` |

## PublicMember

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| user_id | 是 | `{"type": "integer", "description": "现有账号 ID，不是 TRTC 用户串"}` |
| role | 是 | `{"type": "string", "enum": ["host", "matchmaker", "guest", "spectator", "operator"], "description": "本场角色，不赋予其他场次的权限"}` |
| group | 是 | `{"type": "string", "description": "male/female/none；工作人员和观众为 none"}` |
| seat | 是 | `{"type": "integer", "description": "本组席位 1—4，工作人员及观众为 0"}` |
| display_name | 是 | `{"type": "string", "description": "本人已授权称呼，未确认时为受邀用户"}` |
| introduction | 是 | `{"type": "string", "description": "本人已授权公开的介绍，未确认时为空"}` |
| attendance | 是 | `{"type": "string", "description": "invited/reserved/checked_in/backstage/onstage/left；签到完成直接进入 backstage"}` |
| on_stage | 是 | `{"type": "boolean", "description": "是否拥有当前逻辑舞台席位；disabled不代表媒体发布或设备检测通过"}` |
| hand | 是 | `{"type": "boolean", "description": "是否正在举手等待主持安排"}` |
| light_target | 是 | `{"anyOf": [{"type": "integer"}, {"type": "null"}], "description": "本轮公开普通亮灯对象，无亮灯为 null"}` |
| special_target | 是 | `{"anyOf": [{"type": "integer"}, {"type": "null"}], "description": "本场公开特别心动对象，撤回或未使用为 null"}` |
| invitation | 否 | `{"type": "string", "enum": ["pending", "accepted", "declined"], "default": "pending"}` |
| checked_in | 否 | `{"type": "boolean", "default": false}` |
| removed | 否 | `{"type": "boolean", "default": false}` |

## LiveMe

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| user_id | 是 | `{"type": "integer", "description": "当前登录用户 ID"}` |
| role | 是 | `{"type": "string", "enum": ["host", "matchmaker", "guest", "spectator", "operator"], "description": "本场身份"}` |
| accepted | 是 | `{"type": "boolean", "description": "是否已确认本场告知及公开资料"}` |
| invitation | 否 | `{"type": "string", "enum": ["pending", "accepted", "declined"], "default": "pending"}` |
| reserved | 是 | `{"type": "boolean", "description": "是否预约观看，独立于嘉宾资格"}` |
| checked_in | 是 | `{"type": "boolean", "description": "是否已签到，离场后不自动撤销原签到记录"}` |
| removed | 是 | `{"type": "boolean", "description": "是否被工作人员移出；后续场次接口拒绝访问"}` |
| special_remaining | 是 | `{"type": "integer", "description": "特别心动剩余 0 或 1 次，撤回不恢复"}` |
| selection | 否 | `{"items": {"type": "integer"}, "type": "array", "description": "只返回调用者本人的选择"}` |

## LiveTargets

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| stage_ids | 否 | `{"items": {"type": "integer"}, "type": "array", "description": "可安排上下台的人"}` |
| speaker_ids | 否 | `{"items": {"type": "integer"}, "type": "array", "description": "本环节可安排发言的人"}` |
| remove_ids | 否 | `{"items": {"type": "integer"}, "type": "array", "description": "可移出的人；永不包含运营自己"}` |
| interest_ids | 否 | `{"items": {"type": "integer"}, "type": "array", "description": "本人可亮灯/特别心动的对象"}` |
| choice_ids | 否 | `{"items": {"type": "integer"}, "type": "array", "description": "本人可私密选择的有效对象"}` |

## Exchange

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| main_id | 是 | `{"type": "integer"}` |
| candidate_id | 是 | `{"type": "integer"}` |
| status | 否 | `{"type": "string", "enum": ["queued", "active", "completed", "withdrawn"], "default": "queued"}` |
| started_at | 否 | `{"anyOf": [{"type": "integer"}, {"type": "null"}]}` |
| ended_at | 否 | `{"anyOf": [{"type": "integer"}, {"type": "null"}]}` |

## LiveUpdateRequest

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| title | 是 | `{"type": "string", "maxLength": 80, "minLength": 1, "description": "受邀场次标题"}` |
| scheduled_at | 是 | `{"type": "integer", "exclusiveMinimum": 0.0, "description": "计划开场 Unix 秒，UTC"}` |
| host_id | 是 | `{"type": "integer", "exclusiveMinimum": 0.0, "description": "唯一主持的现有账号 ID"}` |
| matchmaker_ids | 是 | `{"items": {"type": "integer"}, "type": "array", "maxItems": 2, "minItems": 2, "description": "两位红娘的现有账号 ID"}` |
| male_ids | 是 | `{"items": {"type": "integer"}, "type": "array", "maxItems": 4, "minItems": 4, "description": "四位男嘉宾 ID，数组顺序即席位顺序"}` |
| female_ids | 是 | `{"items": {"type": "integer"}, "type": "array", "maxItems": 4, "minItems": 4, "description": "四位女嘉宾 ID，数组顺序即席位顺序"}` |
| main_order | 是 | `{"items": {"type": "integer"}, "type": "array", "maxItems": 4, "minItems": 4, "description": "2 男 2 女主嘉宾顺序"}` |
| spectator_ids | 否 | `{"items": {"type": "integer"}, "type": "array", "maxItems": 20, "description": "受邀观众 ID，不获得上台或选择权"}` |
| notice | 是 | `{"type": "string", "maxLength": 2000, "minLength": 10, "description": "展示范围、音视频及必要审核留存告知"}` |
| expected_revision | 是 | `{"type": "integer", "minimum": 0.0, "description": "编辑前快照版本；完整替换场前信息和名单"}` |

## LiveCommand

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| command_id | 是 | `{"type": "string", "maxLength": 64, "minLength": 8, "pattern": "^[a-zA-Z0-9_-]+$", "description": "单次操作幂等键，重试复用"}` |
| expected_revision | 是 | `{"type": "integer", "minimum": 0.0, "description": "操作前快照版本；冲突重新拉取，不自动重放"}` |
| action | 是 | `{"type": "string", "enum": ["accept", "reserve", "check_in", "leave", "hand", "light", "special", "choose", "withdraw_exchange", "schedule", "start", "pause", "resume", "extend", "advance", "speaker", "stage", "remove", "end", "cancel", "rehearse", "decline", "take_control", "return_control", "skip_round"], "description": "本人或工作人员动作；条件字段与权限见 live.md 命令表"}` |
| target_id | 否 | `{"anyOf": [{"type": "integer", "exclusiveMinimum": 0.0}, {"type": "null"}], "description": "亮灯、特别心动、发言、上下台或移出的对象账号 ID"}` |
| targets | 否 | `{"items": {"type": "integer"}, "type": "array", "maxItems": 3, "description": "主嘉宾私密选择的候选 ID，可提交空数组"}` |
| value | 否 | `{"type": "boolean", "description": "确认/开启为 true，撤回/暂不愿意/下台为 false", "default": false}` |
| seconds | 否 | `{"type": "integer", "maximum": 600.0, "minimum": 1.0, "description": "extend 延长秒数，仅截止前有效", "default": 60}` |
| display_name | 否 | `{"type": "string", "maxLength": 32, "description": "accept 时授权公开的称呼，不可为空白", "default": ""}` |
| introduction | 否 | `{"type": "string", "maxLength": 500, "description": "accept 时本人授权公开的介绍", "default": ""}` |
| consent_version | 否 | `{"anyOf": [{"type": "string", "const": "live-trial-v1"}, {"type": "null"}], "description": "accept 必须提交本期告知版本"}` |
| device_checked | 否 | `{"type": "boolean", "description": "仅 trtc 模式的非观众须完成设备检测；disabled 不记录为通过", "default": false}` |
| reason | 否 | `{"type": "string", "maxLength": 255, "description": "移出、接管、交还、跳轮须填写非空白原因", "default": ""}` |

## LiveActionList

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| items | 是 | `{"items": {"$ref": "#/components/schemas/LiveActionRecord"}, "type": "array"}` |
| page | 是 | `{"type": "integer"}` |
| page_size | 是 | `{"type": "integer"}` |
| total | 是 | `{"type": "integer"}` |
| has_more | 是 | `{"type": "boolean"}` |

## LiveActionRecord

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| id | 是 | `{"type": "integer"}` |
| user_id | 是 | `{"type": "integer"}` |
| action | 是 | `{"type": "string"}` |
| revision | 是 | `{"type": "integer"}` |
| outcome | 否 | `{"type": "string", "enum": ["accepted", "rejected"], "default": "accepted"}` |
| target_id | 否 | `{"anyOf": [{"type": "integer"}, {"type": "null"}]}` |
| reason | 否 | `{"type": "string", "default": ""}` |
| created_at | 是 | `{"type": "integer"}` |

## LiveCredentials

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| mode | 是 | `{"type": "string", "enum": ["rtc", "cdn"]}` |
| sdk_app_id | 否 | `{"type": "integer", "default": 0}` |
| room_id | 否 | `{"type": "integer", "default": 0}` |
| user_id | 否 | `{"type": "string", "default": ""}` |
| user_sig | 否 | `{"type": "string", "default": ""}` |
| private_map_key | 否 | `{"type": "string", "default": ""}` |
| publish | 否 | `{"type": "boolean", "default": false}` |
| playback_url | 否 | `{"type": "string", "default": ""}` |
| expires_at | 是 | `{"type": "integer"}` |
| media_epoch | 是 | `{"type": "integer"}` |

## LiveResults

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| items | 是 | `{"items": {"$ref": "#/components/schemas/LiveOpportunity"}, "type": "array"}` |
| session_ended | 是 | `{"type": "boolean"}` |
| media_mode | 否 | `{"type": "string", "enum": ["disabled", "trtc"], "default": "trtc"}` |

## LiveOpportunity

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| id | 是 | `{"type": "integer"}` |
| session_id | 是 | `{"type": "integer"}` |
| peer_id | 是 | `{"type": "integer"}` |
| peer_name | 是 | `{"type": "string"}` |
| expires_at | 是 | `{"type": "integer"}` |
| application_id | 是 | `{"anyOf": [{"type": "integer"}, {"type": "null"}]}` |
| status | 是 | `{"type": "string", "enum": ["available", "used", "expired"]}` |

## app__schemas__live_v2__LiveReportRequest

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| target_id | 是 | `{"type": "integer", "exclusiveMinimum": 0.0}` |
| reason | 是 | `{"type": "string", "maxLength": 500, "minLength": 2}` |

## LiveReport

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| id | 是 | `{"type": "integer"}` |
| target_id | 是 | `{"type": "integer"}` |
| reason | 是 | `{"type": "string"}` |
| status | 是 | `{"type": "string", "enum": ["open", "resolved"]}` |
| resolution | 否 | `{"type": "string", "default": ""}` |

## LiveReportResolution

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| reason | 是 | `{"type": "string", "maxLength": 500, "minLength": 2, "description": "工作人员处置结论，不向场次公开广播"}` |

## ApplicationCreateRequest

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| message | 否 | `{"anyOf": [{"type": "string", "maxLength": 255}, {"type": "null"}]}` |
| live_opportunity_id | 否 | `{"anyOf": [{"type": "integer", "exclusiveMinimum": 0.0}, {"type": "null"}], "description": "四轮直播 v2 完成交流后的共享免费申请机会"}` |

## ApplicationResponse

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| id | 是 | `{"type": "integer"}` |
| from_user_id | 是 | `{"type": "integer"}` |
| to_user_id | 是 | `{"type": "integer"}` |
| message | 是 | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| status | 是 | `{"type": "integer", "enum": [0, 1, 2, 3]}` |
| expire_at | 是 | `{"anyOf": [{"type": "string", "format": "date-time"}, {"type": "null"}]}` |
| created_at | 是 | `{"type": "string", "format": "date-time"}` |
| from_user | 否 | `{"anyOf": [{"$ref": "#/components/schemas/RelationUserSummary"}, {"type": "null"}]}` |
| to_user | 否 | `{"anyOf": [{"$ref": "#/components/schemas/RelationUserSummary"}, {"type": "null"}]}` |
| live_opportunity_id | 否 | `{"anyOf": [{"type": "integer"}, {"type": "null"}]}` |

## RelationUserSummary

| 字段 | 必填/必返 | 类型、范围、默认值与含义 |
| --- | --- | --- |
| user_id | 是 | `{"type": "integer"}` |
| nickname | 是 | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| avatar | 是 | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
| age | 是 | `{"anyOf": [{"type": "integer"}, {"type": "null"}]}` |
| city_code | 是 | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` |
