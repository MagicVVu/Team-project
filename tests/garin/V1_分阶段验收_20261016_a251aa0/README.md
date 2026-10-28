# Garin V1 分阶段离线复测 第一批交付

记录日期：2026-10-16。对应源码 a251aa033586e915cb49e35bbd242efccb358de6，分支 dev。

本轮完成离线规则测试、临时SQLite后端测试、Android构建与单元测试。完整V1正式链路尚未验收。不能将规则结果当真实模型成绩，也不能用SQLite结果代替PostgreSQL事务与并发。

## 实测结果

|组别|实际结果|证据|
|---|---|---|
|AI首次源码测试|462 PASS / 2 FAIL|evidence/ai-source/junit.xml|
|补齐部署模板后的完整复跑|464 PASS|evidence/ai-source-corrected/junit.xml|
|P1规则集|dev 90/90，test 60/60|evidence/p1-dev、p1-test|
|P2规则集|dev 90/90，test 60/60|evidence/p2-dev、p2-test|
|P3规则集|dev 90/90，test 60/60|evidence/p3-dev、p3-test|
|P5规则集|dev 90/90，test 60/60|evidence/p5-dev、p5-test|
|Garin专项|22项pytest通过，24条观察记录|results/专项执行记录.jsonl|
|云端后端本地测试|40 PASS，9条弃用警告|evidence/backend-local/junit.xml、日志|
|库存采购参考闭环|1 PASS|evidence/backend-special-http.jsonl|
|Android assembleDebug|PASS，APK未安装|evidence/android-assemble.log|
|Android testDebugUnitTest|17 PASS|evidence/android-unit-results|
|Android lintDebug|BLOCKED，离线依赖不足|evidence/android-build.log|

各组有重叠，禁止相加成独立真人样本数或统一通过率。开发记录的464/40/17只有经过本轮实际日志确认后才登记。规则评测JSON中的model_calls是规则提取次数，付费模型调用为0。

## P4旧缺陷复测

|旧测试入口|PASS|FAIL|REVIEW|BLOCKED|
|---|---:|---:|---:|---:|
|P0|260|0|18|0|
|P1|209|19|18|32|
|Android旧快照网关|210|18|18|32|

原84次程序问题中81条满足原断言。另3条保留原FAIL：P1 p0-41-2返回BATCH_TERMINAL；Android ext-013、ext-015受未注册采购品约束。开发方P4验证器把这3条列为resolved，本轮独立报告不将它们转PASS。

旧37条FAIL逐条见 results/旧用例失败清单.jsonl，含实际输出、HTTP、操作前后状态及原始证据行号。范围包括P0与P1功能/状态契约差异、候选批次表示差异，以及旧快照网关采购品和单位限制。它们不能直接当成37个新程序缺陷，也不能隐藏。三条契约边界已经包含其中，不重复相加。

## 各P做了什么

- P0：复用原150、扩展96与32旧流程；额外检查中文十二盒、完整品牌、提示注入、多操作、确认前无库存变化。
- P1：51项源码用例及90/60规则集；额外以明确批次准备开封、整批移动、部分/全部丢弃、多批次选择、零库存已结束批次。预览不提交事实。过期、版本变更与澄清续接由现有源码测试覆盖。
- P2：52项源码测试与32项交接/集成检查、90/60规则集；额外检查use_by与best_before、缺保存条件、到期风险、来源和规则版本。冰箱位置不替代保存条件。
- P3：94项源码测试、90/60规则集；固定2026-10-15测试时点，28个完整观察日消费7盒、库存2盒，日均0.25，剩8天，参考2026-10-23。14日覆盖加2日提前量，有待购1盒时新建议1盒；消费事件去重和非消费Finished事件不计入消费。
- P4：117项源码用例，以及原84次问题逐项对照，原FAIL/REVIEW/BLOCKED全部保留。
- P5：83项交互源码测试、90/60规则集；识别99盒手改2盒只产生2盒草稿；口误、否定和转述先澄清；未确认输入无提取与读取；公开网关不支持的item_key/空答案在发HTTP前拒绝。

源码单测数量属于464项内部划分，不能与规则集相加作样本数。现有源码测试具体名称、跳过与失败以JUnit为准。24条后续场景保持原包原样，不因规则覆盖而冒充正式事务验收。

## 首轮失败与适配修复

