"""Licensed MBTI core question bank and versioned result copy.

The source workbook is retained in the approved demo archive.  This module is
the reviewed production snapshot: it intentionally contains only MBTI's four
pre-agreed dimensions and never imports the demo runtime, Jung functions or
enneagram material.
"""

from __future__ import annotations

from typing import Final


DEFINITION_ID: Final = "mbti-core"
DEFINITION_VERSION: Final = "mbti-core@2"
RESULT_COPY_VERSION: Final = "mbti-result-copy@2"
SCALE_MIN: Final = 1
SCALE_MAX: Final = 7
DIMENSION_POLES: Final = {
    "EI": ("E", "I"),
    "SN": ("S", "N"),
    "TF": ("T", "F"),
    "JP": ("J", "P"),
}
OPTIONS: Final = (
    {"value": 1, "label": "非常不同意"},
    {"value": 2, "label": "不同意"},
    {"value": 3, "label": "比较不同意"},
    {"value": 4, "label": "不确定"},
    {"value": 5, "label": "比较同意"},
    {"value": 6, "label": "同意"},
    {"value": 7, "label": "非常同意"},
)

# id, question text, canonical dimension, direction.
# direction=1 means agreement favours the first canonical pole; -1 favours
# the second.  The source order is intentionally stable and is never shuffled.
QUESTION_ROWS: Final = (
    ("mbti-16p-001", "您经常交新朋友。", "EI", 1),
    ("mbti-16p-002", "您花了很多空闲时间探索各种激起您兴趣的随机主题。", "SN", 1),
    ("mbti-16p-003", "看到别人哭很容易让您觉得自己也想哭。", "TF", -1),
    ("mbti-16p-004", "您通常会为备份计划制定备份计划。", "JP", 1),
    ("mbti-16p-005", "您通常保持冷静，即使在很大的压力下。", "TF", 1),
    ("mbti-16p-006", "社交活动中，您很少尝试向新人介绍自己，主要与您已认识的人交谈。", "EI", -1),
    ("mbti-16p-007", "您更喜欢在开始另一个项目之前完全完成本个项目。", "JP", 1),
    ("mbti-16p-008", "您很多愁善感。", "TF", -1),
    ("mbti-16p-009", "您喜欢使用组织工具，如日程表和列表。", "JP", 1),
    ("mbti-16p-010", "即使是一个小错误也会让您怀疑自己的整体能力和知识水平。", "TF", -1),
    ("mbti-16p-011", "只要走到一个您觉得有趣的人身边，然后开始一段谈话，您就会觉得舒服。", "EI", 1),
    ("mbti-16p-012", "您对讨论创意作品的各种诠释和分析不太感兴趣。", "SN", 1),
    ("mbti-16p-013", "您更倾向于跟随您的头脑而不是您的心。", "TF", 1),
    ("mbti-16p-014", "您更喜欢在任何给定时刻做自己想做的事，而非计划特定日常工作。", "JP", -1),
    ("mbti-16p-015", "您很少担心您是否给您遇到的人留下好印象。", "TF", 1),
    ("mbti-16p-016", "您喜欢参加集体活动。", "EI", 1),
    ("mbti-16p-017", "您喜欢使您对结局做出自我诠释的书籍和电影。", "SN", -1),
    ("mbti-16p-018", "您的幸福更多地来自帮助别人完成事情，而不是您自己的成就。", "TF", -1),
    ("mbti-16p-019", "您对很多事情感兴趣，您发现很难选择下一步尝试什么。", "JP", -1),
    ("mbti-16p-020", "您很容易担心事情会变得更糟。", "TF", -1),
    ("mbti-16p-021", "您避免在小组环境中扮演领导角色。", "EI", -1),
    ("mbti-16p-022", "您绝对不是艺术类型的人。", "SN", 1),
    ("mbti-16p-023", "您认为若人更多依靠理性而更少地依靠自己的感受，世界将变得更美好。", "TF", 1),
    ("mbti-16p-024", "在让自己放松之前，您更喜欢做家务。", "JP", 1),
    ("mbti-16p-025", "您喜欢观看人们的争论。", "TF", 1),
    ("mbti-16p-026", "您倾向于避免把注意力吸引到自己身上。", "EI", -1),
    ("mbti-16p-027", "您的情绪会很快改变。", "TF", -1),
    ("mbti-16p-028", "您对效率不如您的人会失去耐心。", "JP", 1),
    ("mbti-16p-029", "您经常在最后截止日期前做事情。", "JP", -1),
    ("mbti-16p-030", "您一直着迷于死后会发生什么的问题（如果真的会发生的话）。", "SN", -1),
    ("mbti-16p-031", "您通常更喜欢和别人在一起，而不是独自一人。", "EI", 1),
    ("mbti-16p-032", "当讨论变得高度理论化时，您会觉得变得无聊或失去兴趣。", "SN", 1),
    ("mbti-16p-033", "您发现很容易同情一个与您的经历非常不同的人。", "TF", -1),
    ("mbti-16p-034", "您通常会尽可能长时间地推迟最终决定。", "JP", -1),
    ("mbti-16p-035", "您很少狐疑您所做的选择。", "JP", 1),
    ("mbti-16p-036", "经过漫长而疲惫的一周，一场热闹的社交活动正是您所需要的。", "EI", 1),
    ("mbti-16p-037", "您喜欢去艺术博物馆。", "SN", -1),
    ("mbti-16p-038", "您经常很难理解别人的感受。", "TF", 1),
    ("mbti-16p-039", "您喜欢有一份每天的待办事项清单。", "JP", 1),
    ("mbti-16p-040", "您很少感到没有安全感。", "TF", 1),
    ("mbti-16p-041", "您会避免打电话。", "EI", -1),
    ("mbti-16p-042", "您经常花很多时间试图理解与您自己截然不同的观点。", "SN", -1),
    ("mbti-16p-043", "在您的社交圈里，您经常是联系您的朋友并发起活动的人。", "EI", 1),
    ("mbti-16p-044", "如果您的计划被打断，您的首要任务是尽快回到正轨。", "JP", 1),
    ("mbti-16p-045", "您仍然被您很久以前犯的错误所困扰。", "TF", -1),
    ("mbti-16p-046", "您很少考虑人类存在的原因或生命的意义。", "SN", 1),
    ("mbti-16p-047", "您的情绪控制您胜过您控制它们。", "TF", -1),
    ("mbti-16p-048", "您非常小心地不让别人难堪，即使这完全是他们的错。", "TF", -1),
    ("mbti-16p-049", "比起有组织和一贯的努力，您的工作风格更接近自发的能量爆发。", "JP", -1),
    ("mbti-16p-050", "当有人对您评价很高时，您会想知道他们需要多久就会对您失望。", "TF", -1),
    ("mbti-16p-051", "您会喜欢一份大部分时间都需要您独自操作的工作。", "EI", -1),
    ("mbti-16p-052", "您认为思考抽象的哲学问题是浪费时间。", "SN", 1),
    ("mbti-16p-053", "与安静、私密的地方相比，您更喜欢繁忙、熙熙攘攘的地方。", "EI", 1),
    ("mbti-16p-054", "您乍一看就知道某人的感受。", "TF", -1),
    ("mbti-16p-055", "您经常感到不知所措。", "TF", -1),
    ("mbti-16p-056", "您有条不紊地完成事情，而不跳过任何步骤。", "JP", 1),
    ("mbti-16p-057", "您对被标记为有争议的事情很感兴趣。", "SN", -1),
    ("mbti-16p-058", "如果您认为别人更需要它，您会把一个好机会让出去。", "TF", -1),
    ("mbti-16p-059", "您会在最后期限上挣扎。", "JP", -1),
    ("mbti-16p-060", "您对事情会向对自己有利的方向发展有信心。", "TF", 1),
)

