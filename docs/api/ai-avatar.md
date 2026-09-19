# AI 分身接口

## 1. 统一约定

- 基础路径：`/api/v1/ai-avatars`
- 认证：全部接口要求 `Authorization: Bearer <access_token>`。
- 数据格式：请求和响应均为 `application/json`。
- 隐私：公开资料上下文由后端按目标用户当前隐私设置生成。客户端不得提交或覆盖资料上下文。
- 隔离：会话保存在 `ai_avatar_conversation`、`ai_avatar_message`，不进入真人消息列表、未读数或通知。
- 模型：后端调用 OpenAI 兼容的 `/chat/completions`，不会向客户端返回供应商密钥。
- 限额：发送消息默认每位用户每日 20 次，以 UTC 自然日重置，实际值由 `AI_AVATAR_DAILY_LIMIT` 配置。
- 主人补充：每个访客问题都会进入分身所属用户的待回答列表。主人补充回答后，原访客下次读取会话可看到来源为 `owner-answer` 的消息；这不是真人聊天，不产生通知或开放联系方式。

### 1.1 公共消息字段

| 字段 | 类型 | 必返 | 空值 | 含义 | 示例 |
| --- | --- | --- | --- | --- | --- |
| `id` | integer | 是 | 否 | 消息 ID；欢迎消息固定为 `0` | `12` |
| `type` | string | 是 | 否 | 固定为 `text` | `text` |
| `content` | string | 是 | 否 | 用户问题、AI 回答或欢迎语 | `Ta 喜欢徒步` |
| `time` | integer | 是 | 否 | Unix 毫秒时间戳 | `1786675200000` |
| `showTime` | boolean | 是 | 否 | 前端是否显示独立时间标签 | `false` |
| `isMine` | boolean | 是 | 否 | 是否为当前访问者发送 | `false` |
| `avatar` | string/null | 是 | 可空 | AI 消息头像；用户消息可空 | `/storage/uploads/a.webp` |
| `source` | string | 是 | 否 | `user`、`real-ai`、`owner-answer` 或 `system` | `real-ai` |
| `category` | string | 是 | 否 | `basic`、`interest`、`expectation`、`platform`、`general` | `interest` |
| `handoffRequired` | boolean | 是 | 否 | 当前固定 `false` | `false` |
| `handoffStatus` | string | 是 | 否 | 当前固定 `not_requested` | `not_requested` |

### 1.2 公共错误

| HTTP | 触发条件 | 响应示例 | 前端处理 |
| --- | --- | --- | --- |
| `401` | Token 缺失、过期或会话失效 | `{"detail":"请先登录"}` | 进入登录流程 |
| `403` | 自己的分身、双方任一方拉黑、资料不可见、认证或会员条件不满足 | `{"detail":"该用户当前未公开个人资料"}` | 关闭入口并提示原因 |
| `404` | 目标用户不存在或账号不可用 | `{"detail":"用户不存在"}` | 返回上一页并刷新用户列表 |
| `422` | 路径或请求体校验失败、问题命中拒绝规则 | `{"detail":[{"msg":"String should have at most 300 characters"}]}` | 保留输入并提示修改 |
| `429` | 当日 AI 提问达到限额 | `{"detail":"今日 AI 分身提问已达 20 次上限"}` | 禁止重复提交，次日重试 |
| `429` | 供应商临时限流（非每日额度耗尽） | `{"detail":"AI 服务当前请求较多，请稍后重试"}` | 稍后重试；若有 `Retry-After`，至少等待指定秒数，不按每日额度耗尽处理 |
| `503` | AI 未配置、供应商非 429 异常或 Redis 在生产环境不可用 | `{"detail":"AI 服务暂时不可用，请稍后重试"}` | 展示重试，不回退 Mock |
| `504` | AI 供应商请求超时 | `{"detail":"AI 回答超时，请稍后重试"}` | 保留输入并允许重试 |

## 2. 读取 AI 分身公开资料

**基本信息**：读取当前访问者有权看见的资料快照。URL `GET /api/v1/ai-avatars/{target_user_id}/profile`；需登录；成功状态 `200`。

**请求参数**：

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 业务含义 | 合法/非法示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `target_user_id` | path | integer | 是 | 无 | `>=1`，且不能等于当前用户 | AI 分身所属用户 ID | `2` / `0` |
| `Authorization` | header | string | 是 | 无 | Bearer Token | 当前访问者身份 | `Bearer ey...` / 缺失 |

**请求体示例**：无请求体。

```http
GET /api/v1/ai-avatars/2/profile HTTP/1.1
Authorization: Bearer <access-token>
```

**返回参数**：

