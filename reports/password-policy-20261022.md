# 注册密码规则调整（2026-10-22）

新注册密码统一为 8–16 位 ASCII 英文字母和数字，必须同时包含两者，不接受空格、符号或中文。不要求同时包含大写和小写。规则仅作用于注册，已有账号登录及密码哈希不变。

## 已实施

- Android：`AuthForm.kt` 校验及 `AuthScreen.kt` 注册提示同步更新；服务器地址继续固定并隐藏。
- FastAPI：仅修改 `RegisterRequest` 长度与组合校验，保留实际线上 `LoginRequest` 和所有其他代码。
- 云端使用原运行镜像作为基础，仅覆盖一个 `app/schemas.py` 文件，生成 `magicvvu/backend:password-8-16-20261022`。实际 Compose 仅更改 backend 镜像字段，仅重新创建 backend，未重建 Agent、PostgreSQL 或运行数据库迁移。
- 更新现用自动化注册脚本的随机密码生成方式，使其满足新规则。
- 新 APK：`frontend/app/build/outputs/apk/debug/app-debug.apk`，已使用 `adb install -r` 覆盖 MuMu 并启动，未清除 App 数据。

## 验证

- 后端注册模型 13 项边界/兼容性测试通过；8、16 位有效，7、17 位、纯数字、纯字母、符号、中文、空格和换行无效。
- Android 28 项单元测试、2 项 MuMu 登录/注册表单测试通过。
- 新镜像在无网络、只读文件系统、临时 SQLite 数据库中通过认证安全及家庭邀请/隔离测试，包含较长旧密码的真实登录验证。
- 云端真实 HTTPS API：随机 8 位组合密码注册 201、登录 200、错误密码 401、重复注册 409、未验证状态保持、退出后 Token 401；临时专用测试账号和会话已清理，无家庭/库存写入。
- 本机通过公网 HTTPS 健康检查 200，证书校验开启。
- 变更前后的既有用户、家庭、成员、库存、采购表逐行摘要完全一致；来源白名单、宿主机来源规则、Agent/数据库镜像均未改变，三个容器运行正常。
- 本轮没有在 MuMu 重跑远程库存/Agent 全流程；这些接口未修改。

## 备份与回滚

服务器备份目录：`/etc/magicvvu/team-testing-password-20261022T092322Z`，包含原 Compose、环境文件、可读取的 PostgreSQL 备份、原 schema、实际补丁及测试/完整性日志。私有文件仅保存在服务器。

仅需回滚本次后端密码规则时，将实际 `/srv/magicvvu/magicvvu-starter/deploy/compose.yaml` 的 backend.image 恢复为 `magicvvu/backend:p72-units-736c2299edda`，然后运行：

```bash
sudo docker compose -f /srv/magicvvu/magicvvu-starter/deploy/compose.yaml config --quiet
sudo docker compose -f /srv/magicvvu/magicvvu-starter/deploy/compose.yaml up -d --no-deps --no-build backend
```

无需恢复数据库或删除数据卷。回滚后新建的 8–9 位密码账号仍可按旧登录逻辑登录；仅新注册规则恢复为此前要求。Android 如回滚注册规则，应同步恢复 `AuthForm.kt` 和注册页提示，再重新构建覆盖安装。
