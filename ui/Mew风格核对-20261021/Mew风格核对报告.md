# Mew 风格全项目核对

日期：2026-10-21（Asia/Shanghai）。代码基准：`5b29d8bc7207ec4b1c234487de2926ac28e3810b`，并复核审阅时的工作区。

检查期间工作区的 AppBrand.kt 与品牌接入说明另有未提交更新：深色字标改为提亮双色、取消奶油矩形底。已重读这些变化；它们不改变角色素材引用与本报告的三套角色混用结论。本次没有编辑这两个文件。

结论：确实存在风格混用。当前角色至少混用了 **旧版立体有脚猫、新版无脚盒子猫、拉绳挂件变体** 三套表现；此外还有一套经过确认的简化品牌标志。主要问题是不同角色代际混用，并非正常的表情变化。

本次只新增核对报告，没有替换角色、修改应用源码、安装应用或改动用户数据。

## 核对范围与证据口径

- 检查当前 Android 主源码的36个 Kotlin 文件，记录41处相关定义、调用或直接图片引用；41处不等于41个页面。
- 对 drawable-nodpi 中17张相关资源记录尺寸、SHA-256、代码引用和同源路径。其中13张是角色图／分层图，4张是字标／品牌图形。
- 核对最终版目录23张PNG：21张独立状态 + 2张透明总图；检索836个PNG候选路径进行同源定位，并查看关键原图、总图和既有浅深设计总览。未声称逐张人工审阅836张历史截图。
- 页面可达性依据当前代码路由。历史设计稿、归档ZIP、截图、仅声明资源与当前运行入口分开记录。
- 本次不登录云端、不逐页运行设备测试；现象通过当前源码、原图、哈希同源和既有截图交叉核对。HTML里的素材展示是文件预览，不是新拍的App截图。

## 四类视觉来源

| 类别 | 来源／特征 | 当前使用 | 判断 |
| --- | --- | --- | --- |
| A 旧角色 | maoyou_states.png + maoyou_welcome.png；绿脚、渐变箱体、粗壮奶油尾，部分状态蓝／紫箱盖 | 浅色登录、首页、底栏、我的、清单、空态、添加导语、游客AI | 与已确认V14造型冲突，是主要替换对象 |
| B 已更新角色 | V14十二场景 + V16展开收起；无脚、低宽奶白盒、绿白双尾、绿尾尖、较平面描边 | 当前主要接在DarkMaoYou，只有少数姿态 | 建议作为普通角色统一基准；透明导出须复核 |
| C 拉绳变体 | V04挂件；棕色粗描边、歪头、尾巴缠麻绳，六层PNG | 两主题的库存／清单／我的右上角 | 特殊动作允许，需与B统一五官和线条，不应随便废弃已确认结构 |
| D 品牌符号 | 已确认Mewstow V1字标／无脸猫盒图标；橄榄绿与奶油色 | 字标、桌面自适应图标等 | 功能性简化允许，不能因为没眼睛就判为错误；保持V1确认版 |

## 全部问题与建议顺序

P1先统一身份；P2统一各入口与素材质量；P3统一维护方式。

