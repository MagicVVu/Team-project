# Mewstow V1 品牌接入

更新日期：2026-10-17。

## 已应用的命名

- 应用显示名称：**Mewstow**，替换原来的“拾物”。
- 角色正式英文名称：**Nekomata**，中文物种名“猫又”保留。
- 角色日常昵称：**Mew**，用于首页、登录欢迎语、对话标题与消息署名。
- 关于页面展示“猫又 Nekomata · 昵称 Mew”。
- 采用用户确认的 **V1 不连写字标**，包含猫耳 M、盒形 o、双尾 w。

## 已替换的位置

1. 应用桌面名称、系统应用名称与桌面猫盒图标。
2. 登录和注册页顶部字标、登录标题、陪伴文案及角色辅助说明。
3. 浅色和深色首页顶部字标、品牌图形和助手名称。
4. 助手展开页、对话介绍、助手消息署名。
5. 个人中心的关于入口、深色品牌页脚、关于页字标与角色名称。
6. 数据导出的建议文件名、系统分享反馈的品牌标题。

字标使用独立透明 PNG，保持比例。深色背景使用奶油色衬底，以保留 V1 的两种绿色和尾巴细节。桌面图标使用猫盒图形，不把完整英文挤进图标；自适应前景保留中央安全区域，同时提供旧系统的五档密度图标和主题单色层。

### 顶栏调整 V2

按用户反馈，首页删除字标前方独立猫盒图形，字标从顶栏左侧 18dp 内边距开始，向左移动原图形与间距占用的 36dp。浅色首页使用沿字形轮廓的约 1dp 奶油白细描边，以区分绿色字标与绿色背景；不改变 V1 字母结构。深色首页仍使用原来的奶油色衬底。库存、清单、我的页面保留功能图标，提醒按钮位置和 56dp 顶栏高度保持一致。

顶栏调整后重新构建成功，浅色和深色两项下拉助手/顶栏导航检查通过，Lint 为 0 错误、35 条工程现有建议。新的截图、前后对比和安装包保存在下述交付目录的 `顶栏调整V2` 子目录，根目录中的首次品牌接入版保留用于对照。

现有 Android 项目没有独立的自定义开屏页面，本次没有插入等待或新增开屏流程。系统启动时使用新应用图标，登录入口显示 V1 完整字标。

## 源码与素材位置

| 内容 | 路径（相对 frontend） |
| --- | --- |
| 显示名称与正式名称资源 | `app/src/main/res/values/strings.xml` |
| 共用字标与品牌图形组件 | `app/src/main/java/com/example/teamapp/ui/AppBrand.kt` |
| 顶栏 | `app/src/main/java/com/example/teamapp/ui/AppHeader.kt` |
| 登录注册 | `app/src/main/java/com/example/teamapp/ui/AuthScreen.kt` |
| 两种首页、个人中心、对话介绍 | `app/src/main/java/com/example/teamapp/ui/LightDesign.kt`、`DarkDesign.kt` |
| 下拉助手名称 | `app/src/main/java/com/example/teamapp/ui/AssistantPullLayer.kt` |
| 对话署名与面板标题 | `app/src/main/java/com/example/teamapp/ui/MagicApp.kt` |
| 关于、导出和反馈 | `app/src/main/java/com/example/teamapp/ui/SettingsPanel.kt` |
| 透明字标与图形 | `app/src/main/res/drawable-nodpi/mewstow_*.png` |
| 自适应图标 | `app/src/main/res/mipmap-anydpi-v26/ic_launcher*.xml` |
| 旧版桌面图标 | `app/src/main/res/mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/ic_launcher*.webp` |
| 已确认 V1 图、源素材、提示词 | `../docs/ui/branding/Mewstow/` |
| 资源尺寸适配脚本 | `tools/prepare_brand_assets.py` |

## 如何运行

Android Studio 打开 **`E:\TM_code\Team-project\frontend`**，选择 `app` 和 MuMu 设备后运行。

本次本机验证使用：

```powershell
$env:JAVA_HOME = 'D:\Android Studio\jbr'
.\gradlew.bat :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

安装包输出：`app/build/outputs/apk/debug/app-debug.apk`。

MuMu 已通过原包名 `com.example.teamapp` 更新安装。当前界面代码、库存本机存储键名、数据库/缓存、服务器接口及登录认证均沿用原标识；没有修改用户库存，也没有清除应用数据。

## 如何再次替换字标

1. 保留名称 `mewstow_wordmark.png`，用新的透明主字标替换 `drawable-nodpi` 下的同名资源。
2. 保留猫耳和尾巴的透明边距；字标组件按原比例适配，不强行拉伸。
3. 需要重新封装所有图标时，将确认的透明源图放入 `../docs/ui/branding/Mewstow/wordmark-source.png` 和 `launcher-source.png`，使用带 Pillow 的 Python 运行 `tools/prepare_brand_assets.py`。
4. 重新构建并运行应用。普通文字称呼在对应页面及 `strings.xml` 中修改，不需要改包名。

## 验证结果

- Debug APK 构建成功。
- 17 项本地单元测试通过。
- MuMu Android 12（API 32）上 7 项现有界面测试通过，包括浅色/深色首页、登录注册、关于页面和下拉助手；测试数据使用独立偏好文件。
- Lint：0 个错误；剩余为工程现有配置、旧 API/依赖或代码建议。本次新增组件的 Modifier 与未使用资源提示已修正。
- APK 元数据显示名已通过 `aapt dump badging` 确认是 Mewstow，包名仍是 `com.example.teamapp`。
- 桌面布局中已找到 Mewstow 名称。
- 实际截图已检查字标完整性、浅深背景显示、Mew/Nekomata 命名和关于入口。

MuMu 运行截图、检查结果 JSON 和便于安装的 APK 副本位于：

`E:\1-大三上\团队项目\UI设计稿\Mewstow品牌设计\Android接入版-20261017\`

本次没有重新验证云端后端、相机识别或真实语音服务，因为品牌替换没有改变这些逻辑。旧的圆环原型截图与历史说明继续保留原名称，不能用来判断当前应用显示名。所有修改仅在本机，未提交或推送 GitHub。

Android 自适应图标的尺寸和资源引用按[官方说明](https://developer.android.com/develop/ui/compose/system/icon_design_adaptive)配置。
