"""Pydantic 请求/响应模型"""

from pydantic import BaseModel
from typing import Optional


class EmailAuthRequest(BaseModel):
    email: str
    password: str


class PhoneOTPStartRequest(BaseModel):
    phone: str  # 国际格式, 如 +8613800138000


class PhoneOTPVerifyRequest(BaseModel):
    phone: str
    token: str  # 6 位验证码


class RefreshTokenRequest(BaseModel):
    refresh_token: str
