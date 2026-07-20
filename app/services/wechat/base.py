"""微信登录服务统一接口。"""

from typing import Protocol


class WechatProvider(Protocol):
    """微信登录供应商必须实现的接口。"""

    async def exchange_code(self, code: str) -> dict[str, str]:
        """将登录凭证换取微信身份。"""
