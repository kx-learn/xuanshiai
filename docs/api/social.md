# 关系、聊天与安全接口

统一前缀：`/api/v1`。所有接口需要：

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

除查看个人资料和资料编辑外，本组社交接口要求账号已绑定手机号。聊天还要求双方存在有效匹配关系，且没有互相拉黑。

## 喜欢、关注和匹配

### `PUT /users/{target_id}/like`

喜欢用户。双方互相喜欢时自动创建双方匹配记录和聊天会话，并向双方写入匹配通知。

### `DELETE /users/{target_id}/like`

取消喜欢。若双方已经匹配，同时将匹配状态改为取消。

### `PUT /users/{target_id}/follow` / `DELETE /users/{target_id}/follow`

关注或取消关注用户。关注关系不产生匹配。

### 关系列表

- `GET /relations/likes`：我喜欢的人。
- `GET /relations/liked-by`：喜欢我的人。
- `GET /relations/following`：我的关注。
- `GET /relations/followers`：我的粉丝。
- `GET /relations/matches`：我的匹配。
- `DELETE /relations/matches/{target_id}`：取消匹配。

列表支持 `page` 和 `page_size`，每页最多 50 条。

## 聊天

### `GET /chat/sessions`

返回当前用户的聊天会话和未读数。

### `GET /chat/sessions/{session_id}/messages`

分页返回聊天记录，支持 `page`、`page_size`（每页最多 50 条）。

### `POST /chat/sessions/{session_id}/messages`

文本消息：

```json
{"type": 1, "content": "你好"}
```

媒体消息需要提供已上传的资源地址：

```json
{"type": 2, "media_url": "/storage/uploads/chat/example.jpg"}
```

消息类型：`1` 文本、`2` 图片、`3` 语音、`4` 视频、`5` 小程序卡片、`6` 系统消息。当前接口校验消息内容和地址，不负责聊天媒体上传。

### `POST /chat/sessions/{session_id}/read`

将当前会话中发给当前用户的未读消息标记为已读，并清零会话未读数。

### `DELETE /chat/messages/{message_id}`

撤回自己发送的消息。撤回后不再返回原文本或媒体地址。

## 通知

- `GET /notifications`：分页查询通知，返回 `unread_count`。
- `POST /notifications/{notification_id}/read`：标记单条通知已读。
- `POST /notifications/read-all`：标记当前用户全部通知已读。

喜欢、匹配、认识申请和爆灯会写入用户通知表。

## 隐私、拉黑和举报

### `GET /users/me/privacy` / `PUT /users/me/privacy`

读取或更新隐私设置，包括谁可以看我、仅 VIP 查看详情、无痕浏览、仅认证用户联系、展示状态和通知开关。

### `GET /security/blocks`

返回当前用户黑名单。

### `PUT /security/blocks/{target_id}`

请求体可选：`{"reason": "骚扰"}`。拉黑后会取消双方匹配、关闭待处理认识申请，并阻止主页、申请和聊天操作。

### `DELETE /security/blocks/{target_id}`

解除当前用户对目标用户的拉黑。

### `POST /security/reports/{target_id}`

请求体：

```json
{
  "type": "骚扰",
  "description": "持续发送不当消息",
  "images": ["/storage/uploads/report/example.png"]
}
```

举报写入待处理记录，后台审核接口仍需后续补充。

## 权限和错误码

- `401`：未登录或会话失效。
- `403`：未绑定手机号、没有匹配关系、已拉黑或无权访问。
- `404`：目标用户、会话或消息不存在。
- `409`：关系状态冲突。
- `422`：请求字段不合法。