| 字段 | 类型 | 必返 | 空值 | 业务含义 | 示例 |
| --- | --- | --- | --- | --- | --- |
| `id` | integer | 是 | 否 | 目标用户 ID | `2` |
| `name` | string | 是 | 否 | 公开昵称，缺失时为 `Ta` | `林夏` |
| `avatar` | string/null | 是 | 可空 | 公开头像 URL | `/storage/uploads/2.webp` |
| `age` | integer/null | 是 | 可空 | 由生日计算的年龄 | `28` |
| `city` | string/null | 是 | 可空 | 公开城市或城市编码 | `南京` |
| `job` | string/null | 是 | 可空 | 未隐藏且有权限查看的职业 | `产品经理` |
| `education` | string/null | 是 | 可空 | 未隐藏且有权限查看的学历标签 | `本科` |
| `tags` | string[] | 是 | 空数组 | 公开兴趣、性格和资料标签 | `["徒步"]` |
| `bio` | string/null | 是 | 可空 | 公开自我介绍 | `喜欢自然和阅读` |
| `interests` | string[] | 是 | 空数组 | 公开兴趣摘要 | `["徒步","摄影"]` |
| `expectations` | string[] | 是 | 空数组 | 当前访问者有权查看的择偶期待 | `["认真稳定"]` |
| `allowExpectations` | boolean | 是 | 否 | 是否允许展示择偶期待 | `true` |
| `restricted` | boolean | 是 | 否 | 详细资料是否因会员隐私受限 | `false` |
| `aiMode` | string | 是 | 否 | 固定为 `real` | `real` |

**返回示例**：

```json
{"id":2,"name":"林夏","avatar":null,"age":28,"city":"南京","job":"产品经理","education":"本科","tags":["徒步"],"bio":"喜欢自然和阅读","interests":["徒步","摄影"],"expectations":["认真稳定"],"allowExpectations":true,"restricted":false,"aiMode":"real"}
```

**使用方法与业务规则**：进入聊天页前调用。后端检查账号状态、拉黑关系、`show_profile`、`who_can_see_me`、`match_status`、会员与实名认证可见条件。本接口不扣普通主页浏览次数。隐私变化立即生效，旧客户端不得使用本地资料替代失败响应。

**错误**：见 1.2。`403` 时不得继续调用消息接口。接口幂等，不创建会话，不产生通知。

**兼容性**：新增接口，不影响 `/users/{id}/profile`。响应新增字段时旧客户端应忽略未知字段。

## 3. 读取 AI 分身聊天记录

**基本信息**：读取当前用户与指定分身的独立历史。URL `GET /api/v1/ai-avatars/{target_user_id}/conversations`；需登录；成功状态 `200`。

**请求参数**：`target_user_id` 与 `Authorization` 的类型、校验和含义同第 2 节。非法示例为 `target_user_id=-1`。无 query，无请求体。

```http
GET /api/v1/ai-avatars/2/conversations HTTP/1.1
Authorization: Bearer <access-token>
```

**返回参数**：

| 字段 | 类型 | 必返 | 空值 | 业务含义 | 示例 |
| --- | --- | --- | --- | --- | --- |
| `targetUserId` | integer | 是 | 否 | 目标用户 ID | `2` |
| `messages` | object[] | 是 | 至少含欢迎消息 | 独立 AI 消息数组；内部字段见 1.1 | `[{"id":0,...}]` |

**返回示例**：

```json
{"targetUserId":2,"messages":[{"id":0,"type":"text","content":"你好，我是林夏的 AI 分身。这里只参考 Ta 当前对你公开的资料，不是真人聊天，Ta 也不会收到提醒。你可以问我基本资料、兴趣爱好、择偶标准或平台规则。","time":1786675200000,"showTime":false,"isMine":false,"avatar":null,"source":"system","category":"general","handoffRequired":false,"handoffStatus":"not_requested"}]}
```

**使用方法与业务规则**：成功加载公开资料后调用。没有数据库历史时仍返回一条临时欢迎消息；欢迎消息 ID 为 `0`，不会存入数据库。最多返回当前会话前 200 条数据库消息。历史只对发起者可见，不产生已读或未读状态。

**错误**：见 1.2。接口幂等，不扣 AI 提问额度。

**兼容性**：新增接口；AI 历史不会出现在任何真人会话接口中。

## 4. 向 AI 分身发送问题

**基本信息**：调用真实模型并在成功后保存问题与回答。URL `POST /api/v1/ai-avatars/{target_user_id}/messages`；需登录；`Content-Type: application/json`；成功状态 `200`。

