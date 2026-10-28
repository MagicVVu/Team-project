# 物品详情布局与单件左滑交互交付记录

日期：2026-10-27。工作目录：`Team-project/`。分支：`dev`。

开始时工作区干净，上一阶段已提交为 `e8b964a`。本轮 `git fetch origin dev` 成功，本地与远程 dev 一致。在此基础上直接修改现有实现，没有新建另一套库存模型。

## 1. 文件与职责

| 文件 | 职责 |
| --- | --- |
| `frontend/app/src/main/java/com/example/teamapp/data/InventoryPreview.kt` | 增加单件资料更新、开封与消耗；本地修改快照保护；已处理入库批次集合 |
| `frontend/app/src/main/java/com/example/teamapp/ui/ring/InventoryDetailContent.kt` | 顶部全局编辑、底部添加/采购/删除；按作用域及物品管理展开记录与编辑目标 |
| `frontend/app/src/main/java/com/example/teamapp/ui/ring/InventoryPreviewRow.kt` | 新增原生水平拖动菜单、可访问性操作、退出动画及完成回调 |
| `frontend/app/src/main/java/com/example/teamapp/ui/ring/InventoryRecordEditor.kt` | 新增单件编辑弹窗，复用位置选择器及日期日历 |
| `frontend/app/src/main/java/com/example/teamapp/ui/ring/InventoryReceiveDialog.kt` | 将原日期选择组件开放给单件编辑复用；容错读取旧日期；保留原入库表单 |
| `frontend/app/src/main/res/values/ui_strings.xml` | 更新中文添加/提示文案及新增单件操作资源 |
| `frontend/app/src/main/res/values-en/ui_strings.xml` | 同步英文资源及按钮/可访问性描述 |
| `frontend/app/src/test/java/com/example/teamapp/InventoryPreviewTest.kt` | 增加 8 项单件存储边界测试，共 17 项 |
| `frontend/app/src/androidTest/java/com/example/teamapp/InventoryPreviewUiTest.kt` | 调整底部添加、采购入口及稳定 ID 标签测试，移除旧全局消耗/历史断言 |
| `frontend/app/src/androidTest/java/com/example/teamapp/InventoryRecordActionsTest.kt` | 新增 13 项手势、编辑、日期、动画时序、快点、空态、聚合保护、路由与云端缓存隔离测试 |
| `frontend/app/src/androidTest/java/com/example/teamapp/CloudUiIntegrationTest.kt` | 将已有可选云端 UI 测试的采购入口改为新稳定标签 |
| `docs/inventory-record-actions.md` | 本报告 |

已复核 RingInventoryPage 的展开/关闭状态机、MagicApp 的编辑/采购/删除路由及 QuantityAction、BatchOperationsPanel。上述产品宿主和全局业务组件没有修改。

## 2. 新布局

详情顶部继续由原宿主提供“详情 / 关闭”。物品图标、名称、分类右侧为全局“编辑”，仍调用 `open("编辑物品")`。

其后依次为前端预览数量、服务器/本机已保存数量、单件列表及操作说明。底部按顺序显示现有照片（有照片时）、全宽主按钮“添加”、次级按钮“加入购买清单”、危险操作“删除物品”。全局消耗、数量记录按钮及历史展开内容已移除，StockItem.history、其他页面和底层组件保留。

“添加”继续打开原 InventoryReceiveDialog；采购入口根据 store.purchases 进入原“加入采购清单”或“调整采购数量”，没有使用预览数量替代原采购计算。

## 3. 左滑手势与菜单

使用 Compose draggable 的 Horizontal 方向及原生触摸阈值，与 LazyColumn 垂直滚动协调。拖动值限制在 `[-菜单宽度, 0]`，菜单最大宽 216dp，小屏保留至少 48dp 前景区域。前景跟随手指，背景三个按钮固定在右侧，揭露程度由拖动量控制。

松手按 45% 菜单宽度阈值及 650dp/s 速度判断，使用无过冲的临界阻尼 spring 吸附。短慢滑返回；右滑或点击展开卡片主体关闭。

详情仅维护一个 expandedId，展开另一条时前一条关闭。选择编辑、开封或消耗会清除此 ID。详情内容以 store、scope、item.id 为 Compose key，换物品/家庭或退出详情会销毁相应手势状态；记录消失后清理无效展开/编辑 ID。隐藏的按钮不暴露到可访问性树，展开后才启用；另提供“显示/收起单件操作”的辅助功能动作。

## 4. 单件编辑

独立 InventoryRecordEditor 使用原 Choice 和 store.locations，不新增自定义位置规则或写入位置设置。有效期、开封日期可以保留、选择或清除；共享原入库日历。仅展示月份不会给空日期赋当天。

保存调用 `updateRecord(scope, itemId, recordId, location, expiryDate, openedAt)`，只 copy 三个可编辑字段，保留 id、itemId、batchId、source、quantity。新日期必须合法；未变动的旧日期文本可原样保留，不会静默丢弃。取消不调用存储更新。

## 5. 开封

`markOpened` 仅为目标 openedAt 为空的独立单件写入操作时的设备 `LocalDate.now()`。已有日期时返回无副作用，界面显示“已开封”并禁用。日期行使用主题主色提供轻量反馈；父级 openedAt、lifecycleStatus 不变。

## 6. 消耗与移除时序

