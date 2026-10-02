"""Trial contracts. Private storage models never serve as response models."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Role = Literal['host', 'matchmaker', 'guest', 'spectator', 'operator']
MediaMode = Literal['disabled', 'trtc']
Invitation = Literal['pending', 'accepted', 'declined']
Phase = Literal['intro', 'question', 'interest', 'choice', 'exchanges', 'transition', 'completed']
Action = Literal['accept', 'reserve', 'check_in', 'leave', 'hand', 'light', 'special',
                 'choose', 'withdraw_exchange', 'schedule', 'start', 'pause', 'resume',
                 'extend', 'advance', 'speaker', 'stage', 'remove', 'end', 'cancel', 'rehearse',
                 'decline', 'take_control', 'return_control', 'skip_round']


class LiveCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=80, description='受邀场次标题')
    scheduled_at: int = Field(gt=0, description='计划开场 Unix 秒，UTC')
    host_id: int = Field(gt=0, description='唯一主持的现有账号 ID')
    matchmaker_ids: list[int] = Field(min_length=2, max_length=2, description='两位红娘的现有账号 ID')
    male_ids: list[int] = Field(min_length=4, max_length=4, description='四位男嘉宾 ID，数组顺序即席位顺序')
    female_ids: list[int] = Field(min_length=4, max_length=4, description='四位女嘉宾 ID，数组顺序即席位顺序')
    main_order: list[int] = Field(min_length=4, max_length=4, description='2 男 2 女主嘉宾顺序')
    spectator_ids: list[int] = Field(default_factory=list, max_length=20, description='受邀观众 ID，不获得上台或选择权')
    notice: str = Field(min_length=10, max_length=2000, description='展示范围、音视频及必要审核留存告知')

    @model_validator(mode='after')
    def roster(self):
        ids = [self.host_id, *self.matchmaker_ids, *self.male_ids, *self.female_ids, *self.spectator_ids]
        if min(ids) <= 0 or len(ids) != len(set(ids)):
            raise ValueError('名单用户必须为正整数且不得兼任角色')
        if len(set(self.main_order)) != 4 or len(set(self.main_order) & set(self.male_ids)) != 2 or len(set(self.main_order) & set(self.female_ids)) != 2:
            raise ValueError('主嘉宾须为名单中不重复的两男两女')
        return self


class LiveUpdateRequest(LiveCreateRequest):
    expected_revision: int = Field(ge=0, description='编辑前快照版本；完整替换场前信息和名单')


class LiveCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    command_id: str = Field(min_length=8, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$', description='单次操作幂等键，重试复用')
    expected_revision: int = Field(ge=0, description='操作前快照版本；冲突重新拉取，不自动重放')
    action: Action = Field(description='本人或工作人员动作；条件字段与权限见 live.md 命令表')
    target_id: int | None = Field(default=None, gt=0, description='亮灯、特别心动、发言、上下台或移出的对象账号 ID')
    targets: list[int] = Field(default_factory=list, max_length=3, description='主嘉宾私密选择的候选 ID，可提交空数组')
    value: bool = Field(default=False, description='确认/开启为 true，撤回/暂不愿意/下台为 false')
    seconds: int = Field(default=60, ge=1, le=600, description='extend 延长秒数，仅截止前有效')
    display_name: str = Field(default='', max_length=32, description='accept 时授权公开的称呼，不可为空白')
    introduction: str = Field(default='', max_length=500, description='accept 时本人授权公开的介绍')
    consent_version: Literal['live-trial-v1'] | None = Field(default=None, description='accept 必须提交本期告知版本')
    device_checked: bool = Field(default=False, description='仅 trtc 模式的非观众须完成设备检测；disabled 不记录为通过')
    reason: str = Field(default='', max_length=255, description='移出、接管、交还、跳轮须填写非空白原因')


class Member(BaseModel):
    user_id: int
    role: Role
    group: Literal['male', 'female', 'none'] = 'none'
    seat: int = 0
    display_name: str = ''
    introduction: str = ''
    accepted: bool = False
    invitation: Invitation = 'pending'
    reserved: bool = False
    checked_in: bool = False
    attendance: Literal['invited', 'reserved', 'checked_in', 'backstage', 'onstage', 'left'] = 'invited'
    removed: bool = False
    hand: bool = False
    special_spent: bool = False
    special_target: int | None = None
    consent_at: int | None = None

    @model_validator(mode='before')
    @classmethod
    def legacy_invitation(cls, value):
        if isinstance(value, dict) and 'invitation' not in value and value.get('accepted'):
            return {**value, 'invitation': 'accepted'}
        return value


class Exchange(BaseModel):
    main_id: int
    candidate_id: int
    status: Literal['queued', 'active', 'completed', 'withdrawn'] = 'queued'
    started_at: int | None = None
    ended_at: int | None = None


class RoundState(BaseModel):
    main_id: int
    phase: Phase = 'intro'
    deadline: int | None = None
    selections: dict[str, list[int]] = Field(default_factory=dict)
    lights: dict[str, int] = Field(default_factory=dict)
    exchanges: list[Exchange] = Field(default_factory=list)
    skip_reason: str = ''


class LiveState(BaseModel):
    id: int = 0
    title: str
    scheduled_at: int
    notice: str
    owner_id: int
    media_mode: MediaMode = 'trtc'
    controller_id: int | None = None
    status: Literal['draft', 'scheduled', 'live', 'paused', 'ended', 'cancelled'] = 'draft'
    revision: int = 0
    members: list[Member]
    rounds: list[RoundState]
    round_index: int = 0
    stage_ids: list[int] = Field(default_factory=list)
    speaker_id: int | None = None
    pause_remaining: int = 0
    ended_at: int | None = None
    media_epoch: int = 0
    media_room_id: int = 0
    media_task_id: str | None = None

    @property
    def current(self) -> RoundState:
        return self.rounds[self.round_index]

    @property
    def controller(self) -> int:
        return self.controller_id if self.controller_id is not None else next(m.user_id for m in self.members if m.role == 'host')


class PublicMember(BaseModel):
    user_id: int = Field(description='现有账号 ID，不是 TRTC 用户串')
    role: Role = Field(description='本场角色，不赋予其他场次的权限')
    group: str = Field(description='male/female/none；工作人员和观众为 none')
    seat: int = Field(description='本组席位 1—4，工作人员及观众为 0')
    display_name: str = Field(description='本人已授权称呼，未确认时为受邀用户')
    introduction: str = Field(description='本人已授权公开的介绍，未确认时为空')
    attendance: str = Field(description='invited/reserved/checked_in/backstage/onstage/left；签到完成直接进入 backstage')
    on_stage: bool = Field(description='是否拥有当前逻辑舞台席位；disabled不代表媒体发布或设备检测通过')
    hand: bool = Field(description='是否正在举手等待主持安排')
    light_target: int | None = Field(description='本轮公开普通亮灯对象，无亮灯为 null')
    special_target: int | None = Field(description='本场公开特别心动对象，撤回或未使用为 null')
    invitation: Invitation = 'pending'
    checked_in: bool = False
    removed: bool = False


class LiveMe(BaseModel):
    user_id: int = Field(description='当前登录用户 ID')
    role: Role = Field(description='本场身份')
    accepted: bool = Field(description='是否已确认本场告知及公开资料')
    invitation: Invitation = 'pending'
    reserved: bool = Field(description='是否预约观看，独立于嘉宾资格')
    checked_in: bool = Field(description='是否已签到，离场后不自动撤销原签到记录')
    removed: bool = Field(description='是否被工作人员移出；后续场次接口拒绝访问')
    special_remaining: int = Field(description='特别心动剩余 0 或 1 次，撤回不恢复')
    selection: list[int] = Field(default_factory=list, description='只返回调用者本人的选择')


class LiveTargets(BaseModel):
    stage_ids: list[int] = Field(default_factory=list, description='可安排上下台的人')
    speaker_ids: list[int] = Field(default_factory=list, description='本环节可安排发言的人')
    remove_ids: list[int] = Field(default_factory=list, description='可移出的人；永不包含运营自己')
    interest_ids: list[int] = Field(default_factory=list, description='本人可亮灯/特别心动的对象')
    choice_ids: list[int] = Field(default_factory=list, description='本人可私密选择的有效对象')


class LiveSnapshot(BaseModel):
    id: int = Field(description='场次 ID')
    title: str = Field(description='场次标题')
    scheduled_at: int = Field(description='计划开场 Unix 秒，按本地时区展示')
    status: str = Field(description='draft/scheduled/live/paused/ended/cancelled')
    revision: int = Field(description='单调递增业务版本，命令提交时必须携带')
    server_time: int = Field(description='服务端当前 Unix 秒，用于校正倒计时')
    notice: str = Field(description='本场固定的展示、音视频和留存告知')
    round_index: int = Field(description='当前轮次索引 0—3，显示时加一')
    main_id: int = Field(description='当前主嘉宾账号 ID')
    phase: Phase = Field(description='当前轮次环节')
    deadline: int | None = Field(description='环节截止 Unix 秒；未开始、暂停或整场结束为 null')
    pause_remaining: int = Field(description='暂停时剩余秒数，恢复时重新计算 deadline')
    speaker_id: int | None = Field(description='主持安排的发言人 ID，无安排为 null')
    media_epoch: int = Field(description='媒体房间代数；变化后重新获取凭证和连接')
    media_mode: MediaMode = 'trtc'
    controller_id: int = Field(description='唯一有效控场者；不改变公开主持角色')
    owner_id: int = Field(description='本场运营账号；平台管理员不自动获得本场权限')
    main_order: list[int] = Field(description='已确定的四轮主嘉宾顺序')
    can_edit: bool = Field(description='仅本场运营、未开场时为 true')
    can_read_actions: bool = Field(description='本场运营、主持、红娘可读脱敏操作记录')
    members: list[PublicMember] = Field(description='本场名单与授权公开资料，含已离场人员')
    me: LiveMe = Field(description='仅调用者自己的意愿与资格，不含他人单方选择')
    allowed_actions: list[Action] = Field(description='按身份、状态和时间计算的动作；对象见 allowed_targets，提交仍须携带版本')
    allowed_targets: LiveTargets = Field(default_factory=LiveTargets)
    exchanges: list[Exchange] = Field(description='仅本轮截止后互选成功的组合，按候选席位顺序')


class SessionSummary(BaseModel):
    id: int
    title: str
    scheduled_at: int
    status: str
    role: Role
    media_mode: MediaMode = 'trtc'


class LiveList(BaseModel):
    items: list[SessionSummary]
    can_manage: bool


class LiveResources(BaseModel):
    ready: bool
    missing: list[str]
    provider: Literal['tencent-trtc'] = 'tencent-trtc'
    media_mode: MediaMode = 'trtc'
    business_ready: bool = Field(default=True, description='业务环境配置允许运行；不是数据库/Redis健康探测')
    business_missing: list[str] = Field(default_factory=list)
    media_ready: bool = False
    media_missing: list[str] = Field(default_factory=list)


class LiveAccount(BaseModel):
    user_id: int
    nickname: str
    gender: int
    eligible: bool
    missing: list[str] = Field(description='账号状态、成年、手机、实名等资格缺项，不返回敏感值')


class LiveAccountList(BaseModel):
    items: list[LiveAccount]
    page: int
    page_size: int
    total: int
    has_more: bool


class LiveActionRecord(BaseModel):
    id: int
    user_id: int
    action: str
    revision: int
    outcome: Literal['accepted', 'rejected'] = 'accepted'
    target_id: int | None = None
    reason: str = ''
    created_at: int


class LiveActionList(BaseModel):
    items: list[LiveActionRecord]
    page: int
    page_size: int
    total: int
    has_more: bool


class LiveCredentials(BaseModel):
    mode: Literal['rtc', 'cdn']
    sdk_app_id: int = 0
    room_id: int = 0
    user_id: str = ''
    user_sig: str = ''
    private_map_key: str = ''
    publish: bool = False
    playback_url: str = ''
    expires_at: int
    media_epoch: int


class LiveOpportunity(BaseModel):
    id: int
    session_id: int
    peer_id: int
    peer_name: str
    expires_at: int
    application_id: int | None
    status: Literal['available', 'used', 'expired']


class LiveResults(BaseModel):
    items: list[LiveOpportunity]
    session_ended: bool
    media_mode: MediaMode = 'trtc'


class LiveReportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    target_id: int = Field(gt=0)
    reason: str = Field(min_length=2, max_length=500)


class LiveReport(BaseModel):
    id: int
    target_id: int
    reason: str
    status: Literal['open', 'resolved']
    resolution: str = ''


class LiveReportResolution(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: str = Field(min_length=2, max_length=500, description='工作人员处置结论，不向场次公开广播')
