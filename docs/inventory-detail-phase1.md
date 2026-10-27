# 物品详情第一阶段交付记录

日期：2026-10-27。项目实际工作目录：`Team-project/`，分支：`dev`，起点：`181b413`。

## 工作区与边界

- 内层项目开始时只有未跟踪的 `reports/connectivity-20261027/`，完整保留。
- 外层 `Team_Project_Shared` 是另一份具有大量既存删除状态的 Git 工作区，本次没有恢复、清理或修改它的跟踪文件。
- 本地 HEAD 与缓存的 `origin/dev` 一致；两次 fetch 分别遇到网络初始化失败、连接重置，因此不能保证它是 GitHub 当前最新提交。
- 未修改后端 Python、数据库、迁移、API 契约、登录、家庭切换或云端读取逻辑。没有提交或推送。

## 1. 文件清单

| 文件 | 改动 |
| --- | --- |
| `frontend/app/src/main/java/com/example/teamapp/data/InventoryPreview.kt` | 新增独立单件/聚合预览模型、按作用域及物品 ID 隔离的会话仓库、校验和批次幂等 |
| `frontend/app/src/main/java/com/example/teamapp/data/InventoryStore.kt` | 挂载会话预览仓库及作用域；不进入持久化、导出和网络请求 |
| `frontend/app/src/main/java/com/example/teamapp/ui/ring/InventoryDetailContent.kt` | 重排身份区、右侧入库、数量摘要、单件列表和次要操作 |
| `frontend/app/src/main/java/com/example/teamapp/ui/ring/InventoryReceiveDialog.kt` | 新增数量输入、可选有效期日历、取消及确认交互 |
| `frontend/app/src/main/java/com/example/teamapp/ui/MagicApp.kt` | 首页和库存详情统一使用新内容；保留原操作路由及删除确认 |
| `frontend/app/src/main/java/com/example/teamapp/ui/ring/RingInventoryPage.kt` | 仅移除已不需要的展示分支参数；动画状态机与时序保持原样 |
| `frontend/app/src/main/res/values/ui_strings.xml` | 新增中文资源 |
| `frontend/app/src/main/res/values-en/ui_strings.xml` | 新增对应英文资源 |
| `frontend/app/src/test/java/com/example/teamapp/InventoryPreviewTest.kt` | 新增 9 项模型测试 |
| `frontend/app/src/androidTest/java/com/example/teamapp/InventoryPreviewUiTest.kt` | 新增 9 项隔离 UI 测试及截图 |
| `frontend/app/src/androidTest/java/com/example/teamapp/InventoryDetailAnimationTest.kt` | 将编辑按钮定位适配为 LazyColumn 滚动查找，保留原动画断言 |
| `docs/inventory-detail-phase1.md` | 本交付记录 |

已阅读 `Inventory.kt`、`InventoryContract.kt`、编辑器、QuantityAction、BatchOperationsPanel、日期组件及现有测试；未修改原 StockItem 或服务器业务模型。

## 2. 新详情结构

顶部仍由原宿主显示“详情 / 关闭”。内容顺序为：图标、名称、分类与右侧绿色“入库 +”；前端预览数量及原已保存数量；单件库存；编辑、消耗、可展开的数量记录、删除。辅助信息采用较低对比度，列表使用柔和边框和圆角。

使用 LazyColumn 和稳定记录 key，长列表不一次组合所有行。浅色、深色沿用 MaterialTheme。新增资源通过项目 rememberUiStrings 读取。列表无记录时显示空状态及入库入口，不制造示例数据。

## 3. 入库流程

点击身份区“入库 +”打开 Dialog。输入当前单位下的数量，选择有效期或保持“不设置”，再确认。数字为空、零、负数、非法格式、按件小数时禁用确认。

日期界面沿用已有 CoverageDateDialog 的 Compose 日历样式，允许选择过去及未来日期，支持翻月；初始日期为空，展示当前月份不等于选择当天。取消日期选择保持原选择；“不设置有效期”可清除选择。

确认后按数量追加记录，更新列表及由记录计算的总量，滚动到本次新增记录。位置取当前物品的位置；开封日期始终为空。取消不调用预览写入。提交锁与批次 ID 双重防重复。

## 4. 模型与状态

InventoryPreviewRecord 包含 id、itemId、location、可空 expiryDate/openedAt、batchId、source、quantity。单件模式每条 quantity 为 1；连续计量或不能安全拆分的旧数据，每条保留 BigDecimal 聚合数量。

InventoryPreview 保存初始化 StockItem 快照、展示模式和记录列表。InventoryPreviewStore 通过 Compose SnapshotStateMap 使追加操作触发刷新；键包含 cloud.scopeKey（服务地址、账号、家庭）及物品 ID，访客使用独立 local 作用域。

