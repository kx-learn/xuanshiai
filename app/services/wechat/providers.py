"""微信登录服务实现和工厂。"""

from fastapi import HTTPException

from app.core.config import settings
from app.services.wechat.base import WechatProvider


class MockWechatProvider:
    """仅用于 development/testing 的微信登录实现。"""

    async def exchange_code(self, code: str) -> dict[str, str]:
        if not settings.is_test_mode:
            raise HTTPException(status_code=503, detail="微信 Mock 服务仅允许测试环境使用")
        if not code.startswith("mock-code-"):
            raise HTTPException(status_code=400, detail="微信 Mock 登录凭证无效")
        suffix = code.removeprefix("mock-code-").strip()
        if not suffix or len(suffix) > 64:
            raise HTTPException(status_code=400, detail="微信 Mock 登录凭证无效")
        openid = f"{settings.wechat_mock_openid_prefix}{suffix}"
        return {"openid": openid, "unionid": f"mock-unionid-{suffix}"}


def get_wechat_provider() -> WechatProvider:
    """根据配置返回微信登录供应商。"""
    if settings.wechat_provider.lower() == "mock":
        return MockWechatProvider()
    if settings.wechat_provider.lower() == "wechat":
        raise RuntimeError("真实微信服务由 auth.exchange_wechat_code 处理")
    raise HTTPException(status_code=503, detail="微信登录供应商未实现")
