# 库存详情展开动画实现报告

日期：2026-10-24。范围：Android / Jetpack Compose 库存页面。未提交或推送 Git，未修改后端、数据库、同步协议或已有物品响应动画参数。

## 1. 原有页面架构

- `MagicApp.kt` 用 Scaffold 预留顶部、云端状态及底部导航的位置，通过 AnimatedContent 切换主页面；原物品详情、编辑和数量操作共用 ModalBottomSheet。
- `RingInventoryPage.kt` 原来使用整页 verticalScroll；`StockRingBrowser.kt` 用 Canvas 缓存扇形 Path 绘制圆环，普通 Compose 组件叠加图标、文字、分类和预览卡片。
- `selectedId` 是浏览器的可保存选择状态；`position`、`dragPosition`、`interacting` 管理原有浏览动画。选择通过物品 ID 对齐，拖动期间冻结排序。
- 原有物品响应：位置弹簧 dampingRatio=0.92、stiffness=420；扇形突出使用原来的 160ms、12dp 位移和 1.12 倍缩放。上述参数、路径和选中算法保留。
- 左下角 `RingInfoCard` 已独立封装。真实数据来自 `InventoryStore.items` 中的 `StockItem`，游客持久化与家庭云端库存共用该入口，无需新增 Repository 或业务模型。
- 现有 `Detail` 已有删除确认与真实删除操作；编辑、入库、消耗和采购计划继续使用原有页面路由。

## 2. 实现的动画阶段

1. 保留原有扇形选择与拖动响应。点击未选中的模块仅执行选择；运动中的点击继续选择，不打开详情。稳定选中后再次点击模块，或点击可用的预览卡片，才展开详情。
2. 点击展开后，卡片展开与背景、圆环淡化在同一帧同时启动，不再等待聚焦完成。180ms 内圆环缩至 0.975；非选中扇形及背景弱化至约 0.72。使用图层和绘制参数，未改变圆环测量尺寸。
3. 预览卡片沿实际布局边界扩展为详情卡片；弹簧 dampingRatio=0.88、stiffness=Spring.StiffnessMediumLow，圆角由 18dp 过渡到 24dp。
4. 展开达到 68% 后，身份、数量状态、位置有效期、操作历史四组内容分别渐入，间隔 50ms，单组 160ms、12dp 短位移。
5. 关闭先将内容淡出，再用 260ms 将卡片缩回当前预览位置，同时恢复圆环。动画结束才删除浮层。

## 3. 文件清单

生产代码：

- 修改 `frontend/app/src/main/java/com/example/teamapp/ui/ring/RingInventoryPage.kt`：页面内浮层、测量坐标、状态机、动画和返回处理。
- 修改 `frontend/app/src/main/java/com/example/teamapp/ui/ring/StockRingBrowser.kt`：二次点击规则、移除扇形和预览卡片波纹、视觉聚焦、有限高度布局及短屏紧凑排布。
- 新增 `frontend/app/src/main/java/com/example/teamapp/ui/ring/InventoryDetailContent.kt`：基于真实 StockItem 的详情展示和分组动画入口。
- 修改 `frontend/app/src/main/java/com/example/teamapp/ui/MagicApp.kt`：复用 Detail 删除逻辑和原操作路由；详情显示期间暂时收起会遮挡关闭按钮的 AI 拉绳，关闭后恢复。
- 修改 `frontend/app/src/main/java/com/example/teamapp/ui/ring/RingInventoryTestPage.kt`：给滚动调试宿主中的共用浏览器提供有限高度，保持原调试功能可用。

测试与交付：

- 新增 `frontend/app/src/androidTest/java/com/example/teamapp/InventoryDetailAnimationTest.kt`。
- 更新 `InventoryV02UiTest.kt`、`LightDesignTest.kt`、`DarkDesignTest.kt`、`MagicAppTest.kt`、`MotionBehaviorTest.kt`、`CloudUiIntegrationTest.kt` 中依赖库存整页滚动或旧详情结构的断言。未运行依赖真实服务器的云端写入测试。
- 本报告和 `reports/inventory-detail-animation/` 中的验证日志与截图。

## 4. 状态管理

动画阶段只有一个枚举：Idle → Expanding → Expanded → Collapsing → Idle。Expanding 阶段并行运行聚焦和卡片展开，详情内容仍在展开达到 68% 后依次进入。

详情仅保存稳定 ID，每次重组都从共享库存重新取得真实物品；不复制可变业务对象。浮层显示期间屏蔽底层圆环、筛选和预览卡片的输入与语义，快速点击不会产生多个详情层。切换主页面后停止动画、清除浮层，原有可保存选择和筛选仍保留。

LaunchedEffect 管理可取消动画，rememberCoroutineScope 仍管理原有浏览动画。物品删除导致 ID 无法解析时，安全清理浮层和聚焦状态。详情状态不跨页面销毁保存，避免返回页面时残留半展开的卡片。

## 5. 展开与关闭实现

