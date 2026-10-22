# 家庭管理功能上线记录

日期：2026-10-22（北京时间）。已部署镜像 `magicvvu/backend:households-20261022`，基于线上 `magicvvu/backend:password-8-16-20261022` 构建，仅替换 `app/routers/households.py`。无需数据库迁移。保留现有密码规则、注册开关、TLS、来源限制、环境配置和其他业务代码。

## 接口约定

所有路径以 `/api/v1/households` 开头，均要求登录 Bearer Token。成员 ID 是用户 UUID。

| 方法 | 路径 | 请求体 | 权限及结果 |
|---|---|---|---|
| POST | `/{household_id}/leave` | 无 | 普通成员、管理员可退出，成功 204；所有者返回 409，须先转让或解散 |
| DELETE | `/{household_id}/members/{user_id}` | 无 | 所有者可移除其他非所有者成员；管理员仅可移除普通成员；成功 204 |
| PATCH | `/{household_id}/members/{user_id}` | `{"role":"admin"}` 或 `{"role":"member"}` | 仅所有者可设置/取消管理员，返回更新后的成员信息；不能用此接口变更所有者 |
| POST | `/{household_id}/transfer-ownership` | `{"new_owner_user_id":"已有成员的 UUID"}` | 仅所有者可操作；目标须为有效账号且已加入该家庭；新成员成为所有者，原所有者成为普通成员；成功 200，返回调用者的新家庭角色 |
| DELETE | `/{household_id}` | `{"confirmation_name":"当前完整家庭名称"}` | 仅所有者可操作，名称须精确一致；成功 204 |

未登录返回 401；不是家庭成员或目标成员不存在返回 404；角色无权操作返回 403；不允许的状态或确认名称不匹配返回 409；请求字段错误返回 422。自我移除应使用退出接口。转让给自己返回 409。

退出和移除仅删除成员关系，保留共享库存、采购和既有历史记录，也保留用户账号及其其他家庭。此后该成员不能继续访问该家庭。成员变化、管理员任免、所有权转让均使本家庭所有未使用的邀请码失效，需要重新生成邀请。

**解散是永久删除操作。** 它在一个事务内删除该家庭的成员、邀请码、共享库存、采购清单、AI 任务/草稿、执行回执和业务事件；不会删除用户账号或其他家庭。前端应展示删除范围并要求用户输入当前家庭名称，然后调用 DELETE 接口。本次未新增 Android 管理按钮，也未重建 APK。

## 并发和事务

家庭行锁串行化加入、退出、移除、角色变更、改名、生成邀请和转让操作；成员锁使库存/采购事务的授权在事务结束前保持有效。转让在同一事务中修改双方角色，并发转让不会产生两个所有者。

解散按任务、草稿、成员的顺序获取锁，与 AI 执行业务锁顺序一致；按外键依赖顺序删除执行台账后，由数据库级联删除其余家庭数据。提交前失败会回滚全部删除。邀请码加入也先锁家庭，避免与成员变更/解散产生相反的加锁顺序。

## 验证

- 最终候选镜像：SQLite 8 项测试通过，另 2 项 PostgreSQL 专属测试跳过；独立 PostgreSQL 10 项全部通过。
- 覆盖五项功能、角色权限、跨家庭隔离、现有创建/邀请/加入流程、成员移除后共享数据保留、含执行台账的完整解散、故障回滚、并发转让和授权事务等待。
- 候选镜像注册登录回归通过，保留 8–16 位字母数字注册规则及旧账号登录兼容性。
- 正式 PostgreSQL 备份已在独立临时 PostgreSQL 中通过 `pg_restore --exit-on-error` 实际恢复，家庭/成员/用户数量与原库一致。临时数据库容器与网络已清理。
- 实际发布 TLS listener 的 32 项 HTTPS 检查全部通过，校验项目 CA 与服务器 IP 身份。因公网 IP 不支持本机回环，服务器通过 loopback 访问同一个对外监听端口。
- 当前电脑另通过公网 HTTPS 验证 `/health` 返回 200；使用 Python 标准 TLS 校验项目 CA 和 IP 身份，证据见 `public-verification.json`。
- 真实验收使用 4 个随机标记临时账号和 2 个临时家庭，包含共享采购和购买入库；临时数据已清理。发布前后对 public schema 全部表逐行规范排序计算摘要，既有记录完全一致。
- 仅更新 backend.image 并重建 backend；Agent 和 PostgreSQL 容器 ID 不变。环境变量按名称和值比较一致、挂载和密钥文件不变，三个容器健康。首次发布因环境变量列表顺序检查触发自动回退，修正为映射比较后重新发布并验收成功。

机器可读证据：[deployment-verification.json](deployment-verification.json)。

测试源码：[隔离数据库回归](../../tools/household_management_verify.py)、[真实 TLS 验收](../../tools/household_management_live_verify.py)、[带自动回退的部署检查](../../tools/deploy_household_management.py)。

## 备份与回滚

服务器私有目录 `/etc/magicvvu/households-20261022`（0700）保存原 Compose、原镜像名称、数据库备份、候选构建文件和验证日志。数据库备份和原配置为 0600，不导出凭据或用户数据。

仅回退代码时，把 `/srv/magicvvu/magicvvu-starter/deploy/compose.yaml` 的 `services.backend.image` 改回 `magicvvu/backend:password-8-16-20261022`，验证配置后仅重建 backend：

```bash
sudo docker compose -f /srv/magicvvu/magicvvu-starter/deploy/compose.yaml config --quiet
sudo docker compose -f /srv/magicvvu/magicvvu-starter/deploy/compose.yaml up -d --no-deps --no-build --pull never backend
```

无需降级数据库。代码回滚不会恢复用户已执行的成员变化或已解散家庭；数据恢复须按具体家庭核对备份，不能直接覆盖整个业务库。
