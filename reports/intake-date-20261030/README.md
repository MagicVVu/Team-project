# 入库日期修复（2026-10-30）

新增物品在用户点击确认添加时，使用手机当天的日历日期作为入库日期，通过现有 `purchased_on` 字段上传。手动、语音核对、照片核对均覆盖；同一次添加拆出的独立物品使用同一日期。日期在归类核对前固定，归类请求持久化和网络重试保留原日期。

后端创建独立物品时保留上传日期，旧客户端省略或提交 null 时按 Asia/Shanghai 当天补齐。编辑资料保留已有日期。数据库无需迁移，product 数量继续由接口实时汇总。历史空日期未回填，避免把更新当天误记为历史入库日期。

## 部署与验证

- 已通过 `ssh magicvvu` 检查实际运行源码，基于原运行镜像仅替换 `app/services/physical_inventory.py`。
- 当前后端镜像：`magicvvu/backend:intake-date-20261030`。健康检查通过，AI 与数据库容器、环境、端口、挂载保持原配置。
- 服务器回滚备份：`/srv/magicvvu/releases/intake-date-20261030`。
- 临时 PostgreSQL：34 项测试通过，覆盖日期持久化、逐件拆分、跨日回放、编辑保留及现有库存功能。
- Android JVM：75 项测试通过。模拟器：7 项仪器测试通过，覆盖确认添加、照片、归类请求日期、原请求重试和真实服务器只读库存。
- 部署后在运行容器中经实际 API 栈与 PostgreSQL 验证 6 件测试物品；全部测试写入由外层事务回滚，并验证测试家庭、用户和物品均未留存。

应用版本：`1.2.5-inventory`（versionCode 9）。已在连接的模拟器上覆盖安装，保留登录和数据。

详细结果见 `verification.json`、`backend-postgres.xml`、`device-tests.log`、`live-after-deploy.log`、`server-check.json`、`deployment.json`。
