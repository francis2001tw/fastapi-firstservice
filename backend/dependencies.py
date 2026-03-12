"""
JWT 验证依赖项

验证方式: HS256 + Supabase JWT Secret
说明: Supabase 托管版默认使用 HS256 签名 JWT, 因此这里不使用 RS256 / JWKS。
     如果你的项目切换到自托管并启用了 RS256, 请改用 JWKS 方式验证。
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import SUPABASE_JWT_SECRET

_bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """
    解码并验证 Supabase access_token。
    - 算法: HS256
    - audience: "authenticated" (拒绝 anon / service_role token)
    返回 JWT payload dict。
    """
    token = credentials.credentials
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="服务器未配置 SUPABASE_JWT_SECRET",
        )
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期, 请刷新或重新登录")
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=401, detail="Token audience 无效")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Token 验证失败: {e}")
