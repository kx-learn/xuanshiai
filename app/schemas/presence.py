"""Online presence request and response models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PresenceStatusRequest(BaseModel):
    status: Literal[1, 2]


class PresenceResponse(BaseModel):
    status: Literal[0, 1, 2]
    last_active_at: datetime | None
    heartbeat_interval_seconds: int
    expires_after_seconds: int
