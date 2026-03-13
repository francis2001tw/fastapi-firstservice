"""
FastAPI + Supabase 用户认证演示 — 应用入口

启动方式:
  uvicorn backend.main:app --reload --port 8000
  或在 backend 目录下: python main.py
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 支持直接运行 python main.py（无父包时用绝对导入）
if __name__ == "__main__" or not __package__:
    _backend = Path(__file__).resolve().parent
    if str(_backend) not in sys.path:
        sys.path.insert(0, str(_backend.parent))
    __package__ = "backend"

import httpx
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import SUPABASE_URL, SUPABASE_AUTH_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET
from backend.dependencies import get_current_user
from backend.routers import auth, wechat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    _check_config()
    await _log_provider_health()
    logger.info("🚀 服务启动 — 前端: http://localhost:8000  文档: http://localhost:8000/docs")
    yield
    logger.info("🛑 服务关闭")


def _check_config():
    """启动时检查必要配置, 缺失则给出明确警告"""
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_ANON_KEY:
        missing.append("SUPABASE_ANON_KEY")
    if not SUPABASE_JWT_SECRET:
        missing.append("SUPABASE_JWT_SECRET")
    if missing:
        logger.warning(
            "⚠️  以下环境变量未配置: %s — 请复制 .env.example 为 .env 并填入真实值",
            ", ".join(missing),
        )


async def _fetch_provider_health() -> dict:
    """
    从 Supabase Auth Settings 读取 provider 开关。
    注意: 这是只读请求, 不会触发登录流程。
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return {
            "ok": False,
            "error": "SUPABASE_URL 或 SUPABASE_ANON_KEY 未配置",
            "providers": {
                "google_enabled": None,
                "phone_enabled": None,
                "email_enabled": None,
            },
        }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{SUPABASE_AUTH_URL}/settings",
                headers={"apikey": SUPABASE_ANON_KEY},
            )
        if resp.status_code != 200:
            return {
                "ok": False,
                "error": f"读取 Supabase settings 失败: HTTP {resp.status_code}",
                "providers": {
                    "google_enabled": None,
                    "phone_enabled": None,
                    "email_enabled": None,
                },
            }

        data = resp.json()
        external = data.get("external", {})
        return {
            "ok": True,
            "error": None,
            "providers": {
                "google_enabled": bool(external.get("google", False)),
                "phone_enabled": bool(external.get("phone", False)),
                "email_enabled": bool(external.get("email", False)),
            },
            "raw": {
                "disable_signup": data.get("disable_signup"),
                "sms_provider": data.get("sms_provider"),
                "phone_autoconfirm": data.get("phone_autoconfirm"),
                "mailer_autoconfirm": data.get("mailer_autoconfirm"),
            },
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"请求 Supabase settings 异常: {e}",
            "providers": {
                "google_enabled": None,
                "phone_enabled": None,
                "email_enabled": None,
            },
        }


async def _log_provider_health():
    """启动时自动检测并输出 provider 状态。"""
    health = await _fetch_provider_health()
    if health.get("ok"):
        p = health["providers"]
        logger.info(
            "Auth Providers 状态: google=%s, phone=%s, email=%s",
            p["google_enabled"],
            p["phone_enabled"],
            p["email_enabled"],
        )
        if not p["google_enabled"]:
            logger.warning("⚠️ Google Provider 未启用: Authentication -> Providers -> Google")
        if not p["phone_enabled"]:
            logger.warning("⚠️ Phone Provider 未启用: Authentication -> Providers -> Phone (并配置 Twilio)")
    else:
        logger.warning("⚠️ Provider 检测失败: %s", health.get("error"))


app = FastAPI(
    title="FastAPI + Supabase Auth Demo",
    description="演示邮箱 / 手机 OTP / Google OAuth / 微信登录",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def json_exception_handler(request, exc: Exception):
    """确保所有未捕获异常都返回 JSON，避免前端解析到 "Internal Server Error" 文本"""
    logger.exception("未捕获异常: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) or "Internal server error"},
    )


# ────────────────── CORS (本地开发) ──────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ────────────────── 注册路由 ──────────────────
app.include_router(auth.router)
app.include_router(wechat.router)


# ────────────────── /me 端点 ──────────────────
@app.get("/me", tags=["用户信息"])
async def get_me(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    获取当前登录用户信息:
    1. 先通过 JWT 验证 (dependencies.get_current_user)
    2. 再调用 Supabase /auth/v1/user 获取完整用户对象
    """
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    supabase_user = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{SUPABASE_AUTH_URL}/user",
                headers={
                    "apikey": SUPABASE_ANON_KEY,
                    "Authorization": f"Bearer {token}",
                },
            )
            if resp.status_code == 200:
                supabase_user = resp.json()
    except Exception as e:
        logger.warning("调用 Supabase /user 失败: %s", e)

    return {
        "user_id": user.get("sub"),
        "email": user.get("email"),
        "phone": user.get("phone"),
        "role": user.get("role"),
        "expires_at": user.get("exp"),
        "app_metadata": user.get("app_metadata", {}),
        "user_metadata": supabase_user.get("user_metadata", {}),
        "identities": supabase_user.get("identities", []),
        "created_at": supabase_user.get("created_at"),
    }


@app.get("/health/providers", tags=["健康检查"])
async def health_providers():
    """
    返回当前 Supabase Auth Provider 配置状态。
    可用于排查:
    - Unsupported provider: provider is not enabled
    """
    return await _fetch_provider_health()


# ────────────────── 前端静态文件 ──────────────────
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/", include_in_schema=False)
async def serve_frontend():
    """返回前端单页应用"""
    return FileResponse("frontend/index.html")
