"""
Supabase 连接示例
将环境变量配置在 .env 文件中，或设置系统环境变量
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

# 从脚本所在目录加载 .env（兼容 Code Runner 等不同工作目录）
load_dotenv(Path(__file__).resolve().parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def get_supabase_client(use_service_role: bool = False) -> Client:
    """
    创建 Supabase 客户端

    Args:
        use_service_role: 若为 True，使用 service_role_key（绕过 RLS，用于服务端/admin 操作）
                         若为 False，使用 anon_key（受 RLS 限制，用于普通客户端）

    Returns:
        Supabase Client 实例
    """
    url = SUPABASE_URL
    key = SUPABASE_SERVICE_ROLE_KEY if use_service_role else SUPABASE_ANON_KEY

    if not url or not key:
        raise ValueError(
            "缺少 Supabase 环境变量。请设置 SUPABASE_URL、"
            "SUPABASE_ANON_KEY 和 SUPABASE_SERVICE_ROLE_KEY"
        )

    return create_client(url, key)


# 默认客户端：anon 权限（受 RLS 限制）
supabase: Client = get_supabase_client(use_service_role=False)

# 服务端客户端：service_role 权限（绕过 RLS，谨慎使用）
supabase_admin: Client = get_supabase_client(use_service_role=True)


if __name__ == "__main__":
    # 简单测试连接
    try:
        client = get_supabase_client()
        print("OK - Supabase connection successful")
    except Exception as e:
        print(f"FAIL - Connection error: {e}")
