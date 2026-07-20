"""短信服务统一接口。"""

from typing import Protocol


class SmsProvider(Protocol):
    """短信供应商必须实现的接口。"""

    async def send_code(self, phone: str, purpose: str, code: str) -> None:
        """发送验证码；失败时抛出异常。"""
