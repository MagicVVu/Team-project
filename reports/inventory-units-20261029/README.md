# 库存逐件记录改造

2026-10-29，Asia/Shanghai。

## 最终行为

- `inventory_items` 每行代表一个实物，数据库与库存响应不再包含 `quantity`。新增请求仍接收数量，由服务端原子展开；首条 ID 与请求 ID 保持一致，其余 ID 确定生成，重试不会重复入库。
- 同一家庭内，商品名称经过 NFKC、去除首尾空格与大小写标准化后，名称完全相同，或共享连续至少两个字符，就自动关联已有 product。精确匹配优先，其余按名称长度、名称和 ID 确定选择；商品名称保持稳定，各物品保留原名。
- 连续确认“我买了10个苹果放在冰箱里”“我买了12个红苹果放在冰箱里”，得到一个“苹果”商品、10条“苹果”和12条“红苹果”。圆环显示 `*22`，详情逐件列出，消耗指定一件后显示 `*21`。
- 重量、体积按用户确认的规则保存为一份，原始重量或容量写到 `specification`。例如“500克肉”是一条“肉”，单位“份”，规格“500克”。计数输入须为1至10000的整数，不能把半个苹果静默取整。
- 编辑、消耗、丢弃、开封和移动针对具体物品 ID。改名只对该物品重新归类。消耗与丢弃锁定一个实物；已结束记录保留历史并可在详情切换展示。
- Android 游客模式也按逐件记录保存，迁移旧本地批次。旧云端批次缓存隔离，联网刷新后读取新模型。低库存提醒在商品汇总层计算，不对每件物品重复误报。

## 数据与迁移

`20261029_0012` 拆分旧整数计数批次，保留原首条 ID、名称、日期、存放位置、采购来源和历史。重量体积及历史小数计数保留原量到规格。原记录版本递增，旧批次待确认草稿不能直接执行。采购来源允许关联多个物品，一次请求允许产生多条逐件事件；原请求幂等凭据继续负责防重复。

服务器生产数据副本的完整升级、降级、再次升级均验证一致：34条旧记录转换为323条，其中319条在库、4条为丢弃历史。每条都有关联商品，家庭边界保持一致。6条旧重量/体积或小数批次转换为规格记录。历史事件 JSON 和请求回执保留原语义。

服务器保留私有迁移快照及完整发布前数据库备份。`inventory_items` 已去除数量列；快照仅用于恢复原数据。降级会核对迁移后的业务表摘要，发现后续写入会拒绝覆盖，不能直接用旧数据库备份覆盖新业务数据。

## 验证与安装

- Android：74项 JVM 单元测试、11项 Android 16 模拟器测试通过，覆盖22件明暗主题详情、指定红苹果 ID 操作、自动归类、超时请求原 ID 重试、逐件缓存和无数量字段解析。见 [前端报告](frontend/README.md)。
- AI：105项单位兼容、P8.4、P8.5回归通过，支持“份”“件”，保持原有最多两次模型调用规则。
- 迁移：独立 PostgreSQL 17 的7项规则及真实迁移测试通过，包含完整回滚、后续写入保护、多事件约束与扩展数量上限。
- 服务器79项后端测试全部通过，包含18项逐件库存专项、7项迁移测试和鉴权/登录安全回归。专项覆盖手工、AI与采购入库、事务回滚、跨家庭权限、分页、改名重新归类、并发与幂等；两句苹果原文通过真实 HTTP 处理阶段、模拟理解、持久化草稿与正式提交进行验收。

验证范围是新库存契约专项和选定回归；尚未全面改写依赖旧批次 `quantity` 语义的历史测试，不能把整个历史后端测试集视为通过。

新的手机客户端需安装 [调试 APK](../../frontend/app/build/outputs/apk/debug/app-debug.apk)。APK、设备测试与截图摘要见 [frontend/verification.json](frontend/verification.json)。未进行真实付费模型调用；模拟理解测试不代表真实模型对所有自然语言的识别率。

## 服务器发布

通过 `ssh magicvvu` 构建和验证候选版本；发布脚本为 [inventory_units_release.py](../../tools/inventory_units_release.py)，生产副本验证为 [inventory_units_clone_verify.py](../../tools/inventory_units_clone_verify.py)。

服务器交付和私有备份目录：`/srv/magicvvu/releases/inventory-units-20261029`。基于实际运行镜像覆盖本次22个后端、迁移与AI文件；完整候选源码位于该目录 `test-project/backend/server`。旧的 `/srv/magicvvu/magicvvu-starter/backend` 不是完整当前运行源码，未把新文件混入旧版本。

已在服务器完成正式发布：后端 `magicvvu/backend:inventory-units-20261029`，AI `magicvvu/agent:inventory-units-20261029`。切换期间短暂停止后端与AI写入，完成最终备份与迁移后恢复服务；Compose仅修改后端与AI镜像，数据库容器、环境变量、端口和挂载保持原样。三项服务均healthy，22个部署文件摘要与本地交付一致；直接TLS健康请求200，缺少App Key返回403，缺少Bearer返回401。没有创建生产验收账号或测试库存。

最终部署和服务器测试结果见本目录 [deployment-verification.json](deployment-verification.json)、[postcheck.json](postcheck.json)、[clone-verification.json](clone-verification.json)、[backend-postgres-tests.xml](backend-postgres-tests.xml) 与 [server-agent-tests.xml](server-agent-tests.xml)。

工作区原有聊天可靠性报告和部署材料已保留；本次没有提交或推送 Git。
