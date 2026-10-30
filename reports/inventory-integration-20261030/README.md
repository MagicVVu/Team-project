# 库存接口对接复核与设备修复

2026-10-30，Asia/Shanghai。

截图中的 `No value for quantity` 来自旧客户端：实际连接的 `emulator-5554` 安装时间仍为2026-10-28 23:35:44，版本号4（1.2.0-test），早于10月29日的逐件库存改造。当前源码的库存解析已经按ACTIVE状态生成内部单件投影，不再读取库存数量字段；采购清单的数量仍是合法字段。

通过 `ssh magicvvu` 检查，服务器当前运行 `magicvvu/backend:p86-dc3519330fec` 与配套AI镜像，三项服务healthy。运行中的库存响应模型不包含quantity，采购响应仍包含quantity。保留今天的P8.6部署，未重启或覆盖服务器服务。

已把Android版本递增到5 / `1.2.1-inventory`，从当前源码重新构建，在连接设备执行覆盖安装并保留登录及原数据。新增显式开启的 `LiveInventoryReadTest`，直接使用设备已有账号执行真实服务器只读验收：

- 当前库存和商品接口读取成功，无quantity字段的库存及缓存可以解析。
- 商品圆环显示真实库存，点击后逐件详情可以展示；截图不再出现quantity错误。
- 新建CloudStore可恢复本次缓存，账号和家庭保持不变。

74项JVM测试通过，2项真实服务器设备测试通过。验证期间未新建账号、未调用真实模型、未修改服务器库存或采购数据；仅刷新设备缓存。应用已重新打开。

安装包：[mewstow-1.2.1-inventory.apk](../../frontend/app/build/outputs/apk/debug/mewstow-1.2.1-inventory.apk)。实际安装版本、安装包摘要与测试统计见 [verification.json](verification.json)，设备验收输出见 [live-device-tests.log](live-device-tests.log)，实际详情截图见 [live-inventory-detail.png](live-inventory-detail.png)。未提交或推送Git。