消耗先将行标记为 removing，清除展开 ID，阻止该行再次操作。MutableTransitionState 从 true 变为 false，组合 300ms 渐隐和垂直收缩，以及 240ms、约行宽 10% 的轻微左移。退出过程包含行下方间距，避免留下空隙；相邻项使用 animateItem 的位置动画。

只有观察到 `isIdle && !currentState`，才调用 `consumeRecord`。没有用固定 delay 推测动画完成，设备动画时长缩放也由 Compose 处理。移除后由记录数重新计算数量；快速双击由行状态及存储层目标存在性双重保护。

如果退出动画尚未完成，该行就被 LazyColumn 回收或详情整体销毁，未完成的预览操作会取消并保留数据；不会在已离开的页面上猜测动画完成并扣减。之后重新操作该记录即可。这一行为优先避免误删，后续可增加跨列表回收的退出事务管理。

## 7. 身份、幂等和一致性

列表 key 和所有操作均使用稳定 record.id。列表编号仅用于显示，不参与操作定位。存储层通过 `(scope, itemId)` 寻找已存在的预览，再校验 record.id、record.itemId 和数量为 1，聚合模式拒绝所有单件操作。

locallyModified 在入库、单件编辑、开封、消耗后保留快照，父级资料变化不会重建列表或丢失批次日期。receivedBatchIds 独立于当前记录列表，某批最后一件被消耗后也不会让同批次 ID 再次入库。界面始终区分预览与已保存数量。

## 8. 前后端边界

本轮所有单件操作只更新现有 InventoryPreviewStore 的内存状态，不调用 saveItemSynced、changeQuantitySynced、QuantityAction 或批次开封/消费接口；不修改父级数量、历史、位置、日期、状态、云端缓存或持久化。

只有原有全局编辑、采购和物品删除入口继续使用各自原业务流程。连续计量、未知单位、非整数旧库存及超大库存保留精确聚合只读展示，不开放单件菜单。

## 9. 验证

在 frontend/ 下使用已有 JDK 21、Gradle Wrapper 和 Android 12 模拟器运行：

```powershell
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug :app:connectedDebugAndroidTest '-Pandroid.testInstrumentationRunnerArguments.class=com.example.teamapp.InventoryPreviewUiTest,com.example.teamapp.InventoryRecordActionsTest,com.example.teamapp.InventoryDetailAnimationTest,com.example.teamapp.AppLanguageTest,com.example.teamapp.InventoryV02UiTest,com.example.teamapp.InventoryStoreTest' --console=plain
```

单元测试共 60 项（预览模型 17 项）。UI 回归覆盖原入库、菜单阈值/关闭/单展开、垂直滚动、单件编辑和取消、清除日期、重复开封保护、动画中数据不删除与高度变化、双击防重、最后一件空态、聚合保护、真实全局编辑/采购保存、删除确认，以及原详情动画、双语主题。

云端模式使用隔离偏好文件中的虚构加密账号和库存缓存，直接挂载详情组件，不运行账号登录、远程刷新或真实写入。测试比较单件操作前后的导出、父库存及三个偏好文件，验证缓存、凭据和游客数据不变。可选 CloudUiIntegrationTest 仅更新入口并参与编译，没有连接真实云端执行它。

初轮 39 项 UI 回归有一处测试将原始缓存数量 3.0 错写为预期 3；修正断言后 39 项全部通过，未改产品数量精度。随后补入关闭重开测试与全局保存验证。

最终结果：Debug 构建成功；60 项 JVM 单元测试、40 项完整相关 UI 测试全部通过；模拟器实际调整为 640×960px、320dpi（320×480dp）后，22 项入库与单件 UI 测试再次全部通过。均无失败或跳过，测试后恢复 900×1600px 原尺寸。git diff --check 通过，变更仅限 Android 前端及本报告；没有后端、数据库、登录或家庭读取逻辑改动。本轮没有提交或推送。

构建和验证产物：

- APK：`frontend/app/build/outputs/apk/debug/app-debug.apk`
- JVM 报告：`frontend/app/build/reports/tests/testDebugUnitTest/index.html`
- 完整 40 项 UI 报告：`frontend/app/build/reports/inventory-record-actions/full-ui/index.html`
- 最后 22 项实际小屏 UI 报告：`frontend/app/build/reports/androidTests/connected/debug/index.html`
- 手工检查截图：`frontend/app/build/reports/inventory-record-actions/` 下的左滑菜单、单件编辑弹窗、消耗动画中间帧 PNG。

项目已有 AGP 9.1.1 对 compileSdk 37.1 的警告保留，未修改依赖或构建配置。

## 10. 限制与后续

- 单件信息仍只属于当前 InventoryStore 会话，不跨应用重启持久化。单件身份、消费分配、并发版本校验及跨设备同步需要后端协议后再接入。
- 行在退出完成前被回收/销毁时保留数据，尚无跨组件生命周期的退出事务恢复。
- 位置选择遵循现有 store.locations；本轮没有新增自定义位置输入流程。
- 原型单件上限仍为 10,000，连续计量遵守原精度和范围限制。历史同名不同 ID 不自动合并。
- 软键盘避让沿用 safeDrawingPadding、imePadding、可滚动表单及固定底部操作；Compose 输入服务不能完整替代各真实输入法，真机多输入法遮挡仍需复核。
- 本轮不接入服务器单件编辑、开封或消费事件，不新增后端字段、接口或迁移。
