# 媒体存储访问盘点与迁移方案

> 本文是访问风险盘点，不改变历史 URL、文件位置、数据库字段或部署契约。任何私有化迁移、URL 过渡、旧文件搬迁和线上发布都需要另行专项授权。

## 1. 当前事实

`app/main.py:145-146` 将整个 `settings.upload_dir` 直接挂载为 `/storage/uploads` 的 `StaticFiles`，该挂载没有认证依赖。因而同一目录下的文件具有相同的 HTTP 传输边界：知道 URL 即可匿名 `GET`，与生成 URL 的业务接口是否需要登录无关。

风险复现脚本 `scripts/reproduce_upload_exposure.py` 使用 `TemporaryDirectory`、`create_app()` 和 `TestClient`，不连接数据库、不读取本机上传目录。它分别写入跟进图片、跟进录音和普通资料图片哨兵文件，再以无 Cookie/Authorization 的请求验证当前行为；脚本预期三者均返回 `200`，仅供手动风险证据，不属于默认 pytest 集。

## 2. 服务、路径和消费方

| 服务 | 物理/URL 规则 | 逻辑属性 | 主要消费方 |
| --- | --- | --- | --- |
| `app/services/member_follow_up_admin.py:597-655` | `{upload_dir}/{member_id}/follow-up-img-{uuid}.webp`、`follow-up-voice-{uuid}.{ext}`；返回 `/storage/uploads/{member_id}/...` | 跟进记录附件，业务上属于红娘后台数据；当前传输层实际公开 | `app/api/routes/member_follow_up_admin.py:100-136` 的 `POST /api/v1/admin/members/{member_id}/follow-ups/media`；列表 `:82-85` 返回 `images`/`voice_url` |
| `app/services/media.py:75-99` | `{upload_dir}/{user_id}/audio/{uuid}.{ext}`；返回 `/storage/uploads/{user_id}/audio/...` | 纸飞机/聊天语音上传，上传接口需已认证；当前文件下载仍走无认证静态挂载 | `app/api/routes/media.py:11-28` 的 `POST /api/v1/media/uploads`，用途仅允许 `paper_plane_voice`/`chat_voice` |
| `app/services/profile.py:264-269,700-855` | `{upload_dir}/{user_id}/avatar-*`、`photo-*`、`background-*`、`video-*`；数据库 `user_media.file_url`/`thumbnail_url` 保存同类 URL | 资料媒体；普通照片/头像/背景/视频由公开资料消费，审核状态由数据库控制读取，但静态文件本身不检查状态 | `app/api/routes/users.py:101-122` 的头像、背景、相册、视频上传；`get_profile(..., public=True)`（`profile.py:286-361`）筛选已审核媒体并把 URL 提供给公开资料；`app/services/certifications.py:102-108` 复用 profile 的目录/URL 工具保存认证材料 |

补充：`app/services/profile.py:286-306` 的 `public=True` 只影响资料查询和 `user_media.review_status` 过滤，并不能给已经返回的静态 URL 增加下载鉴权。三个服务共用同一个物理根目录，当前没有按“公开资料/后台附件/认证材料/语音”分隔的存储边界。

## 3. 资源分类与权限矩阵

