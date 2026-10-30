# 库存单位输入移除

2026-10-30，Asia/Shanghai。

按用户最新补充，保留product数量由接口实时汇总的方式，没有新增product数量列或数据库触发器，没有执行数据库结构迁移。inventory_items仍无quantity列；新增请求中的quantity仅表示要展开创建多少条物品记录，不会存成某条库存的余量。

前端手动新增、语音审核、编辑的单位文本框与照片审核的单位选择器已移除。库存数量调整页也不再把内部单位拼到件数输入标签中。新增记录统一使用内部“件”单位，编辑旧物品时不要求用户填写、也不会通过PATCH重写其旧单位。采购清单的计量单位保留，未改动其业务。

重量/容量填写在规格中。明确的语音输入“500克肉”在审核表显示一件、规格500克，避免把500误当500件；照片识别的包装规格继续保留。批量录入仍保留件数输入，产品数量仍来自关联的ACTIVE库存记录数。

通过ssh magicvvu将库存新增接口的unit字段改为可省略，默认“件”，兼容已有显式单位请求。发布镜像 `magicvvu/backend:unitless-inventory-20261030` 只覆盖inventory_schemas.py，保留AI、数据库、端口、挂载与环境变量。原配置和文件备份位于服务器 `/srv/magicvvu/releases/unitless-inventory-20261030`。

服务器复核：Alembic版本仍20261029_0012，inventory_items不存在quantity列，product表结构不变。接口仍实时统计22个商品下331条在库记录，没有把汇总数量删除或迁入单物品。准备过程中曾在本机临时数据库验证过独立商品计数字段方案；用户补充后已撤回，相关迁移、模型字段和测试文件已删除，从未向服务器部署该方案。临时数据库已清理。

验证：30项独立PostgreSQL测试通过（含省略单位录入10+12=22、旧单位不改写、重复请求防重）；74项JVM测试通过；8项设备测试通过（新增、编辑、语音规格、照片确认及真实服务器读取）。发布后另通过3项真实服务器只读设备复核，没有新增生产测试库存或调用真实AI。证据：[verification.json](verification.json)、[PostgreSQL测试](backend-postgres.xml)、[设备测试](device-tests.log)、[发布后读取](live-after-deploy.log)、[线上模型复核](server-check.json)、[部署检查](deployment.json)。

连接的模拟器已保留登录和数据升级为8 / 1.2.4-inventory。新版 [APK](../../frontend/app/build/outputs/apk/debug/mewstow-1.2.4-inventory.apk)。所有既有未提交修改均保留，未提交或推送Git。
