"""短信服务实现和工厂。"""

from fastapi import HTTPException

from app.core.config import settings
from app.services.sms.base import SmsProvider


class DisabledSmsProvider:
    """未配置短信服务时的实现。"""

    async def send_code(self, phone: str, purpose: str, code: str) -> None:
        raise HTTPException(status_code=503, detail="短信服务未配置")


class MockSmsProvider:
    """仅用于 development/testing 的短信实现，不调用外部服务。"""

    async def send_code(self, phone: str, purpose: str, code: str) -> None:
        if not settings.is_test_mode:
            raise HTTPException(status_code=503, detail="短信 Mock 服务仅允许测试环境使用")
        if code != settings.sms_mock_code:
            raise HTTPException(status_code=500, detail="短信 Mock 配置异常")


def get_sms_provider() -> SmsProvider:
    """根据配置返回短信供应商。"""
    providers: dict[str, SmsProvider] = {
        "disabled": DisabledSmsProvider(),
        "mock": MockSmsProvider(),
    }
    provider = providers.get(settings.sms_provider.lower())
    if provider is None:
        raise HTTPException(status_code=503, detail="短信服务供应商未实现")
    return provider
