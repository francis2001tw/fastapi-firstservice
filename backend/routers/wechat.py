"""
微信登录路由 — 独立实现 (Supabase 不原生支持微信 OAuth)

方案选择: Option 1 — 后端用 service_role 在 Supabase Auth 中创建用户
  - 微信 openid 映射到 Supabase 用户 (email = {openid}@wx.local)
  - wechat_identities 表保存 openid / unionid 绑定关系
  - 用户可正常使用 Supabase RLS、实时订阅等功能

为什么不选 Option 2 (自签业务 JWT):
  - 自签 JWT 无法被 Supabase RLS 识别, 用户无法直接访问 Supabase REST/Realtime
  - 需要额外维护用户体系, 增加复杂度

⚠️ 本模块使用 SUPABASE_SERVICE_ROLE_KEY, 仅限后端调用
"""

import hmac
import hashlib
import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from ..config import (
    SUPABASE_AUTH_URL,
    SUPABASE_REST_URL,
    SUPABASE_ANON_KEY,
    SUPABASE_SERVICE_ROLE_KEY,
    WECHAT_APP_ID,
    WECHAT_APP_SECRET,
    WECHAT_MOCK_MODE,
    BACKEND_URL,
    FRONTEND_URL,
)

router = APIRouter(prefix="/auth/wechat", tags=["微信认证"])
logger = logging.getLogger(__name__)


def _make_password(openid: str) -> str:
    """
    用 HMAC-SHA256 为微信用户生成确定性密码。
    - 同一 openid 永远生成同一密码, 无需额外存储
    - 不知道 SERVICE_ROLE_KEY 就无法猜测密码
    """
    return hmac.new(
        SUPABASE_SERVICE_ROLE_KEY.encode(),
        openid.encode(),
        hashlib.sha256,
    ).hexdigest()


def _service_headers() -> dict:
    """构造 service_role 级别请求头 — ⚠️ 仅后端使用"""
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


# ────────────────── 获取微信授权 URL ──────────────────

@router.get("/url")
async def wechat_auth_url():
    """
    返回微信授权跳转 URL。
    - Mock 模式: 直接指向本地 callback (无需真实 appid)
    - 真实模式: 跳转到微信开放平台扫码授权页
    """
    if WECHAT_MOCK_MODE:
        url = f"{BACKEND_URL}/auth/wechat/callback?code=mock_code&state=mock"
        return {
            "url": url,
            "mock": True,
            "message": "Mock 模式: 将使用模拟微信身份 (openid=mock_openid_12345) 登录",
        }

    params = urlencode({
        "appid": WECHAT_APP_ID,
        "redirect_uri": f"{BACKEND_URL}/auth/wechat/callback",
        "response_type": "code",
        "scope": "snsapi_login",
        "state": "wx_auth",
    })
    url = f"https://open.weixin.qq.com/connect/qrconnect?{params}#wechat_redirect"
    return {"url": url, "mock": False}


# ────────────────── 微信回调处理 ──────────────────

async def _exchange_wechat_code(code: str) -> tuple[str, str, str]:
    """真实模式: 用 code 换取 openid / unionid / nickname"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.weixin.qq.com/sns/oauth2/access_token",
            params={
                "appid": WECHAT_APP_ID,
                "secret": WECHAT_APP_SECRET,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
    data = resp.json()
    if "errcode" in data and data["errcode"] != 0:
        raise HTTPException(502, f"微信授权失败: {data}")

    openid = data["openid"]
    unionid = data.get("unionid", "")

    async with httpx.AsyncClient(timeout=10) as client:
        info_resp = await client.get(
            "https://api.weixin.qq.com/sns/userinfo",
            params={"access_token": data["access_token"], "openid": openid},
        )
    info = info_resp.json()
    nickname = info.get("nickname", "微信用户")
    return openid, unionid, nickname


async def _find_or_create_user(openid: str, unionid: str, nickname: str) -> dict:
    """
    在 Supabase 中查找或创建微信用户:
    1. 查询 wechat_identities 表判断用户是否已存在
    2. 不存在则通过 admin API 创建 Supabase Auth 用户 + wechat_identities 记录
    3. 用邮箱 + 确定性密码登录, 获取 session
    """
    email = f"{openid}@wx.local"
    password = _make_password(openid)
    svc = _service_headers()

    async with httpx.AsyncClient(timeout=15) as client:
        # 1) 查询已有绑定
        check = await client.get(
            f"{SUPABASE_REST_URL}/wechat_identities",
            params={"openid": f"eq.{openid}", "select": "user_id"},
            headers={**svc, "Prefer": "return=representation"},
        )
        existing = check.json() if check.status_code == 200 and check.text else []

        if not existing:
            # 2) 创建新 Supabase 用户
            create_resp = await client.post(
                f"{SUPABASE_AUTH_URL}/admin/users",
                headers=svc,
                json={
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {
                        "provider": "wechat",
                        "wechat_openid": openid,
                        "wechat_unionid": unionid,
                        "nickname": nickname,
                    },
                },
            )
            if create_resp.status_code >= 400:
                logger.error("创建微信用户失败: %s", create_resp.text)
                raise HTTPException(500, f"创建微信用户失败: {create_resp.text}")

            user_id = create_resp.json()["id"]

            # 3) 写入 wechat_identities (使用 service_role 绕过 RLS)
            await client.post(
                f"{SUPABASE_REST_URL}/wechat_identities",
                headers={**svc, "Prefer": "return=minimal"},
                json={"user_id": user_id, "openid": openid, "unionid": unionid},
            )
            logger.info("新微信用户已创建: user_id=%s, openid=%s", user_id, openid)

        # 4) 登录获取 session
        sign_resp = await client.post(
            f"{SUPABASE_AUTH_URL}/token?grant_type=password",
            headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
            json={"email": email, "password": password},
        )
        if sign_resp.status_code >= 400:
            logger.error("微信用户登录失败: %s", sign_resp.text)
            raise HTTPException(500, "微信用户登录失败, 请稍后重试")

        return sign_resp.json()


@router.get("/callback")
async def wechat_callback(code: str, state: str = ""):
    """
    微信 OAuth 回调:
    - Mock 模式: code=mock_code → 固定 openid/unionid
    - 真实模式: 用 code 换取 openid, 然后查找/创建 Supabase 用户
    """
    if WECHAT_MOCK_MODE and code == "mock_code":
        openid, unionid, nickname = "mock_openid_12345", "mock_unionid_12345", "微信测试用户"
    else:
        openid, unionid, nickname = await _exchange_wechat_code(code)

    session = await _find_or_create_user(openid, unionid, nickname)

    at = session.get("access_token", "")
    rt = session.get("refresh_token", "")

    redirect_url = f"{FRONTEND_URL}/#access_token={at}&refresh_token={rt}&provider=wechat"
    return RedirectResponse(url=redirect_url, status_code=302)