**请求参数**：

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 业务含义 | 合法/非法示例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `target_user_id` | path | integer | 是 | 无 | `>=1`，不能为本人 | 分身所属用户 ID | `2` / `0` |
| `Authorization` | header | string | 是 | 无 | Bearer Token | 当前访问者身份 | `Bearer ey...` / 缺失 |
| `Idempotency-Key` | header | string | 否 | 无 | 1-128 字符 | 同一用户重试同一发送请求的幂等键 | `ai-avatar-...` / 超过 128 字符 |
| `content` | body | string | 是 | 无 | 去首尾和重复空白后 1-300 字符 | 用户问题 | `Ta 喜欢什么？` / 301 字符 |

**请求体示例**：

```http
POST /api/v1/ai-avatars/2/messages HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: ai-avatar-20260905-001

{"content":"Ta 喜欢什么？"}
```

非法请求体：`{"content":""}`。

**返回参数**：

| 字段 | 类型 | 必返 | 空值 | 业务含义 | 示例 |
| --- | --- | --- | --- | --- | --- |
| `messages` | object[] | 是 | 否 | 保存后的完整 AI 会话；内部字段见 1.1 | `[{"id":0,...}]` |
| `result.reply` | string | 是 | 否 | 本次模型回答 | `Ta 的公开资料提到喜欢徒步。` |
| `result.category` | string | 是 | 否 | 本次问题分类，枚举见 1.1 | `interest` |
| `result.source` | string | 是 | 否 | 固定 `real-ai` | `real-ai` |
| `result.handoffRequired` | boolean | 是 | 否 | 当前固定 `false` | `false` |
| `result.handoffStatus` | string | 是 | 否 | 当前固定 `not_requested` | `not_requested` |

**返回示例**：

```json
{"messages":[{"id":0,"type":"text","content":"欢迎语","time":1786675200000,"showTime":false,"isMine":false,"avatar":null,"source":"system","category":"general","handoffRequired":false,"handoffStatus":"not_requested"},{"id":11,"type":"text","content":"Ta 喜欢什么？","time":1786675201000,"showTime":false,"isMine":true,"avatar":null,"source":"user","category":"interest","handoffRequired":false,"handoffStatus":"not_requested"},{"id":12,"type":"text","content":"Ta 的公开资料提到喜欢徒步，这是 AI 回答。","time":1786675202000,"showTime":false,"isMine":false,"avatar":null,"source":"real-ai","category":"interest","handoffRequired":false,"handoffStatus":"not_requested"}],"result":{"reply":"Ta 的公开资料提到喜欢徒步，这是 AI 回答。","category":"interest","source":"real-ai","handoffRequired":false,"handoffStatus":"not_requested"}}
```

**使用方法与业务规则**：先调用资料和历史接口。服务端重新检查隐私，读取最近 `AI_MAX_CONTEXT_MESSAGES` 条历史，调用供应商，过滤输出后再一次性保存用户问题和 AI 回答，同时向主人待回答列表记录问题。供应商或数据库失败时不保存本轮消息并返还本次额度。客户端应为一次用户发送生成一个 `Idempotency-Key`；同一用户、相同请求键和相同请求体会复用首次成功响应。相同键对应不同请求体返回 `409`，处理中再次发送相同键也返回 `409`。

**频率与并发**：每位访问者共享每日额度，不按目标分别计算。数据库会话按访问者与目标唯一。客户端发送期间仍应禁用重复提交；网络重试必须复用同一个 `Idempotency-Key`，而新的用户发送必须生成新键。

**错误**：除 1.2 外，AI 未配置返回 `503`；超时返回 `504`；额度不足或供应商临时限流返回 `429`（区别见 1.2）；幂等键与请求体不一致或同键请求仍在处理中返回 `409`。错误响应不会包含供应商响应体、密钥或内部 Prompt。

**兼容性**：新增接口。当前为非流式响应，未来增加流式接口时保留本接口。

## 5. 管理我的 AI 分身问答

**基本信息**：读取和维护当前登录用户的 AI 分身待回答问题及可复用回答。所有接口均只操作当前用户自己的数据，URL 分别为 `GET /api/v1/ai-avatars/me/dashboard`、`POST /api/v1/ai-avatars/me/questions`、`POST /api/v1/ai-avatars/me/questions/{question_id}/answer`、`DELETE /api/v1/ai-avatars/me/questions/{question_id}` 与 `DELETE /api/v1/ai-avatars/me/answers/{answer_id}`。

**读取返回**：`pending_questions` 与 `answers` 都是数组；单项含 `id`、`question`、`answer`、`status`、`created_at`、`answered_at`。待回答项的 `answer` 和 `answered_at` 为 `null`，状态为 `pending`；已回答项状态为 `answered`。