| 级别 | 编号 | 问题 | 核实到的现状 | 建议 | 证据 |
| --- | --- | --- | --- | --- | --- |
| P1 | 01 | 浅色与深色使用了不同代角色 | 浅色两张主图与旧“猫又圆环版/IP素材”逐字节相同；深色五张与最终版单张逐字节相同。旧版有绿色小脚、立体箱体和整段奶油尾；新版无脚、低宽身体、绿尾尖。 | 以 V14 已确认造型为普通状态母版，先替换浅色旧图；深色沿用同一角色资产，背景主题单独变化。 | [LightDesign.kt:88](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:88)；[DarkDesign.kt:67](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:67) |
| P1 | 02 | 拉绳猫与展开后的助手头像不是同一套 | 拉绳是 V04 独立分层挂件，棕色粗描边、倾斜脸型；展开后浅色又使用旧欢迎猫，深色使用新版思考猫。 | 保留已确认的麻绳、双尾缠绕结构与动作；统一角色线宽、描边色、五官比例，并让展开后的普通猫接上同一身份。 | [AssistantPullMascot.kt:28](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/AssistantPullMascot.kt:28)；[AssistantPullLayer.kt:288](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/AssistantPullLayer.kt:288) |
| P2 | 03 | 相同页面的表情语义没有对应 | 登录、注册、个人头像、AI 顶图在两主题下并非同一状态；旧空态蓝盖、旧思考紫盖与新稿状态系统也不同。 | 先定义 Welcome / Listening / Confirming / Thinking / Shopping / Empty 等语义，再为两主题绑定同一个状态。表情可变，不能随主题换物种般的形体。 | [AuthScreen.kt:100](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/AuthScreen.kt:100)；[LightDesign.kt:396](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:396)；[LightDesign.kt:443](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:443) |
| P2 | 04 | 底部首页入口的识别符号不同 | 浅色是旧版小猫头像，深色是房子线稿。 | 两主题统一为同一导航符号；若保留 Mew 图标，用同一版适合小尺寸的简化形象。不要一边猫、一边房子。 | [LightDesign.kt:131](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:131)；[DarkDesign.kt:83](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:83) |
| P2 | 05 | 页面角色覆盖随主题变化 | 拍照语音导语、游客清单顶部在浅色有猫，深色没有；关于页恰好相反，仅深色有猫。 | 按页面用途确定是否出现角色，再让浅深色具有一致的品牌层级；不必每页都堆满猫。 | [AddFlow.kt:91](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/AddFlow.kt:91)；[LightDesign.kt:341](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:341)；[SettingsPanel.kt:125](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/SettingsPanel.kt:125) |
| P2 | 06 | 游客与云端 AI 的品牌入口不同 | Chat 登录云端后提前返回 CloudAssistant，因此游客专属 DesignChatIntro 不会出现。下拉外层仍有 Mew 头像。 | 复用一个小型品牌头部／头像入口，保留云端任务卡、确认、安全和业务能力差异，不为视觉统一重写业务。 | [MagicApp.kt:263](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/MagicApp.kt:263)；[CloudAssistant.kt:20](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/CloudAssistant.kt:20) |
| P2 | 07 | 空状态和加载状态没有独立语义规范 | 通用空态、采购空态、空会话各用不同猫／闭盒；失败开盖空盒 C-01 和 V16 展开过程停留在设计素材。 | 区分空库存、搜索无结果、空清单、AI 等待、加载失败；按用户已确认的“加载晃盒／成功显现／失败开盖空盒”单独定义。当前圆环分类区保持不变。 | [LightDesign.kt:434](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:434)；[DarkDesign.kt:339](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:339)；[MagicApp.kt:116](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/MagicApp.kt:116) |
| P2 | 08 | 最终版素材有库但未统一使用 | 21 张独立状态中，仅 5 张原样复制到 Android，另外 2 张是总图；深色 voice / confirmed 只在资源选择器中声明，没有实际页面调用。 | 清晰标记“在用／仅配置／待接入／历史稿”，按语义接入缺口；不把目录名“最终版”当成已全部应用。 | [DarkDesign.kt:67](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:67)；[LightDesign.kt:88](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:88) |
| P2 | 09 | 部分透明导出有残边和光晕 | V16 透明总图可见大片灰绿／橙色半透明背景；部分单张边缘仍有灰绿色残留，尤其在深灰底明显。 | 从原始 V14/V16 重做干净透明边缘并双底核对，保留眼睛和黑色轮廓。不要全图染绿、直接降整只猫透明度或粗暴去掉所有浅色。 | E:\TM_code\Team-project\ui\猫又IP-最终版-透明PNG\00-八个展开收起姿态-透明总图V16.png |
| P2 | 10 | 可见角色大小没有统一口径 | welcome 使用整张1254画布；MaoYou 裁十二宫格；DarkMaoYou 裁512画布；同为88dp也不代表可见脸／身体一样大。 | 制定头像、导语、空态、挂件的可见身体尺寸和安全边距，以身体基准对齐，不按原始画布宽度机械缩放。 | [LightDesign.kt:88](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:88)；[DarkDesign.kt:67](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:67)；[AssistantPullLayer.kt:288](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/AssistantPullLayer.kt:288) |
| P3 | 11 | 角色接口分裂且状态用数字表示 | MaoYou(Int)、DarkMaoYou(String)、AssistantPullMascot(Boolean) 分开；state=3/8/9/10 与用途只能人工记忆。 | 建立一个语义状态枚举和角色资源映射；普通插画统一入口，拉绳作为保留分层的特殊表现，避免页面各自找图片。 | [LightDesign.kt:88](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:88)；[DarkDesign.kt:67](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:67)；[AssistantPullMascot.kt:28](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/AssistantPullMascot.kt:28) |
| P3 | 12 | 文件命名和配置容易让后续误用 | dark_maoyou_* 实际是最终版原色角色，不是必须只给深色；拉绳素材JSON推荐96dp，代码已按用户要求缩到57.6dp；示例弹簧参数与实际实现不同。历史页面仍含旧品牌名。 | 补一份唯一的素材登记表和场景映射；以用户确认后的代码参数为准同步文档。旧稿归为历史参考，先不删除，品牌 V1 与角色迭代分别标注。 | [AssistantPullMascot.kt:28](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/AssistantPullMascot.kt:28)；E:\TM_code\Team-project\ui\猫又拉绳-分层素材V01\素材配置.json |