`onGloballyPositioned / boundsInRoot` 取得预览与库存宿主的实际坐标，相减后在库存页面自己的坐标空间插值。目标宽度为页面可用宽度减去左右各 16dp，高度为可用页面高度的 80%。Scaffold 已扣除系统和主导航占用空间，不硬编码设备像素位置。

逐帧只重新测量浮层边界；详情内容从开始就使用最终宽度排版，以裁切和透明度衔接，避免文字随卡片宽度反复换行。源预览保留测量但隐藏绘制，浮层绘制无交互的视觉副本，避免重复卡片。关闭按钮、卡片外点击和系统返回共用同一收起逻辑；中途返回从当前进度反向关闭。

库存主页面已移除 verticalScroll，圆环视口使用父布局剩余高度，搜索、分类、预览、浏览控件及图例在一页内排布。短视口使用两列分类和紧凑预览；详情内的长文本、照片、操作和历史可以独立滚动，固定关闭按钮始终保留。

Compose 动画时钟处理系统 animator duration scale，包括设为 0 时跳过动画；延迟使用 tween 的 delayMillis，没有额外不可缩放的固定协程等待。

## 6. 图标过渡

详情和圆环使用同一 `RingItemIllustration`，保持图标与颜色一致。已实现预览卡片视觉副本与正式详情图标的渐变衔接。未实现从 Canvas 扇形位置飞到详情顶部的独立共享元素轨迹，避免改写已有扇形响应和几何绘制。

## 7. 业务对接

展示真实名称、分类、数量、单位、最低库存、状态、有效期、位置、已有照片和数量历史。缺少有效期显示“未设置”；现有模型没有备注字段，因此不伪造备注。

编辑、入库、消耗、加入/调整采购计划在反向动画结束后打开现有业务面板；删除仍通过原 Detail 的确认对话框和 `deleteItemSynced`。已有编辑保存后的普通详情面板行为继续沿用，没有新增业务导航系统。

## 8. 编译和测试

实际执行环境：现有 Windows JDK / Android SDK；已连接的 `emulator-5554`，Android 12 / API 32，900×1600，密度 320。测试使用独立的游客偏好文件，没有使用生产账号或写入共享云端库存。

| 检查 | 结果 |
| --- | --- |
| `:app:assembleDebug` | 成功，生成 `frontend/app/build/outputs/apk/debug/app-debug.apk` |
| `:app:testDebugUnitTest` | 32 项通过，0 失败 |
| `:app:lintDebug` | 0 错误、26 条警告；警告未涉及本次新增的动画组件，未扩大范围升级 SDK / 插件或依赖 |
| 相关 `:app:connectedDebugAndroidTest` | 30 项通过，0 失败；覆盖 InventoryDetailAnimationTest、InventoryV02UiTest、MagicAppTest、LightDesignTest、MotionBehaviorTest、RingPrototypeTest |
| 系统 `animator_duration_scale=0` | 另运行 4 项测试，全部通过；结束后恢复模拟器原设置 1.5 |
| `git diff --check` | 通过 |

同时启动微调后的补充验证：再次执行 `:app:assembleDebug` 和 `InventoryDetailAnimationTest` 的 8 项模拟器测试，全部通过。实测起点检查仍保留，并将展开检查提前到 80ms，确认卡片立即开始扩展。日志见 `reports/inventory-detail-animation/simultaneous-opening.log`。

新增测试涵盖：未选中模块先选择、选中模块再次点击展开、浅深色、重复打开关闭、背景及返回键关闭、快速操作与展开中返回、浮层唯一性、预览实测起点、展开中删除、详情中真实数据更新及删除、切换主页面、复用编辑表单、长名称与缺省有效期、360×640 约束下的一屏布局、420×280 短视口配合 1.5 倍字体及组件销毁。

已检查浅深色详情及普通库存、小屏、短视口截图。短视口测试是实际设备上的 Compose 约束尺寸测试，不等同于物理旋转设备或折叠屏测试。未执行实体手机验收。

验证记录：`reports/inventory-detail-animation/verification.log`、`device-tests.xml`、`verification-summary.json`、`lint-results-debug.txt`、`reduced-motion.log`。截图位于同目录。构建仍提示工程原有的 AGP 9.1.1 对 compileSdk 37.1 的兼容性警告，未阻止构建。

## 9. 未实现与限制

- 未增加可选的向下拖动关闭，已提供关闭按钮、背景点击和 Android 返回键。
- 未实现独立图标飞行共享元素轨迹。
- 极端长名称在库存预览中沿用省略显示，完整文本在详情中换行。短屏会省略辅助性的滑动提示，筛选和浏览控件仍保留。
- 未进行实体手机验收或 60FPS / 内存的专业性能采样；不能将模拟器功能测试等同于真机性能结论。
- 编辑与数量表单保持原面板形式，编辑保存后仍进入项目既有的普通详情面板。

## 10. 后续优化方向

可按实际真机结果微调聚焦与展开节奏，增加 Macrobenchmark / JankStats 采样；在不改变扇形绘制与原有反馈的前提下增加可选的图标轨迹。进一步覆盖折叠屏、多窗口、最大字体和不同厂商的返回手势。