RESULT_SUMMARIES: Final = {
    "INTJ": "你是一个战略型的思考者，倾向于独立地把复杂想法转化为清晰的行动计划。",
    "INTP": "你倾向于探索抽象概念，重视分析、知识与创造性地解决问题。",
    "ENTJ": "你倾向于组织并动员他人，关注目标、执行和长远方向。",
    "ENTP": "你倾向于从不同角度探索可能性，享受思考、讨论和创新。",
    "INFJ": "你倾向于从价值与洞察出发理解问题，并关注积极而有意义的影响。",
    "INFP": "你倾向于忠于内在价值，重视创造力、同理心和个人意义。",
    "ENFJ": "你倾向于关注人与关系，擅长鼓励、引导并凝聚他人。",
    "ENFP": "你倾向于保持好奇与想象力，并在人际互动中发现新的可能。",
    "ISTJ": "你倾向于重视秩序、责任和可靠的执行，习惯把事情做得细致明确。",
    "ISFJ": "你倾向于以细致可靠的方式关心和支持他人，也重视承诺与责任。",
    "ESTJ": "你倾向于组织资源并推动结果，重视清晰的规则、效率和行动。",
    "ESFJ": "你倾向于关注社区与和谐，善于察觉需求并维护稳定的人际联系。",
    "ISTP": "你倾向于以冷静、务实的方式理解事物如何运作，并灵活解决问题。",
    "ISFP": "你倾向于尊重内在感受与审美，以温和而自主的方式作出选择。",
    "ESTP": "你倾向于在当下行动、适应变化，并从实践和挑战中获得能量。",
    "ESFP": "你倾向于投入当下体验和人际互动，并为周围带来活力与温度。",
}


def definition_questions() -> list[dict[str, object]]:
    """Return a serializable copy for a newly created session snapshot."""
    return [
        {
            "id": question_id,
            "text": text,
            "dimension": dimension,
            "direction": direction,
            "scaleMin": SCALE_MIN,
            "scaleMax": SCALE_MAX,
            "options": [dict(option) for option in OPTIONS],
        }
        for question_id, text, dimension, direction in QUESTION_ROWS
    ]
