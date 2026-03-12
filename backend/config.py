"""
配置管理 — 从 .env 文件加载所有敏感配置
⚠️ SUPABASE_SERVICE_ROLE_KEY 仅限后端使用, 绝不可出现在任何前端代码中
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ==================== Supabase ====================
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
# ⚠️ SERVICE_ROLE_KEY 拥有完整数据库权限, 仅在后端使用
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")

# ==================== 微信开放平台 ====================
WECHAT_APP_ID: str = os.getenv("WECHAT_APP_ID", "")
WECHAT_APP_SECRET: str = os.getenv("WECHAT_APP_SECRET", "")
WECHAT_MOCK_MODE: bool = os.getenv("WECHAT_MOCK_MODE", "true").lower() == "true"

# ==================== 应用地址 ====================
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:8000")
BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")

# Supabase Auth REST 基础路径
SUPABASE_AUTH_URL: str = f"{SUPABASE_URL}/auth/v1"
SUPABASE_REST_URL: str = f"{SUPABASE_URL}/rest/v1"
