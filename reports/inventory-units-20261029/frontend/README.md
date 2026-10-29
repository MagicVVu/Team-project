# Android逐件库存验收

前端现在把云端每条 inventory_items 记录当作一件实物。JSON 不再要求 quantity；内部输入/商品汇总模型保留 quantity，用于新增件数和圆环投影。库存记录的显示数量只由 ACTIVE 状态决定。

- 商品圆环显示 `*22`，按真实活动记录数统计；终态物品可在详情另行展开。
- 详情每行保留原名、规格、位置和日期，编辑/消耗使用该行真实ID；指定红苹果的消耗路由已验证。
- 新增不再弹出旧归类选择框，由服务器自动归类。原请求outbox保留，超时后按原正文重试。
- 新增计数单位要求1–10000整数；重量/容量请求保存为一份及规格；手动和照片录入可单独编辑规格。
- 老云端批次数量缓存提示联网刷新，避免用旧批次误计库存。游客缓存升级v2，将旧批次拆成真实本地行；本地保存记录不再包含quantity字段，同样按商品聚合。
- 最低库存只在商品计数投影判断，不把每件物品误报为低库存。

验收：74个JVM单元测试通过；11个Android模拟器测试通过。包括10苹果+12红苹果、每行唯一ID、一次消耗一件、不同包装规格、旧缓存/本地持久化、自动归类、超时原请求重试、登录失效不丢未知回执。

构建命令（Java来自本机Android Studio）：

```powershell
$env:JAVA_HOME='D:\Android Studio\jbr'
.\gradlew.bat :app:testDebugUnitTest :app:connectedDebugAndroidTest '-Pandroid.testInstrumentationRunnerArguments.class=com.example.teamapp.ProductRingIntegrationTest,com.example.teamapp.ProductGroupingFlowTest,com.example.teamapp.InventoryStoreTest' --offline --console=plain
```

APK：`frontend/app/build/outputs/apk/debug/app-debug.apk`。哈希和统计见verification.json。四张PNG为测试从真实模拟器截图生成，包含中英文/明暗主题圆环与详情。