## 当前页面逐项清单

| 编号 | 位置 | 浅色 | 深色 | 结论／边界 | 源码 |
| --- | --- | --- | --- | --- | --- |
| 01 | 登录 | 旧十二宫格 state=3，100dp | 新版 home，100×86dp | 已确认：同一入口换主题就换形体 | [AuthScreen.kt:100](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/AuthScreen.kt:100) |
| 02 | 注册 | 旧十二宫格 state=8（爱心成功） | 仍使用新版 home | 造型不一致；注册表情与深色不对应 | [AuthScreen.kt:100](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/AuthScreen.kt:100) |
| 03 | 首页欢迎区 | 旧 maoyou_welcome，94dp | 无同布局欢迎猫，合入深色助手卡 | 布局差异允许，但旧形体仍与新版冲突 | [LightDesign.kt:153](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:153)；[DarkDesign.kt:133](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:133) |
| 04 | 首页 AI 管家卡 | 旧 state=3，60dp | 新版 home，96×86dp | 同角色的体型、脚、尾尖、画风不同 | [LightDesign.kt:157](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:157)；[DarkDesign.kt:133](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:133) |
| 05 | 底栏首页图标 | 旧 state=3 小猫，30dp | home 房子线稿，24dp | 同一个导航入口换了识别符号 | [LightDesign.kt:131](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:131)；[DarkDesign.kt:83](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:83) |
| 06 | 库存／清单／我的拉绳入口 | 六层拉绳挂件，宽57.6dp | 同一挂件，同一原色 | 两主题一致；与普通猫的描边、脸型仍有偏差 | [AssistantPullMascot.kt:28](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/AssistantPullMascot.kt:28) |
| 07 | 下拉 AI 顶部头像 | 旧 maoyou_welcome，88dp | 新版 thinking，88dp | 刚拉下的新挂件又变成旧猫；两主题表情也不同 | [AssistantPullLayer.kt:288](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/AssistantPullLayer.kt:288) |
| 08 | 首页弹出 AI：游客介绍区 | 旧 state=10（紫盖思考），61dp | 没有对应的介绍猫 | 头像品牌组件与主题未统一 | [LightDesign.kt:443](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:443)；[MagicApp.kt:263](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/MagicApp.kt:263) |
| 09 | 游客 AI 空对话 | 旧默认空态 state=9（蓝盖） | 新版闭盒 empty | 同一空会话的形态和故事含义不同；下拉入口 showIntro=false 不走此分支 | [MagicApp.kt:263](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/MagicApp.kt:263)；[LightDesign.kt:434](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:434)；[DarkDesign.kt:339](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:339) |
| 10 | 云端 AI：首页面板 | CloudAssistant 不含角色插画／头像 | 同一 CloudAssistant | 游客有 Mew 介绍，云端走独立文字／任务卡界面；属于品牌覆盖差异 | [MagicApp.kt:263](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/MagicApp.kt:263)；[CloudAssistant.kt:20](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/CloudAssistant.kt:20) |
| 11 | 云端 AI：下拉入口 | 外层头像仍为旧欢迎猫 | 外层头像仍为新版思考猫 | 云端内层无插画，不代表下拉入口完全没有 Mew | [AssistantPullLayer.kt:288](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/AssistantPullLayer.kt:288)；[CloudAssistant.kt:20](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/CloudAssistant.kt:20) |
| 12 | 我的／个人头像 | 旧 state=8 爱心猫，73dp | 新版 home，70×64dp | 形体与表情都不对应 | [LightDesign.kt:396](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:396)；[DarkDesign.kt:300](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:300) |
| 13 | 游客采购清单顶部 | 旧 state=7 采购猫，67dp | 没有对应顶部猫 | 浅色有角色化导语，深色为列表标题 | [LightDesign.kt:341](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:341)；[DarkDesign.kt:262](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:262) |
| 14 | 游客采购清单空态 | 旧 state=7（采购道具猫） | 新版闭盒 empty | 采购空态是否用道具猫可讨论，必须先统一角色形体 | [LightDesign.kt:341](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:341)；[DarkDesign.kt:339](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:339) |
| 15 | 云端清单／购买历史空态 | 共用 Empty → 旧蓝盖空态 | 共用 Empty → 新版闭盒 | 云端清单也受到同一浅深形体分裂影响 | [CloudPanels.kt:99](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/CloudPanels.kt:99)；[MagicApp.kt:181](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/MagicApp.kt:181) |
| 16 | 拍照／语音添加导语 | 旧 state=2 信息确认／state=1 倾听，67dp | 没有对应角色导语 | voice / confirmed 新资源虽配置，未见页面调用 | [AddFlow.kt:91](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/AddFlow.kt:91)；[DarkDesign.kt:67](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:67) |
| 17 | 首页等共用空状态 | 旧 state=9 蓝盖空盒猫，91dp | 新版 B-01 闭盒，72×60dp | 布局、视觉尺寸与空状态含义不一致 | [LightDesign.kt:434](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:434)；[DarkDesign.kt:339](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/DarkDesign.kt:339) |
| 18 | 关于 Mewstow | 字标和文字，没有角色插画 | 新版 home 插画，高145dp | 角色介绍页只在深色显示 Mew | [SettingsPanel.kt:125](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/SettingsPanel.kt:125) |
| 19 | 当前圆环库存中心／空态 | 中心是分类；无结果为半透明文字卡 | 同样为分类和文字卡 | 符合用户已确认方案，不应为了统一而把猫塞回分类位置 | [MagicApp.kt:116](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/MagicApp.kt:116) |
| 20 | 启动／加载成功／失败分支 | 未发现 V16/C-01 接入 Android | 同样未发现接入 | 属于已有设计素材、尚未接入；不是已运行的加载动画 | [AppBrand.kt:29](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/AppBrand.kt:29) |
| 21 | 遗留 DesignInventory / InventoryRing | 中心仍有旧 MaoYou(76dp) | DarkInventory 是旧列表实现 | 当前主库存路由不调用这两套旧库存页，勿计为现用入口 | [LightDesign.kt:271](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/LightDesign.kt:271)；[MagicApp.kt:116](E:/TM_code/Team-project/frontend/app/src/main/java/com/example/teamapp/ui/MagicApp.kt:116) |

