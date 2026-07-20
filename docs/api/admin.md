# 管理审核接口

统一前缀：`/api/v1`。所有接口要求当前账号具有 `admin` 角色，并使用：

```http
Authorization: Bearer <admin_access_token>
Content-Type: application/json
```

### `PATCH /admin/media/{media_id}/review`

审核用户头像、相册或视频：

```json
{"status": 1, "reason": "审核通过"}
```

状态：`1` 通过、`2` 拒绝、`3` 隐藏。未通过的媒体不会进入推荐名片或他人主页公开资料。

### `PATCH /admin/reports/{report_id}/review`

处理用户举报：

```json
{"status": 1, "result": "已处理并限制对方账号"}
```

状态：`1` 已处理、`2` 驳回。处理结果会写入举报记录，后续可扩展站内通知。
