-- ============================================================
-- FastAPI + Supabase Auth 演示 — 数据库初始化脚本
-- 在 Supabase Dashboard → SQL Editor 中执行本文件
-- ============================================================

-- ======================== 1. profiles 表 ========================
-- 用户资料表, 与 auth.users 一一对应
CREATE TABLE IF NOT EXISTS public.profiles (
    id         uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    nickname   text,
    created_at timestamptz DEFAULT now()
);

COMMENT ON TABLE public.profiles IS '用户资料表 — 每个 auth.users 行对应一条 profile';

-- 启用行级安全 (RLS)
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- 策略: 用户只能查看自己的 profile
CREATE POLICY "profiles_select_own"
    ON public.profiles FOR SELECT
    USING (auth.uid() = id);

-- 策略: 用户只能更新自己的 profile
CREATE POLICY "profiles_update_own"
    ON public.profiles FOR UPDATE
    USING (auth.uid() = id);

-- 策略: 用户只能插入自己的 profile (主要由触发器完成)
CREATE POLICY "profiles_insert_own"
    ON public.profiles FOR INSERT
    WITH CHECK (auth.uid() = id);


-- ======================== 2. wechat_identities 表 ========================
-- 微信身份绑定表, 一个 Supabase 用户对应一个微信 openid
CREATE TABLE IF NOT EXISTS public.wechat_identities (
    user_id    uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    openid     text        UNIQUE NOT NULL,
    unionid    text,
    created_at timestamptz DEFAULT now()
);

COMMENT ON TABLE public.wechat_identities IS '微信 openid/unionid 绑定表 — 写入操作仅通过后端 service_role 执行';

-- 启用行级安全 (RLS)
ALTER TABLE public.wechat_identities ENABLE ROW LEVEL SECURITY;

-- 策略: 用户只能查看自己的微信绑定信息
CREATE POLICY "wechat_select_own"
    ON public.wechat_identities FOR SELECT
    USING (auth.uid() = user_id);

-- ⚠️ 不创建 INSERT/UPDATE/DELETE 策略
-- 写入操作仅通过后端使用 service_role key 执行 (service_role 自动绕过 RLS)
-- 这确保了只有后端可以创建/修改微信身份绑定


-- ======================== 3. 自动创建 profile 触发器 ========================
-- 当新用户在 auth.users 中被创建时, 自动在 profiles 中插入一行
-- SECURITY DEFINER: 使用函数创建者的权限执行, 绕过 RLS

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.profiles (id, nickname)
    VALUES (
        NEW.id,
        COALESCE(
            NEW.raw_user_meta_data ->> 'nickname',
            NEW.raw_user_meta_data ->> 'full_name',
            NEW.raw_user_meta_data ->> 'name',
            split_part(NEW.email, '@', 1)
        )
    );
    RETURN NEW;
END;
$$;

-- 删除旧触发器 (幂等操作)
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

-- 创建触发器
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();
