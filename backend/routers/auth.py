"""
认证路由 — 邮箱 / 手机 OTP / Google OAuth / Token 刷新

所有端点均通过 httpx 调用 Supabase Auth REST API:
  - /auth/v1/signup          (邮箱注册)
  - /auth/v1/token           (邮箱登录 / 刷新 token)
  - /auth/v1/otp             (发送手机验证码)
  - /auth/v1/verify           (验证手机验证码)
  - /auth/v1/authorize        (Google OAuth 授权跳转, 隐式流程)
"""

import logging
from urllib.parse import urlencode, quote

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse

from ..config import (
    SUPABASE_AUTH_URL,
    SUPABASE_ANON_KEY,
    BACKEND_URL,
    FRONTEND_URL,
)
from ..models import (
    EmailAuthRequest,
    PhoneOTPStartRequest,
    PhoneOTPVerifyRequest,
    RefreshTokenRequest,
)

router = APIRouter(prefix="/auth", tags=["认证"])
logger = logging.getLogger(__name__)

_ANON_HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Content-Type": "application/json",
}


# ────────────────────── 工具函数 ──────────────────────

async def _supabase_post(path: str, body: dict, headers: dict | None = None) -> dict:
    """统一 POST 请求封装, 自动抛出上游错误"""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{SUPABASE_AUTH_URL}{path}",
            headers=headers or _ANON_HEADERS,
            json=body,
        )
    if resp.status_code >= 400:
        detail = resp.json() if resp.text else {"msg": resp.reason_phrase}
        logger.warning("Supabase %s 返回 %s: %s", path, resp.status_code, detail)
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return resp.json() if resp.text else {}


# ────────────────── 邮箱注册 / 登录 ──────────────────

@router.post("/signup/email")
async def signup_email(body: EmailAuthRequest):
    """邮箱 + 密码注册 — 调用 Supabase Auth /signup"""
    return await _supabase_post("/signup", {"email": body.email, "password": body.password})


@router.post("/signin/email")
async def signin_email(body: EmailAuthRequest):
    """邮箱 + 密码登录 — 调用 Supabase Auth /token?grant_type=password"""
    return await _supabase_post(
        "/token?grant_type=password",
        {"email": body.email, "password": body.password},
    )


# ────────────────── 手机 OTP ──────────────────

@router.post("/signup/phone/start")
async def phone_otp_start(body: PhoneOTPStartRequest):
    """
    发送手机验证码 — 调用 Supabase Auth /otp
    注意: Supabase 手机 OTP 同时支持注册和登录, 用户不存在时自动创建。
    """
    result = await _supabase_post("/otp", {"phone": body.phone})
    return {"message": "验证码已发送, 请查看手机短信", "detail": result}


@router.post("/signup/phone/verify")
async def phone_otp_verify(body: PhoneOTPVerifyRequest):
    """
    验证手机验证码 — 调用 Supabase Auth /verify
    验证成功后返回 access_token / refresh_token / user。
    """
    return await _supabase_post(
        "/verify",
        {"phone": body.phone, "token": body.token, "type": "sms"},
    )


# ────────────────── Google OAuth (隐式流程) ──────────────────

@router.get("/google/url")
async def google_auth_url():
    """
    生成 Google OAuth 登录 URL 并重定向。

    使用隐式流程 (Implicit Flow):
    1. 重定向用户到 Supabase /authorize 端点
    2. Supabase → Google → 用户授权 → Supabase
    3. Supabase 重定向到我们的 /auth/google/callback#access_token=...
       (token 在 URL fragment 中, 浏览器不会把 fragment 发到服务器)
    4. callback 页面的 JS 读取 fragment, 存入 localStorage, 跳转到首页
    """
    if not SUPABASE_AUTH_URL or not SUPABASE_AUTH_URL.startswith("http"):
        raise HTTPException(500, "SUPABASE_URL 未配置, 请检查 .env 文件")

    callback_url = f"{BACKEND_URL}/auth/google/callback"
    authorize_url = (
        f"{SUPABASE_AUTH_URL}/authorize"
        f"?provider=google"
        f"&redirect_to={quote(callback_url, safe='')}"
    )
    logger.info("Google OAuth 跳转: %s", authorize_url)
    return RedirectResponse(url=authorize_url, status_code=302)


@router.get("/google/callback")
async def google_callback(request: Request):
    """
    Google OAuth 回调 — 返回一个中转 HTML 页面。

    Supabase 隐式流程会把 access_token / refresh_token 放在 URL fragment (#) 中。
    浏览器不会把 fragment 发到服务器, 因此必须用客户端 JS 读取。
    此页面读取 fragment → 存入 localStorage → 跳转到首页。
    """
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>正在登录...</title></head>
<body style="font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;">
<div id="status">正在处理 Google 登录, 请稍候...</div>
<script>
(function() {{
    var hash = window.location.hash.substring(1);
    if (!hash) {{
        document.getElementById('status').textContent = 'Google 登录失败: 未收到 token。请返回重试。';
        return;
    }}
    var params = new URLSearchParams(hash);
    var at = params.get('access_token');
    var rt = params.get('refresh_token');
    if (at) {{
        localStorage.setItem('access_token', at);
        localStorage.setItem('refresh_token', rt || '');
        window.location.href = '/';
    }} else {{
        document.getElementById('status').textContent = 'Google 登录失败: token 解析异常。hash=' + hash;
    }}
}})();
</script>
</body></html>""")


# ────────────────── Token 刷新 ──────────────────

@router.post("/refresh")
async def refresh_token(body: RefreshTokenRequest):
    """用 refresh_token 换取新的 access_token — 调用 Supabase Auth /token?grant_type=refresh_token"""
    return await _supabase_post(
        "/token?grant_type=refresh_token",
        {"refresh_token": body.refresh_token},
    )
