# FastAPI + Supabase 用户认证演示

> 演示邮箱注册/登录、手机 OTP、Google OAuth、微信登录（Mock）四种认证方式。

---

## 目录结构

```
fastapi-firstservice/
├── backend/                  # FastAPI 后端
│   ├── main.py              # 应用入口 + /me 端点
│   ├── config.py            # 环境变量加载
│   ├── dependencies.py      # JWT 验证 (HS256)
│   ├── models.py            # Pydantic 请求模型
│   └── routers/
│       ├── auth.py          # 邮箱/手机/Google/Token 路由
│       └── wechat.py        # 微信登录路由 (独立实现)
├── frontend/
│   └── index.html           # 单页测试界面
├── sql/
│   └── init.sql             # 数据库表 + RLS + 触发器
├── .env.example             # 环境变量模板
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## ⚠️ 安全须知

| 规则 | 说明 |
|------|------|
| **SERVICE_ROLE_KEY 仅限后端** | 绝不可出现在前端 HTML/JS 中；本项目前端不使用任何 Supabase Key |
| **密钥泄露立即轮换** | 若 ANON_KEY 或 SERVICE_ROLE_KEY 泄露，立即到 Supabase Dashboard → Settings → API 轮换/撤销 |
| **.env 不入库** | `.gitignore` 已排除 `.env`；只提交 `.env.example` |

---

## 一、Supabase 配置

### 1.1 启用 Providers

在 **Supabase Dashboard → Authentication → Providers** 中启用：

| Provider | 操作 |
|----------|------|
| **Email** | 默认已启用；如需免确认可关闭 "Confirm email" |
| **Phone** | 启用后配置 Twilio SID/Token/Phone Number |
| **Google** | 需要 Google Cloud OAuth 2.0 Client ID & Secret（见下方） |

### 1.2 Google OAuth 配置

1. 前往 [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
2. 创建 **OAuth 2.0 Client ID**（Web application 类型）
3. **Authorized redirect URIs** 添加：
   ```
   https://<your-project-ref>.supabase.co/auth/v1/callback
   ```
4. 复制 Client ID 和 Client Secret
5. 在 Supabase Dashboard → Authentication → Providers → Google 中填入

### 1.3 Redirect URL 白名单

在 **Supabase Dashboard → Authentication → URL Configuration → Redirect URLs** 中添加：

```
http://localhost:8000/auth/google/callback
http://localhost:8000/
```

### 1.4 获取 JWT Secret

**Supabase Dashboard → Settings → API → JWT Secret** — 复制后填入 `.env` 的 `SUPABASE_JWT_SECRET`

---

## 二、数据库初始化

在 **Supabase Dashboard → SQL Editor** 中执行 `sql/init.sql`，会创建：

- `public.profiles` — 用户资料（RLS：只能读写自己的）
- `public.wechat_identities` — 微信绑定（RLS：只能读自己的，写入由后端 service_role 执行）
- `handle_new_user()` 触发器 — 新用户注册时自动创建 profile

---

## 三、本地运行

### 3.1 环境准备

```bash
# 1. 复制并编辑环境变量
cp .env.example .env
# 编辑 .env，填入你的 Supabase URL / Keys / JWT Secret

# 2. 安装依赖
pip install -r requirements.txt
```

### 3.2 启动后端

```bash
uvicorn backend.main:app --reload --port 8000
```

打开浏览器访问：
- **前端页面**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs

### 3.3 Docker 方式（可选）

```bash
# 确保 .env 已填写
docker compose up --build
```

---

## 四、API 端点一览

| 方法 | 路径 | 说明 | 调用方式 |
|------|------|------|----------|
| POST | `/auth/signup/email` | 邮箱注册 | Supabase Auth REST |
| POST | `/auth/signin/email` | 邮箱登录 | Supabase Auth REST |
| POST | `/auth/signup/phone/start` | 发送手机 OTP | Supabase Auth REST |
| POST | `/auth/signup/phone/verify` | 验证手机 OTP | Supabase Auth REST |
| GET | `/auth/google/url` | Google OAuth 跳转 (PKCE) | Supabase Auth REST |
| GET | `/auth/google/callback` | Google OAuth 回调 | Supabase Auth REST |
| GET | `/auth/wechat/url` | 微信授权 URL | 自定义逻辑 |
| GET | `/auth/wechat/callback` | 微信回调 + 创建用户 | 自定义逻辑 + Supabase Admin API |
| POST | `/auth/refresh` | 刷新 Token | Supabase Auth REST |
| GET | `/me` | 获取当前用户信息 | JWT 验证 + Supabase Auth REST |

---

## 五、测试各登录流程

### 5.1 邮箱

1. 在「邮箱」Tab 输入邮箱和密码，点击 **注册**
2. 去邮箱点击确认链接（或在 Supabase Dashboard 关闭邮箱确认）
3. 点击 **登录**，看到用户信息

### 5.2 手机 OTP

> 前提：Supabase 已配置 Twilio

1. 在「手机 OTP」Tab 输入国际格式手机号（如 `+8613800138000`）
2. 点击 **发送验证码**
3. 收到短信后输入 6 位验证码，点击 **验证登录**

### 5.3 Google

> 前提：已配置 Google OAuth Client + Supabase Provider

1. 点击「Google」Tab → **使用 Google 账号登录**
2. 在 Google 授权页登录
3. 自动跳回前端，显示用户信息

### 5.4 微信（Mock 模式）

1. 点击「微信」Tab → **微信登录**
2. Mock 模式下会直接跳转到回调，使用固定 openid 创建/登录用户
3. 自动跳回前端，显示用户信息

**切换真实模式**：在 `.env` 中设置 `WECHAT_MOCK_MODE=false`，并填入真实 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`

---

## 六、JWT 验证说明

本项目使用 **HS256 + Supabase JWT Secret** 验证 access_token。

**为什么不用 RS256 / JWKS：**
Supabase 托管版默认使用 HS256 签名 JWT（签名密钥即 Dashboard 中的 JWT Secret）。
JWKS 端点 (`/.well-known/jwks.json`) 在部分版本中可用，但官方推荐的验证方式仍是 HS256 + JWT Secret。
如果你使用自托管 Supabase 并配置了 RS256，请将 `dependencies.py` 中的 `algorithms=["HS256"]` 改为 `["RS256"]` 并使用公钥验证。

---

## 七、微信登录方案说明

**选择 Option 1**：后端用 service_role 在 Supabase Auth 中创建用户

- 微信 openid → 映射到 Supabase 用户 (email = `{openid}@wx.local`)
- `wechat_identities` 表保存 openid/unionid 绑定关系
- 用户可正常使用 Supabase 的 RLS、Realtime、Storage 等功能

**不选 Option 2（自签业务 JWT）的原因**：
自签 JWT 无法被 Supabase RLS/PostgREST 识别，用户无法直接访问 Supabase 服务，会增加大量代理逻辑。

---

## 八、常见问题

**Q: Google 登录报 "PKCE verifier 丢失"？**
A: Cookie 可能被浏览器阻止。检查浏览器是否允许第三方 Cookie，或确保 callback URL 与 Set-Cookie 的 domain 一致。

**Q: 手机 OTP 发送失败？**
A: 确认 Supabase Dashboard 中 Phone Provider 已启用，且 Twilio 配置正确。

**Q: 微信 Mock 登录失败？**
A: 确认 `sql/init.sql` 已在 Supabase SQL Editor 中执行，`wechat_identities` 表存在。
