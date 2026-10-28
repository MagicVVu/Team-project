# 商品圆环与关联批次接入

日期：2026-10-28

## 行为

- 登录云端后，库存圆环的每个条目对应一条 products 记录。分类、搜索、排序、数量和总条目数作用于商品。
- 商品详情逐条列出 product_batches 关联的 inventory_items，包括 ACTIVE、FINISHED、DISCARDED、REVERSED，不按名称自动合并。
- 圆环数量合计 ACTIVE 且数量大于零的批次；只使用同单位或确定的质量/体积单位换算，不能换算时显示“数量待核对”。有效期取在库批次最早已登记日期。基础单位、名称、分类来自商品。
- 详情显示每个真实批次的数量、单位、位置、有效期、购入日期、开封日期、状态和编号。编辑、资料与盘点、询问使用真实批次 ID。
- 无批次的商品仍显示；未关联商品的旧库存单独提示，不自动创建商品或修改关联。游客模式保持原有本机库存。
- 商品缓存按服务器、账号、家庭隔离。读取失败保留最近缓存并显示同步错误，不把批次回退显示成商品。

## 只读接口

GET /api/v1/households/{household_id}/inventory-products?limit=50&offset=0

返回 inventory-products-1 协议、items、total、limit、offset。每个商品含 inventory_items 完整批次 DTO。复用现有 App Key、登录认证和家庭成员权限；跨家庭关联不会泄漏其他家庭批次。Cache-Control: no-store。

原后端仅提供商品创建和关联写入接口，故本次补充上述读取接口。没有数据库迁移。

## 验证

- Android 单元测试：64 项通过，包括商品身份、Decimal 汇总、可靠换算、未知换算和空商品。
- Android 模拟器：ProductRingIntegrationTest 两项通过，浅色中文、深色英文，圆环到真实批次详情、保留终态批次、关闭恢复圆环。
- assembleDebug、lintDebug 通过；截图已人工查看，深色详情使用主题文字颜色。
- 后端 SQLite：商品读取专项及 P9 回归共 28 项通过、2 项 PostgreSQL 环境专项跳过。
- 线上验证：抽查家庭 1 个商品、2 条关联批次，接口与数据库关联完全一致；实际 HTTP 未登录请求返回 401；迁移版本仍为 20261026_0011。只执行查询及成员共享锁，结束时回滚验证事务。

## 发布

经用户确认发布。当前后端镜像：magicvvu/backend:product-ring-20261028。
基于发布时现有认证镜像 magicvvu/backend:app-key-20261028t140429z，只替换商品路由文件。
后端健康检查通过，数据库和 Agent 容器 ID 保持不变。
服务器 Compose 备份：/srv/magicvvu/magicvvu-starter/deploy/compose.before-product-ring-20261028.yaml。
回滚时仅将 backend.image 恢复为上述认证镜像，使用同一 Compose 文件执行 up -d --no-deps backend。

安装包：frontend/app/build/outputs/apk/debug/app-debug.apk。
截图采用独立离线测试数据，不包含正式账号业务内容。
最终 APK SHA-256：CC4B14F2BBF98BE7DB0BDCFC7809006ABB58F2D580F8B2CC161B9EDA69B4F59E