**新增可复用回答**：`POST /me/questions` 请求体为 `{"question":"Ta 喜欢什么？","answer":"喜欢徒步和阅读。"}`。问题长度为 1-300，回答长度为 1-500；相同归一化问题会更新为最新回答。

**回答或删除待回答项**：回答接口请求体为 `{"answer":"..."}`，回答长度为 1-500。删除只影响待回答项；删除已回答的可复用项使用 `/me/answers/{answer_id}`。不存在、已删除或不属于当前用户的记录均返回 `404`。

**隐私与会话**：主人回答仅用作 AI 分身公开问答的补充，不会创建真人聊天、通知或联系方式交换。访客重新读取自己的 AI 分身会话时，才会看到来源为 `owner-answer` 的补充消息。

## 6. 清空 AI 分身聊天记录

**基本信息**：删除当前访问者与目标分身的独立会话。URL `DELETE /api/v1/ai-avatars/{target_user_id}/conversations`；需登录；成功状态 `200`。

**请求参数**：`target_user_id` 与 `Authorization` 同第 2 节；无 query，无请求体。非法示例：`target_user_id=0`。

```http
DELETE /api/v1/ai-avatars/2/conversations HTTP/1.1
Authorization: Bearer <access-token>
```

**返回参数**：

| 字段 | 类型 | 必返 | 空值 | 业务含义 | 示例 |
| --- | --- | --- | --- | --- | --- |
| `targetUserId` | integer | 是 | 否 | 被清空会话的目标用户 ID | `2` |
| `deleted` | boolean | 是 | 否 | 删除操作已完成；无历史时也为 `true` | `true` |

**返回示例**：`{"targetUserId":2,"deleted":true}`。

**使用方法与业务规则**：用户确认后调用。删除会话会级联删除其 AI 消息；不会删除真人消息、通知或目标用户资料。重复调用结果相同，不扣 AI 额度。删除后重新读取历史只返回欢迎消息。

**错误**：见 1.2。只有当前访问者自己的会话可被删除，不接受会话 ID，避免越权删除。

**兼容性**：新增接口，无旧数据迁移；原前端本地 Mock 历史保留在独立命名空间，不会上传到后端。

## 7. 本地与部署配置

在未提交的 `.env` 中配置：

```env
AI_AVATAR_PROVIDER=openai_compatible
AI_AVATAR_BASE_URL=https://provider.example/v1
AI_AVATAR_API_KEY=YOUR_AI_AVATAR_API_KEY
AI_AVATAR_MODEL=YOUR_AI_AVATAR_MODEL
AI_AVATAR_TIMEOUT_SECONDS=20
AI_AVATAR_MAX_OUTPUT_TOKENS=500
AI_AVATAR_MAX_CONTEXT_MESSAGES=12
AI_AVATAR_DAILY_LIMIT=20
```

本地无密钥的兼容服务可不设置 `AI_AVATAR_API_KEY`。staging/production 强制 `AI_AVATAR_BASE_URL` 使用 HTTPS。修改配置后需要重启 FastAPI。

## 8. 变更记录

### 2026-09-19：供应商限流与旧会话表兼容

- **变更前**：供应商 HTTP 429 被统一映射为 503；文档中的 429 仅表示每日额度耗尽。
- **变更后**：发送消息接口将供应商 HTTP 429 映射为 429，提示“AI 服务当前请求较多，请稍后重试”。供应商返回纯数字秒数的 `Retry-After` 时透传该响应头；缺失、HTTP 日期或其他非数字格式不透传。其他供应商 HTTP 错误仍返回 503，超时仍返回 504。
- **影响范围**：仅 `/api/v1/ai-avatars/{target_user_id}/messages` 的供应商限流错误语义；请求体与成功响应不变，不修改其他 AI 功能的 provider、模型或密钥配置。客户端应结合错误提示区分每日额度与临时限流，不得仅凭 429 将所有失败都锁定到次日。
- **失败处理**：供应商限流不会写入本次用户/助手消息，服务端按既有异常路径回滚事务、尝试退还本次额度，并释放已建立的幂等占位。响应不包含供应商原始响应体或密钥。
- **客户端说明**：前端 AI 分身历史与发送请求等待上限为 60 秒；现有请求封装不暴露 `Retry-After` 给业务页面，因此本次不提供自动倒计时或自动重发。客户端超时不表示服务端一定未完成；应先重新读取历史，避免盲目重复发送。网关、后端模型超时仍需部署环境另行核对。
- **数据库兼容**：旧表同时具有 `owner_user_id`、`visitor_user_id` 时，插入会话补齐访问者参数；标准表分支不变。本次不新增表、不迁移或导出数据。
