# 社区与纸飞机接口

统一前缀：`/api/v1`。所有接口需要登录并绑定手机号。

## 社区动态

### `POST /community/posts`

发布动态：

```json
{
  "content": "今天去看了一个展览",
  "images": ["/storage/uploads/1/photo.webp"],
  "location": "上海"
}
```

文字最多 2000 字，最多 9 张图片。当前媒体地址必须来自已上传资源，社区内容审核后台仍需后续接入。

### `GET /community/posts`

动态流，`mode` 支持：

- `latest`：全站最新动态。
- `following`：已关注用户的动态。

支持 `page`、`page_size` 分页，每页最多 50 条。

### `DELETE /community/posts/{post_id}`

仅作者可以软删除自己的动态。

### `PUT /community/posts/{post_id}/like`

点赞动态。

### `DELETE /community/posts/{post_id}/like`

取消动态点赞。

### 评论

- `GET /community/posts/{post_id}/comments`：分页查看评论。
- `POST /community/posts/{post_id}/comments`：发表评论或回复。
- `DELETE /community/comments/{comment_id}`：删除自己的评论。

评论内容最多 500 字，支持二级回复。

## 纸飞机

### `POST /paper-planes`

请求体：

```json
{
  "content": "想认识同样喜欢旅行的人",
  "city": "杭州",
  "tags": ["旅行", "交友"],
  "is_anonymous": true
}
```

普通用户每天最多发送 3 次，记录有效期 24 小时。次数由 Redis 控制，Redis 不可用时返回 `503`。

### `GET /paper-planes`

捡取别人发送且自己没有回复过的有效纸飞机。

### `GET /paper-planes/mine`

查看自己发送的纸飞机。

### `POST /paper-planes/{plane_id}/replies`

回复纸飞机。不能回复自己的纸飞机，回复后该纸飞机状态变为已回应。

## 当前边界

动态图片审核、敏感词审核、话题管理、纸飞机语音、纸飞机转私信和后台审核接口尚未完成；这些不应在当前阶段标记为已验收。
