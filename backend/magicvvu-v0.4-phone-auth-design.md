# MagicVVu v0.4 手机号 + 密码身份认证设计

## 产品决策

- 用户使用手机号 + 密码注册和登录。
- 早期开发不调用短信验证服务，因此手机号**没有实际所有权验证**。系统不得因为持有此字符串就授予短信重置密码、号码归属等能力。
- 内部测试注册功能默认关闭，运维可通过 `MAGICVVU_ALLOW_UNVERIFIED_SIGNUP=true` 在仅本机/SSH 隧道中开启。正式公开注册前须接入短信验证码、限制频率、HTTPS、账号找回和防滥用机制。

## 账户数据

`users` 保留兼容旧版 `email`（改为可空），新增：

| 字段 | 类型 | 约束与含义 |
| --- | --- | --- |
| `phone` | VARCHAR(20) | 可空（兼容旧 email 用户）；唯一；新用户须填写规范化 E.164 |
| `phone_verified_at` | TIMESTAMPTZ | 可空；目前始终为空 |
| `password_hash` | VARCHAR(255) | Argon2id，不存明文密码 |
| `display_name` | VARCHAR(100) | 用户昵称 |

新增 `auth_sessions`（短期令牌的 SHA-256 摘要、到期和注销），`household_invitations`（一次性邀请码摘要、到期及消耗情况）。数据库现为**原六张业务表 + 两张认证/邀请表**，并保留 `alembic_version` 技术表。

## 认证与安全

- 密码使用 Argon2id；新密码 10–128 字符。
- 登录成功颁发 256-bit 随机 Bearer Token（12h）；数据库中只保存摘要。
- 所有家庭 API 以已验证的 Bearer 身份在服务端检查 `household_members`。
- owner/admin 有权生成 30 分钟一次性邀请码；加入成功后获得 member 身份。
- 开发阶段未配置短信与网络限流；切勿把未验证注册开放到公网。
- 推荐 Android 使用受系统密钥保护的存储保存令牌；不要放日志或分享给其他成员。

## 与 v0.3 购物清单规则兼容

- 创建家庭时自动创建该家庭唯一共享清单。
- `shopping_lists.household_id` UNIQUE 保持不变。
- `shopping_list_items.added_by_user_id` 与 `purchased_by_user_id` 保持不变。
- 已购买自动入库、防重复入库作为内部可信业务函数保留，尚无公开 HTTP 购买接口。

## 迁移

新增 `20261014_0003_phone_auth_households.py`，引用 `20261014_0002`；不修改旧版迁移文件。迁移后版本应为 `20261014_0003 (head)`。

## 需要在公开上线前补充的内容

短信验证、手机号码归属保护和号码更换流程、密码找回、认证/注册限流、审计日志、HTTPS、数据隐私及合规措施、令牌和邀请表清理任务、真实 PostgreSQL 并发测试。