1. 测试副本漏deploy/compose.p2.override.yaml，导致交接包检查失败。补拷同版本文件后通过；没有改断言或预期。
2. P5旧测试在整段JSON查找99，随机UUID恰含99时误报。evidence/p5-uuid-diagnostic.json受控复现：无99的UUID通过，含99的UUID失败，两者上传text均为添加2盒牛奶，均无原始识别字段。测试程序仍需AI负责人修复；未改队友测试代码。
3. Android隔离缓存复制遇到Windows长路径，已只修本轮复制脚本；中文路径导致Gradle worker无法启动，改用临时V盘路径别名并在结束解除。只添加命令行路径检查参数，没改Gradle文件。
4. Lint仍缺material-icons-core-desktop 1.7.0、material3-desktop 1.3.0、material-desktop 1.7.0离线依赖，本轮不联网下载。保留BLOCKED，待补齐隔离构建缓存后单独复跑。

P5历史模型p5-42-1失败继续保留；来源为docs/versions/V1-P5/delivery-and-validation.md，本轮未调用真实模型。原150条人工复核不代签；位置漏标与创可贴快用完了的意图标签仍由团队确认。

## 隔离与文件边界

- 所有测试运行于本目录.snapshot，AI与云后端使用两个独立Python环境。
- Python离线工作进程清除服务/模型连接环境变量，强制rules并阻断socket外连；后端额外限制只创建SQLite引擎。异步运行所需本机socketpair例外仅用于进程自身。
- Gradle --offline；本地私有Gradle缓存从现有缓存只读复制；未安装APK、未连接设备或服务。
- 未连接18080正式服务，也未请求18081；http://10.0.2.2:18081只是测试APK编译参数。
- 真实账号/口令/令牌未写入公开附件，HTTP证据不保存Authorization头。数据是合成样例。
- evidence/source-integrity.json记录原684个范围外跟踪文件、78个旧Garin文件及410个副本输入的前后哈希，全部一致。原有frontend/app初代框架开发文档.md未提交修改保持原样。
- P4原始verification.json中tested_checkout_includes_uncommitted_p4_changes=true是验证器硬编码，不能用来判断本轮改动；实际基线以baseline.json和哈希审计为准。

## 可交给团队的文件

- Garin V1分阶段测试工作记录.docx：独立Word工作记录，可发给成员。
- results/分阶段统计.json、Android结果.json：机器可读统计。
- results/旧用例失败清单.jsonl、旧用例非通过清单.jsonl：37条FAIL与155条非通过记录。
- results/历史84次程序问题对照.json：逐条旧缺陷修复证据。
- results/专项执行记录.jsonl、evidence/backend-special-http.jsonl：独立专项及采购闭环。
- 联调待办.md、results/联调待办.jsonl：18项BLOCKED及1项样本REVIEW，每项列前提、步骤、预期和负责人。
- results/问题分类.json：程序/测试程序、样本、契约、未支持与环境问题分开记录。
- evidence/：原始JUnit、评测JSON、日志、依赖清单和受控误报诊断。先看证据索引.md。

建议命名为“Garin V1分阶段测试 第一批离线复测”，不要命名成产品V1-P1。本轮同时覆盖P0至P5，避免与AI成员的P1生命周期版本重名。

## 复现入口

现有证据禁止覆盖。worker.py和run_checks.py会拒绝已存在的结果目录。复跑时用capture.py创建tests/garin下新的轮次，再准备两套环境，不混用新旧成绩：

```powershell
$newRound='D:\Team_Project\Team-project\tests\garin\V1_分阶段复测_新轮次'
& 'E:\Development\SDKs\Python\Python313\python.exe' '.\capture.py' --source 'D:\Team_Project\Team-project' --out $newRound
```

AI按.snapshot/agent/requirements.lock.txt建独立环境，后端按.snapshot/backend/server/requirements-dev.txt建另一环境，Windows时区额外装tzdata；安装步骤只准备依赖，不调用模型。运行：

```powershell
& "$newRound\.runtime\ai\Scripts\python.exe" "$newRound\run_checks.py" --ai-python "$newRound\.runtime\ai\Scripts\python.exe" --backend-python "$newRound\.runtime\backend\Scripts\python.exe" --set all
```

Android先用prepare_android.py准备本轮私有离线缓存，确认本机JDK与SDK路径，再运行Run-Android.ps1。脚本中V盘须为空；不要给原仓库启动构建或修改构建文件来凑通过。当前Lint缺依赖，重跑前先由团队补齐隔离缓存。

第二批先由inHuman提供隔离服务、账号、家庭与独立数据库证明，MagicVVu确认实际部署入口/引擎/提交号。默认隔离脚本启动P1，不能据此宣布P2至P5通过。完整执行步骤见联调待办.md。未进行Git提交或推送。