## 已确认的资源同源关系

文件SHA-256完全相同，以下不是仅凭肉眼猜测：

| Android资源 | 像素尺寸 | 完全相同的源文件 |
| --- | --- | --- |
| dark_maoyou_confirmed.png | 512×512 | E:\TM_code\Team-project\ui\猫又IP-最终版-透明PNG\A-03-信息确认.png |
| dark_maoyou_empty.png | 512×512 | E:\TM_code\Team-project\ui\猫又IP-最终版-透明PNG\B-01-小盒子轻晃.png |
| dark_maoyou_home.png | 512×512 | E:\TM_code\Team-project\ui\猫又IP-最终版-透明PNG\B-07-完整猫又回应.png |
| dark_maoyou_thinking.png | 512×512 | E:\TM_code\Team-project\ui\猫又IP-最终版-透明PNG\A-11-AI思考.png |
| dark_maoyou_voice.png | 512×512 | E:\TM_code\Team-project\ui\猫又IP-最终版-透明PNG\A-02-录入倾听.png |
| maoyou_pull_body.png | 600×768 | E:\TM_code\Team-project\ui\猫又拉绳-分层素材V01\02-小猫双尾绳结-底层.png |
| maoyou_pull_eyes_closed.png | 600×768 | E:\TM_code\Team-project\ui\猫又拉绳-分层素材V01\04-眼睛-闭眼.png |
| maoyou_pull_eyes_open.png | 600×768 | E:\TM_code\Team-project\ui\猫又拉绳-分层素材V01\03-眼睛-睁眼.png |
| maoyou_pull_mouth_idle.png | 600×768 | E:\TM_code\Team-project\ui\猫又拉绳-分层素材V01\05-嘴巴-待机.png |
| maoyou_pull_mouth_smile.png | 600×768 | E:\TM_code\Team-project\ui\猫又拉绳-分层素材V01\06-嘴巴-开心.png |
| maoyou_pull_rope.png | 104×65 | E:\TM_code\Team-project\ui\猫又拉绳-分层素材V01\01-麻绳-循环纹理.png |
| maoyou_states.png | 1448×1086 | E:\1-大三上\团队项目\UI设计稿\猫又圆环版\IP素材\猫又-十二状态与配色.png |
| maoyou_welcome.png | 1254×1254 | E:\1-大三上\团队项目\UI设计稿\猫又圆环版\IP素材\猫又-新版基础形象.png |