仓库属于 InventoryStore，关闭详情、切换物品、切换页面后仍可在同一 InventoryStore 会话取回预览。重组不会重复初始化。原始单件 ID 来自物品 ID 与序号，新增单件 ID 使用 UUID；同批记录共享另一个 UUID 批次 ID。

## 5. 不同有效期

一次入库的每条新增记录复制本次日期，不修改旧记录。先入库 2 件（11-10）再入库 3 件（11-20），得到 5 条独立记录，前 2 条和后 3 条分别保留各自日期。没有开封日期时显示“未登记”，没有有效期时显示“未设置”。

## 6. 保留与隐藏

保留编辑物品、消耗库存、数量记录和删除；编辑、消耗仍进入原有业务面板，删除仍使用原确认和同步逻辑。

详情中隐藏资料与盘点、开封/丢弃/询问这批、真实消费流水、盘点修正、加入清单/调整入口。对应组件、路由及业务实现仍保留。

## 7. 后端未对接部分

入库 + 只改会话预览，不调用 saveItem、changeQuantity、cloud.adjust 或创建物品接口。原库存、数量记录及清单不因预览入库变化。界面始终标注预览性质，并分别显示服务器/本机已保存数量。

没有预览入库时，原编辑或消耗后的库存可以重新初始化列表。有预览入库后，原数据变化只更新已保存数量和差异提示，保留单件快照；不擅自消耗或删除某条预览记录。单位改变后保留原预览单位并暂停继续入库，防止把不同单位相加。

## 8. 验证

执行命令（在 frontend/ 下，使用现有 JDK 21）：

```powershell
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug :app:connectedDebugAndroidTest '-Pandroid.testInstrumentationRunnerArguments.class=com.example.teamapp.InventoryPreviewUiTest,com.example.teamapp.InventoryDetailAnimationTest,com.example.teamapp.AppLanguageTest,com.example.teamapp.InventoryV02UiTest,com.example.teamapp.InventoryStoreTest' --console=plain
```

JVM 单元测试共 52 项，包括新增预览模型 9 项。UI 测试共 27 项，在 emulator-5554（Android 12）执行，覆盖 A–E 主要场景、实际日期选择、清除日期、快速双击、连续计量精度、原数据不变、原详情动画、编辑路由、中英文、浅深色和小屏滚动。

结果：Debug 构建成功，52 项单元测试与 27 项相关 UI 测试全部通过，0 失败、0 跳过。另将模拟器实际屏幕调整为 640×960px、320dpi（320×480dp）重跑新增 9 项 UI 测试，全部通过，结束后恢复原尺寸。小屏首轮有一项测试在详情关闭/物品切换动画期间触摸旧节点失败，增加等待与精确语义操作后复测通过，没有修改产品动画。git diff --check 通过。

Debug APK 位于 `frontend/app/build/outputs/apk/debug/app-debug.apk`；单元测试报告位于 `frontend/app/build/reports/tests/testDebugUnitTest/index.html`；完整 27 项 UI 报告保存在 `frontend/app/build/reports/inventory-preview/main-ui/index.html`；最后一次 9 项小屏测试报告位于 `frontend/app/build/reports/androidTests/connected/debug/index.html`。已人工检查浅色、深色及小屏详情、入库弹窗截图。Dialog 使用 safeDrawingPadding、imePadding 和内部滚动区域，底部操作固定在可视区域；Compose 测试输入服务没有完整复现真实系统输入法弹出过程，各真机输入法的遮挡情况仍需实机复核。

首次离线构建因原相机/OCR 等依赖未缓存失败；正常联网后已完成依赖解析。保留项目现有 AGP 9.1.1 对 compileSdk 37.1 的兼容性警告，未改构建配置或依赖版本。

## 9. 已知限制与第二阶段

- 数据只属于当前 InventoryStore 实例；应用重启、进程重建或重建该实例后丢失。尚未承诺配置变化后的恢复。
- 按件单位遵循已有模型中的盒、瓶、包、袋、个、卷、片、台，并兼容旧“件”。重量、体积、未知单位及非整数旧库存保留准确聚合数量，不四舍五入。
- 原型每个物品最多创建 10,000 条单件预览；更大的原始数量聚合展示，入库数量上限会提示。连续计量遵循现有 InventoryContract 的六位小数及数值范围。
- 本次“入库 +”始终绑定原 itemId，不新增卡片。历史上已经存在的同名不同 ID 物品不会按名字自动合并，以免混淆单位、位置和现有编辑/删除对象；第二阶段需明确产品身份、批次身份及旧数据合并规则。
- 云端单件创建、持久化、跨设备同步、消费分配、编辑传播及删除对账尚未实现。需先确定后端单件/批次标识与幂等协议、连续单位的模型、并发和版本校验，再接入真实操作及家庭权限测试。
- 本轮测试使用隔离访客存储，不执行真实云端写入；云端边界由调用关系及作用域隔离模型测试验证。
