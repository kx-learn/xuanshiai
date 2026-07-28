"""Focused contracts for the ordinary-user message facade and MBTI release."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.data.mbti_core import (
    DEFINITION_ID,
    DEFINITION_VERSION,
    QUESTION_ROWS,
    RESULT_COPY_VERSION,
    definition_questions,
)
from app.main import app
from app.schemas.message import (
    ContactExchangeCreateRequest,
    MessageSendRequest,
)


def test_approved_mbti_core_is_stable_and_complete() -> None:
    questions = definition_questions()

    assert DEFINITION_ID == "mbti-core"
    assert DEFINITION_VERSION == "mbti-core@2"
    assert RESULT_COPY_VERSION == "mbti-result-copy@2"
    assert len(QUESTION_ROWS) == len(questions) == 60
    assert [question["id"] for question in questions] == [
        f"mbti-16p-{index:03d}" for index in range(1, 61)
    ]
    assert {question["dimension"] for question in questions} == {"EI", "SN", "TF", "JP"}
    assert {question["direction"] for question in questions} == {-1, 1}
    assert all(
        question["scaleMin"] == 1
        and question["scaleMax"] == 7
        and [option["value"] for option in question["options"]] == list(range(1, 8))
        for question in questions
    )


def test_message_media_and_contact_inputs_fail_closed() -> None:
    with pytest.raises(ValidationError):
        MessageSendRequest.model_validate(
            {
                "userId": 23,
                "type": "image",
                "clientMessageId": "media-without-id",
            }
        )

    media = MessageSendRequest.model_validate(
        {
            "userId": 23,
            "type": "image",
            "mediaId": 11,
            "clientMessageId": "media-with-id",
        }
    )
    assert media.content == ""
    assert media.media_id == 11

    with pytest.raises(ValidationError):
        ContactExchangeCreateRequest.model_validate(
            {
                "userId": 23,
                "contactType": "wechat",
                "contactValue": "short",
                "clientCommandId": "contact-invalid",
            }
        )

    with pytest.raises(ValidationError):
        ContactExchangeCreateRequest.model_validate(
            {
                "userId": 23,
                "contactType": "phone",
                "contactValue": "13800000000",
                "clientCommandId": "phone-value-not-allowed",
            }
        )


def test_message_and_emotion_lab_routes_are_in_openapi() -> None:
    paths = app.openapi()["paths"]

    assert paths["/api/v1/message/messages/{message_id}"]["delete"]
    assert paths["/api/v1/message/contact-exchanges"]["get"]
    assert paths["/api/v1/message/contact-exchanges"]["post"]
    assert paths["/api/v1/message/contact-exchanges/{exchange_id}/respond"]["post"]
    assert paths["/api/v1/emotion-lab/summary"]["get"]
    assert paths["/api/v1/emotion-lab/sessions"]["post"]
    assert paths["/api/v1/emotion-lab/sessions/{session_id}/answers"]["put"]
    assert paths["/api/v1/emotion-lab/sessions/{session_id}/submit"]["post"]
    assert paths["/api/v1/emotion-lab/sessions/{session_id}/discard"]["post"]