## 最终版状态接入情况

“原样资源匹配”只说明图片被复制进Android，不代表页面已经调用，更不代表已经做了动画。

| 最终版文件 | Android同源资源 | 使用状态 |
| --- | --- | --- |
| 00-八个展开收起姿态-透明总图V16.png | — | 未发现原样复制到Android资源；总图为核对用 |
| 00-十二场景表情-透明总图V14.png | — | 未发现原样复制到Android资源；总图为核对用 |
| A-01-新手引导.png | — | 未发现原样复制到Android资源；总图为核对用 |
| A-02-录入倾听.png | dark_maoyou_voice.png | 仅配置、未见页面调用 |
| A-03-信息确认.png | dark_maoyou_confirmed.png | 仅配置、未见页面调用 |
| A-04-首页概览.png | — | 未发现原样复制到Android资源；总图为核对用 |
| A-05-临期提醒.png | — | 未发现原样复制到Android资源；总图为核对用 |
| A-06-过期提醒.png | — | 未发现原样复制到Android资源；总图为核对用 |
| A-07-补货提醒.png | — | 未发现原样复制到Android资源；总图为核对用 |
| A-08-采购计划.png | — | 未发现原样复制到Android资源；总图为核对用 |
| A-09-操作成功.png | — | 未发现原样复制到Android资源；总图为核对用 |
| A-10-空白状态.png | — | 未发现原样复制到Android资源；总图为核对用 |
| A-11-AI思考.png | dark_maoyou_thinking.png | DarkMaoYou当前有调用 |
| A-12-异常重试.png | — | 未发现原样复制到Android资源；总图为核对用 |
| B-01-小盒子轻晃.png | dark_maoyou_empty.png | DarkMaoYou当前有调用 |
| B-02-偶尔露眼耳.png | — | 未发现原样复制到Android资源；总图为核对用 |
| B-03-点击后长大.png | — | 未发现原样复制到Android资源；总图为核对用 |
| B-04-猫耳探出.png | — | 未发现原样复制到Android资源；总图为核对用 |
| B-05-原有五官显现.png | — | 未发现原样复制到Android资源；总图为核对用 |
| B-06-小手双尾伸展.png | — | 未发现原样复制到Android资源；总图为核对用 |
| B-07-完整猫又回应.png | dark_maoyou_home.png | DarkMaoYou当前有调用 |
| B-08-反向收回小盒子.png | — | 未发现原样复制到Android资源；总图为核对用 |
| C-01-加载失败-开盖空盒.png | — | 未发现原样复制到Android资源；总图为核对用 |

旧十二宫格的实际页面状态主要为1、2、3、7、8、9、10；0、4、5、6、11未见显式状态调用。旧数字与新A编号不能直接当成同一个索引替换。

`dark_maoyou_home` 对应的是 **B-07 完整猫又回应**，并非 A-04 首页概览；`dark_maoyou_empty` 对应的是 **B-01 小盒子轻晃**，并非 A-10 空白状态。名称相近不代表情境相同。

## 素材裁切与透明度检查

- 深色5张资源均为512×512，代码按各自有效框裁切；框和像素数据记录在“核对证据.json”。
- 以alpha≥128视为主要不透明内容，5张图的裁切框均未漏掉此阈值的有效像素。本次**没有证据把它认定为明确的主体截断Bug**。
- 半透明的柔边、光晕和动作线可能位于框外，不包含在上述保证内；透明总图存在可见大范围光晕，单张也有局部残边。应先清理透明导出，再按同一视觉基准确定边距。
- 当前普通角色未见统一ColorFilter染色；脸部风格不同主要来自换图，不能一律归因于深色模式“把脸染绿”。AppBrand的ColorFilter用于字标白色描边及深色字标双色提亮，不作用于角色插画。