| 类别 | 当前生成位置/URL | 当前消费方 | 应有读取角色 | 当前匿名结果 | 历史 URL/缓存影响 |
| --- | --- | --- | --- | --- | --- |
| 公开资料媒体 | `/{user_id}/avatar-*`、`photo-*`、`background-*`、`video-*`；`/storage/uploads/{user_id}/...` | 公开资料、本人资料页 | 已审核且已发布的公开媒体可匿名读取；未审核/撤回对象不应继续公开 | 静态挂载会按路径返回，绕过 `review_status` | 公开 URL 可能被客户端、CDN、微信缓存；撤回需考虑缓存失效 |
| 社区图片/视频及缩略图 | `/{user_id}/community/*` | 帖子、纸飞机、社区媒体审核/展示 | 应按 `community_media` 状态、过期时间和可见范围控制；未绑定/未审核对象不应公开 | 静态挂载会按路径返回，数据库状态不参与文件下载 | URL 存在于媒体记录和客户端响应，直接下线会影响帖子/纸飞机 |
| 纸飞机/聊天语音 | `/{user_id}/audio/*` | 语音消息、纸飞机 | 已认证用户且通过会话/内容归属校验的参与者 | 静态挂载允许匿名读取 | 语音 URL 可能已写入消息或纸飞机数据；需要兼容期和缓存控制 |
| 红娘后台跟进附件 | `/{member_id}/follow-up-img-*`、`follow-up-voice-*` | 红娘 CRM 跟进详情 | 具备 `matchmaker.member.read` 且对目标会员有组织/业务归属的后台角色 | 当前 `200`，不需要后台凭据 | 历史跟进记录直接保存 URL；迁移需要逐条映射和回滚清单 |
| 用户认证材料 | 用户目录下 `education-cert-*`、`house-cert-*`、`single-pledge-*` 或认证字段引用的 URL | 用户本人认证页、平台审核后台 | 本人查看自身状态；具备认证审核权限的后台角色；其他用户禁止 | 当前静态挂载按路径可读 | 认证材料具有高敏感性；旧 URL 不能直接公开兼容 |
| AI/系统语音及后台资源 | `voice/tts`、`tts`、`admin` 等上传根目录子路径 | 对应任务或后台页面 | 按任务、账号和短期有效期授权；不应作为公共静态资源 | 需按具体路径核验，静态挂载原则上可读 | 可能被日志、任务结果或后台响应引用；需单独盘点 TTL 与缓存 |

### 权限结论

- 必须匿名失败：红娘跟进附件、认证材料、纸飞机/聊天语音、未审核或已撤回的社区/资料媒体、AI/后台临时资源。
- 可匿名读取的最小范围：仅明确标记为已审核、已发布的公开资料媒体；这不等于整个 `upload_dir` 可静态公开。
- 普通用户、红娘后台、认证审核后台和资源所属用户必须使用不同的授权判断，不能仅凭用户 ID 或 URL 前缀推断权限。
- 本矩阵是隔离环境设计基线，不代表当前线上已满足这些边界。

## 4. 隔离访问证据

`scripts/reproduce_upload_exposure.py` 使用 `TemporaryDirectory` 写入三类哨兵文件，随后以无 Cookie/Authorization 的 `TestClient` 请求验证。2026 年 9 月 25 日结果：

- 跟进图片：`200`，内容完全匹配。
- 跟进录音：`200`，内容完全匹配。
- 普通资料图片：`200`，内容完全匹配。
- 路径穿越请求：返回 `400` 或 `404`，未观察到目录外文件读取。
- 不存在文件：`404`。

这些结果证明路径规范化本身没有扩大到目录外，但不能抵消“知道合法路径即可匿名读取”的权限问题。当前脚本没有伪造后台身份或数据库归属，因此合法授权读取、普通用户越权和跨后台角色越权仍需在隔离数据库/服务环境补测。

## 5. 兼容止损方案（未实施）

1. 保留现有公开资料 URL 作为兼容入口，但停止将整个 `upload_dir` 挂载为无鉴权静态根目录。
2. 新增私有媒体读取路由：按资源类型、资源 ID、登录身份、组织/后台权限、会话参与关系和撤销/过期状态做归属校验，再用 `FileResponse` 或流式响应返回。
3. 新写入的跟进附件、语音、认证材料和临时系统资源进入私有目录；数据库保存资源类别、对象键或等价可校验元数据。
4. 公开资料只有在审核状态和发布状态均满足时才生成公开对象或公开 URL；审核撤回时由发布层撤销公开对象。
5. 对旧私有 URL 先建立观测和兼容策略，再按专项授权选择鉴权读取、明确拒绝或短期重定向；不直接删文件。

## 6. 完整迁移方案（未实施）

1. 建立 `public-profile`、`community-moderated`、`follow-up-private`、`voice-private`、`certification-private`、`system-private` 分区。
2. 生成资源清单：来源表、记录 ID、旧 URL、实际路径、SHA-256、媒体类型、归属用户/组织、目标对象键和可见性。
3. 在隔离存储复制并校验哈希、大小、MIME 和缩略图关系；先切读后切写，保留旧路径只读观察期。
4. 为历史 URL 定义过渡期限、缓存失效、客户端兼容、失败重试、重复执行和回滚点；迁移脚本必须幂等且禁止删除源文件作为第一步。
5. 逐类验收匿名、本人、同角色、跨角色、撤销授权、过期对象和公开媒体，再安排受控环境切换。

本阶段只完成盘点和证据，不执行上述止损或迁移方案。