## 哪些差异可以保留

- 普通状态、思考、倾听、开心、警告、闭盒、开盒可有不同表情与道具，但应保持相同眼睛、身体结构、无脚设定、双尾和绿尾尖。
- 拉绳保留已确认的粗麻绳、尾巴在后方缠绕、绳结与猫一体、歪头向上及闭眼笑；统一画风时不重做已验证的交互。
- 品牌字标、桌面图标可按识别需求简化；已确认的是V1不连写字标，不能擅自切换V2连写或把Mew正脸硬塞进字标。
- 小猫在深色背景保持奶白原色。深色主题调整页面和卡片背景，不应另画一只不同体型的猫。
- 圆环中心目前按用户要求使用分类。统一角色不意味着把Mew重新放回分类区；半透明详情卡片、轻装饰和紧凑搜索／添加布局继续保留。

## 建议的统一基准与实施批次

1. **确认普通角色母版**：以V14为造型规范，V16为姿态补充；先修透明导出质量，不把总图光晕当成新画风。
2. **先替浅色旧图**：登录／注册、首页欢迎与管家卡、我的头像、游客清单、空态、添加导语、AI介绍；每一处与深色使用同一语义状态。
3. **接通入口一致性**：两主题首页导航、两种AI入口、游客与云端品牌头部、关于页；保留云端业务能力和确认流程。
4. **归一挂件画风**：只核对眼睛、脸型、线宽与描边色；保留600×768同坐标分层和现有拖拽／表情／回弹／出入场动画。
5. **集中管理**：统一语义状态和资源登记，标明在用、仅配置、待接入、历史稿；同步拉绳JSON中的展示尺寸和演示参数说明。
6. **验收**：同一场景浅深对照；普通猫与挂件对照；检查透明边缘、可见身体尺寸、尾巴完整性、表情语义及小尺寸辨识度。单独核对空库存、无结果、空清单、空会话及失败态。

## 原始依据位置

- [猫又-情绪炸毛双尾-十二场景V14-20261012.png](E:/1-大三上/团队项目/UI设计稿/猫又IP概念稿/猫又-情绪炸毛双尾-十二场景V14-20261012.png)
- [猫又-情绪炸毛双尾-十二场景V14-20261012-生成说明.md](E:/1-大三上/团队项目/UI设计稿/猫又IP概念稿/猫又-情绪炸毛双尾-十二场景V14-20261012-生成说明.md)
- [猫又-沿用更新IP的小盒子展开分镜V16-20261013.png](E:/1-大三上/团队项目/UI设计稿/猫又IP概念稿/猫又-沿用更新IP的小盒子展开分镜V16-20261013.png)
- [猫又-沿用更新IP的小盒子展开分镜V16-20261013-生成说明.md](E:/1-大三上/团队项目/UI设计稿/猫又IP概念稿/猫又-沿用更新IP的小盒子展开分镜V16-20261013-生成说明.md)
- [IP拉绳-饱满体型调整-两态-V04.png](E:/TM_code/Team-project/ui/IP拉绳-饱满体型调整-两态-V04.png)
- [素材配置.json](E:/TM_code/Team-project/ui/猫又拉绳-分层素材V01/素材配置.json)
- [approved-v1-design.png](E:/TM_code/Team-project/docs/ui/branding/Mewstow/approved-v1-design.png)
- [资源生成说明.md](E:/TM_code/Team-project/docs/ui/branding/Mewstow/资源生成说明.md)
- [00A-四个主页面总览.png](E:/TM_code/Team-project/ui/light_ui/00A-四个主页面总览.png)
- [00A-四个主页面总览.png](E:/TM_code/Team-project/ui/dark_ui/00A-四个主页面总览.png)

历史浅深设计总览中本来就能看到同源的新式无脚猫，当前浅色代码却仍保留旧素材，因此“设计稿曾统一”不等于“当前代码已统一”。历史品牌名与旧库存布局留作版本资料，不作为当前运行结论。

完整逐文件尺寸、哈希、复制对应与源码位置见同目录CSV和JSON；可视化对比见“Mew风格对比.html”。本报告不授权删除旧稿或自动重绘已确认品牌。
