# MagicVVu 后端 P4 规划数据验收报告

日期：2026-10-23。工程：`D:/project/Team_Project_Shared/Team-project`。本地已实现可信只读事实接入、认证及一致性修正，未部署。真实消费覆盖/库存盘点来源缺失，预测和智能补货维持准确降级；不声明已具备生产完整预测输入。

## 1. Git 与 P3 基线

开始前 `git rev-parse --show-toplevel` 确认上述内层根，工作区干净，HEAD=`b935c38b2b6eaed2513e958c44f1f63d7224edb0`（b935c38，后端和ai对接，添加了open记录等字段）。P1/P2/P3 已存在于这个本地提交，和任务背景所说“可能尚未提交”有所不同。未reset/clean/强制checkout，未提交或推送。没有适用AGENTS.md。先阅读P1/P2/P3主报告、P3迁移/前端交接、V1-P6 Schema/契约、实际Agent读取与算法、后端服务/模型/测试。P3报告244/263/772仅作历史基线，本次全部重新运行。

## 2. P4-00 路由审计与唯一契约

旧服务 `backend/server/app/services/planning_context.py` 真实存在；开始时 `rg` 和 `app.routes/OpenAPI` 均未找到规划路由。P3报告称 `/internal/v1/ai/planning-context` 可读，但本地实际只有服务级调用测试，不能据报告宣称已注册或已部署。Agent `agent/v1/tools.py` 请求 `GET /internal/v1/planning/context`，与V1-P6提议契约相同。

本轮正式契约为 **GET /internal/v1/planning/context**，复用和完善原服务，在主应用注册。旧报告路径 `/internal/v1/ai/planning-context` 是同一处理函数、相同认证/Schema/事务的隐藏兼容入口，不建立第二套数据系统。OpenAPI只展示正式路径。`BACKEND_TOOL_TOKEN` Bearer + `X-User-Id` + `X-Household-Id`，依赖原内部鉴权；快照内重新检查用户active及当前家庭成员。Android登录令牌不能作为服务令牌。GET只读，POST405，跨家庭404，不输出令牌。

## 3. 实际修改文件

- `backend/server/app/services/planning_context.py`：同事务快照、DB时间、批量读取operation来源、真实FK关联、真实分类、未知与失败处理、内容水位和来源。
- `backend/server/app/routers/planning.py`、`app/main.py`：唯一正式GET、兼容入口、内部认证、释放鉴权只读连接后重新校验、V1响应校验、no-store。
- `backend/server/app/planning_schemas.py`：后端独立只读DTO；不依赖Agent运行库，data兼容V1，provenance位于外层。
- `backend/server/app/routers/inventory.py`：在既有认证/版本/幂等事务中，保存显式最低库存请求和普通调整的结构化来源；未改变数量算法或权限。
- `backend/server/tests/test_backend_p4_planning.py`：54项P4用例；真实业务服务和隔离DB，不调用付费模型。
- `tools/p72_local_postgres_tests.py`、`tools/backend_p2_export_contract.py`：新增p4输出目标，保留旧阶段用法。
- `tools/backend_p4_http_probe.py`、`backend_p4_isolated_server.py`、`backend_p4_validate_schema.py`、`backend_p4_write_reports.py`：真实进程HTTP、仅测试DNS、机器Schema验证与证据报告生成。

未修改Agent预测/风险算法、Android、数据库模型、Alembic迁移或正式配置。原P2/P3测试会重写历史JSON证据；本轮将其输出另存P4回归证据后从开始时备份恢复，未倒填历史报告。

## 4. 字段映射（真实/未知/处理）

| Schema字段 | 数据库来源 | 完整性 | 缺口 | 处理 |
|---|---|---|---|---|
| scope | household_members + users.is_active | 家庭作用域在快照事务首条SELECT重新校验 | service token不等于用户权限 | 401/404拒绝，全部按家庭过滤 |
| snapshot_id / as_of | 服务端SHA256 / 首条SELECT数据库clock_timestamp或strftime | 同事务可见家庭内容/来源标识，as_of独立采集 | 不是客户端时间；不是人工核实时间 | 同内容跨筛选ID稳定；每次重新读取DB，as_of不可由请求覆盖 |
| event_watermark | business_events + draft_operations.committed_at | 全部家庭已可见语义事件内容散列 | 不是递增序号、WAL LSN或精确提交时间 | 包含ID/类型/数量/单位/before/after/occurred/recorded，禁止当范围游标 |
| shopping_version | shopping_lists + shopping_list_items全量内容 | 同快照家庭全清单含来源FK、数量、购买状态 | 60位散列整数，非递增版本；有极小碰撞概率 | 只作保守变化标识，不允许据此自动提交 |
| items_complete / history_complete | 有界查询成功且未超1000批/20000事件 | 传输完整，可重现同一MVCC读取 | 不证明现实消费已全部记录 | 超限409；查询失败503；不返回部分成功 |
| items[].item_key / batches[].id | inventory_items.id | 稳定批次ID；不合并同名或相似名 | 没有商品目录或可信跨批次product_id | 一批次一item；product_id=null |
| name / unit / quantity / version / location / status | inventory_items真实对应列 + 原to_p1_batch | 六位Decimal、规范单位、真实版本状态 | 旧件等不受支持单位仍存在可能 | 不猜包装换算；不兼容数据409 |
| category | inventory_items.category | 仅food/medicine/household精确值映射 | 中文自由分类无审核映射 | unknown并在来源保留raw_category，药品不猜 |
| purchased_at / label_expiry / opened_at | purchased_on / expires_on / opened_at | 真实保存日期，不改变其业务粒度 | 日期不等于标签类型/储存条件/审核事实 | 返回原日期；is_opened仅已存在日期时true，否则null |
| label_date_type / label_context_valid / storage_condition / label_storage_condition | 无真实业务列/写入来源 | unknown / null | 不能用位置名字或物品名字推断 | 本轮不编规则、不写审核记录 |
| events[].id / item_key / kind / quantity / unit | business_events真实行 + event_type确定性映射 | 仅Consumed参与原消费净量算法 | Moved/Opened数据库quantity NULL | V1兼容数量0占位，provenance保留NULL；丢弃仍独立 |
| events[].occurred_at / recorded_at / committed | business_events.occurred_at / draft_operations.committed_at /事务可见性 | 已提交事务中行及operation可见 | committed_at为应用事务内登记时间，不是PG精确commit timestamp | 开封日不覆盖事件时间；不声称墙钟保证等于提交时刻 |
| operation_id / household / actor / batch / relation | provenance.events按真实event_id提供 | 真实关联可追溯 | V1 Event不允许额外字段；DB不支持语义撤销/纠正 | 来源在data外；related_event_id=null，不将REVERSED状态猜成撤销消费 |
| coverage / recording_completeness_source | 当前无覆盖、每日消费确认或缺货记录模型 | [] / null，完整性unknown | 无事件不等于零；连续事件不等于完整 | 保留RECORDING_COMPLETENESS_UNKNOWN / NO_COMPLETE_COVERAGE_DAYS |
| known_quantity_adjustments | 现有history_json新增结构化kind、变更前后 | 只证明仍保留的adjust/edit_quantity，不算Consumed | 最多30条，旧展示文字无可靠语义 | 仅provenance列证据，adjustment_history_complete=false，不推日覆盖 |
| usable_quantity_verified / stock_verification | 无人工核实写入来源 | false / null | updated_at、添加、编辑或执行成功均不是盘点 | STOCK_VERIFICATION_REQUIRED，不提供耗尽日期/可用量保证 |
| preferences.minimum_stock | minimum_quantity + 显式请求的结构化历史证据 | 旧正值是真实存储值；新显式零有来源 | 旧零为默认值，无法辨别；历史证据会被淘汰 | 旧零null；显式零返回0；证据淘汰后零降级null |
| preferences.version / source | inventory_items.version / provenance.minimum_preference | 保守复用库存版本；有证据时记录actor/time/unit/version | 不存在独立偏好版本；旧正值无精确操作者/时间 | 不伪造精确来源，source标明来源列或authenticated_inventory_input |
| coverage_days / lead_days / order_unit / pack_size | 无保存源 | null | 不能生成默认偏好 | 沿用EXPLICIT_PURCHASE_PREFERENCES_REQUIRED及原算法门槛 |
| pending[].id / item_key / quantity / unit | shopping_list_items.id / source_inventory_item_id /真实列 | 仅同家庭明确FK关联，六位Decimal规范化 | 名称匹配、采购入库来源反向关联不能证明待购商品身份 | 不猜匹配；无关联的待购使pending_complete=false |
| pending[].status / confirmed / visibility | is_checked / 已持久化共享清单事实 | purchased或pending；confirmed=true=已是业务清单行 | 不代表本轮AI自动确认；draft不写购物表 | 已购不计待购扣减；保留原确认执行边界 |
| pending_complete / provenance.shopping | 家庭列表存在且全部待购可关联并表示 | 全家庭读取成功；含未关联/已购明细与内容版本 | 关联不确定仍有重复采购风险；缺列表不是空列表 | 无列表或无关联/不受支持数量单位的待购置false；不遗漏其他家庭内列表 |
| automatic_planning_commit | 原capabilities与执行拒绝门禁 | false | 规划基准尚无后端确认重验能力 | 不通过PLAN_ADD绕过；AI不直接写库存/采购 |

机器可读同表见 [字段清单](backend-p4-field-mapping.json)。所有UUID/数量样例来自隔离合成用户/业务写入，不是真实用户数据。provenance提供来源说明，不被Agent当成新增覆盖事实。

## 5. 快照一致性与水位

鉴权session只做SELECT，端点rollback释放连接，避免小连接池内每个请求同时占有两条连接。独立Session/identity map在PostgreSQL READ ONLY REPEATABLE READ内，首SELECT同时校验active/member并读取数据库时间；后续库存、事件+operation、采购表均在相同MVCC视图。SQLite显式BEGIN，规避Python legacy模式SELECT不自动开启事务的问题。SQLite WAL并发测试和PG并发测试分别在读库存后真正提交CONSUME/OPEN/PLAN_ADD，旧快照仍没有新事件/采购，新请求才同时看到新版本/事件/采购水位。

上限1000批次/20000语义事件/10000采购行，多查询不是分页，next_cursor=null；任一超限409 PLANNING_INCOMPLETE，任一SQL失败503 PLANNING_CONTEXT_UNAVAILABLE，没有部分成功、丢行或伪零。DTO遇不兼容旧数据409 PLANNING_CONTRACT_INVALID。items_complete/history_complete仅表示所选范围/已有账本传输完整，不证明现实消费完整。pending_complete还要求全家庭待购关联可判断，缺采购主表也false。

as_of是每次首SELECT的数据库时间。snapshot_id标识全家庭库存/事件/采购事实和来源，独立于读取时刻与name/item_key筛选；同内容重复读取/选择续接ID稳定。新请求仍重新读取数据库，不从旧缓存换时间戳。ID本身不是新鲜度凭证，Agent仍校验as_of。水位是内容散列，**不代表最新操作时间或精确事务提交序号**。operation.committed_at是事务内应用登记时间，行可见性证明事务已提交，但该字段不是数据库精确commit timestamp。当前不提供增量水位游标或跨快照排序。shopping_version为现有V1所需60位内容散列整数，有非零碰撞概率，也不用于自动确认。

## 6. 消费、调整、覆盖与核实

只输出真实business_events；Consumed、Discarded、Opened、Added、Moved各自保留语义。只有Consumed进入原算法消费净额；PlanAdded是购物事实，仅来源区保留。operation_id数据库唯一约束和P1回执重试保证相同操作不会重复累计。数量一直Decimal，事件单位按现有字典规范化，不合并不同包装。跨批次不做名称合并。DB没有撤销/纠正事件写入接口，不把库存REVERSED状态推断为逆向消费；Agent既有合成撤销/纠正回归继续运行。

Opened业务日期来自库存opened_at；事件occurred_at和operation登记时间仍是实际执行登记事实。V1对于无数量的Opened/Moved用0兼容表示，来源区保留数据库NULL；绝不当消费。新增普通adjust/edit_quantity只在原最多30条history_json中保存结构化变更，不创建假Consumed，不解析旧展示文字，不把有限调整历史标完整。

不存在每日记录完整性确认、缺货史、持续覆盖、人工盘点的可信业务写入源。因此production coverage=[]、recording_completeness_source=null、stock_verification=null、usable_quantity_verified=false。完整性为unknown；已知调整仅证明存在该调整，不证明整段历史是否完整。Agent原原因码RECORDING_COMPLETENESS_UNKNOWN、NO_COMPLETE_COVERAGE_DAYS、STOCK_VERIFICATION_REQUIRED/USABLE_STOCK_REQUIRES_REVIEW保持；统计占位0不能展示成真实零消费。

54项P4测试中使用合成覆盖仅验证完整输入的算法行为；五笔真实执行产生的0.2消费合计1，28个测试完整日，当前4，日均1/28、剩112天；测试偏好覆盖140天+提前0天，目标5、补货1。该测试没有将覆盖或核实写入生产模型，不声称数据库已具备这些事实。另测缺口、stockout、adjustment、history transport、单位冲突及新鲜度拒绝。

## 7. 偏好、商品关联与风险

最低库存旧正值有真实列依据；旧0不能区分默认，保持null。新认证创建/PATCH请求**显式包含minimum_quantity**才写结构化来源，含值/单位/actor/server time/版本；显式0因此可返回0。请求字段存在证明业务输入，不推测用户心理意图。最近30条证据淘汰后，0保守回到未知；这不是永久偏好审计系统，不为该阶段扩表。精确偏好时刻/操作者对旧正值未知，版本保守复用库存版本。其他偏好全部null。

只有shopping_list_items.source_inventory_item_id且指向当前家庭批次，才产生可信批次关联。原服务反用库存购买来源FK，漏掉真实补货项，本轮已修复。无关联待购仍在来源列表保留，不按同名消除重复风险；存在任一不可关联待购，pending_complete=false。已购保留purchased状态，原算法不扣入pending。清单版本包括来源FK变化。库存购买来源不被当成稳定商品ID；无product_id/规格目录，不能跨批次汇总。分类只精确映射既有V1枚举，位置不当作温度储存条件；日期类型/标签适用性unknown，未新建任何安全规则或审核记录。

## 8. Agent 与真实HTTP

Agent实际RemoteReader未改路径或算法；Backend data通过Agent PlanningSnapshot与仓库V1 JSON Schema。外层provenance不传给严格data校验。Reader继续300秒新鲜度（超过5分钟/未来超过1秒拒绝）、items_complete和cursor门槛；库存核实最大168小时原规则不改。真实网络证据见 [双进程HTTP](backend-p4-http-evidence.json)：独立后端Uvicorn+锁定环境Agent Uvicorn+临时PG，执行真实CONSUME后，经原公开消息网关→内部Agent→后端规划GET，返回insufficient_data及原原因；预测/补货接口也拒绝无依据数量，写标志false。仅测试DNS将固定agent:8767解析为127.0.0.1，端口8767启动前检查空闲，保留生产白名单与认证，未修改hosts或现有服务。后端/PG其余端口随机。

不允许自动规划提交。原P1对planning_basis、quantity_source=planning_calculation、intent=SUGGEST_PURCHASE的PLAN_ADD提交均仍拒绝PLANNING_REVALIDATION_UNAVAILABLE；无采购/库存写入。普通用户明确PLAN_ADD不受影响。Android不能调用内部接口/持有内部令牌。

## 9. 本次自动化与运行证据

| 环境 | 通过 | 跳过 | 失败/错误 | 证据 |
|---|---:|---:|---:|---|
| sqlite | 298 | 35 | 0 | [JUnit](backend-p4-sqlite-tests.xml) |
| postgres | 317 | 16 | 0 | [JUnit](backend-p4-postgres-tests.xml) |
| agent | 772 | 0 | 0 | [JUnit](backend-p4-agent-tests.xml) |

完整后端333项=原279+P4新增54。SQLite跳过35=19个PG并发+16个可选Nginx；PG跳过16均为可选Nginx。P4新增54项在两个DB都运行，没有将跳过记为PASS。Agent使用原锁定依赖环境加既有tzdata，共772项全通过。所有结果均由本次JUnit生成。

实际命令：

```powershell
.venv/Scripts/python.exe -m pytest backend/server/tests -q --tb=short --basetemp=.cache/p4-sqlite-final-3 --junitxml=reports/backend-p4-sqlite-tests.xml
.venv/Scripts/python.exe tools/p72_local_postgres_tests.py --stage p4
$env:PYTHONPATH='<repo>;<repo>/agent'
.cache/p2-agent-venv/Scripts/python.exe -m pytest agent/tests -q --tb=short --basetemp=.cache/p4-agent-final --junitxml=reports/backend-p4-agent-tests.xml
.venv/Scripts/python.exe tools/backend_p2_export_contract.py backend --stage p4
.cache/p2-agent-venv/Scripts/python.exe tools/backend_p2_export_contract.py agent --stage p4
.venv/Scripts/python.exe tools/backend_p4_validate_schema.py
git diff --check
```

[PG升级/启动/清理证据](backend-p4-postgres-evidence.json)记录PostgreSQL17.11、隔离data_directory、随机端口、未访问正式库、真实health/ready、测试退出0及cluster_removed=true。双方OpenAPI全部本地引用解析通过、路由唯一性回归通过。[Schema结果](backend-p4-schema-validation.json)共17个实际快照通过Draft202012Validator+FormatChecker和Agent模型；校验器jsonschema4.26.0仅安装到.cache/p4-schema-deps，不加生产依赖。样例：[SQLite](backend-p4-sqlite-examples.json)、[PG](backend-p4-postgres-examples.json)。TEST_ONLY键下的完整覆盖夹具不等于业务覆盖。

## 10. 迁移与失败记录

P4无需新增表/列，不添加0010。Alembic单一head仍20261023_0009。PG空库重跑head→0008→head→0007→head→0006→head；带真实P1操作回执和P2会话的0008↔0009保留，以及已有OPEN事件禁止降级均由原P3用例本轮重跑。SQLite账本存在时0009在DDL前拒绝的保护仍通过，未关闭外键。P4结构化history_json兼容旧应用读取，回退P4代码无需DDL；新来源证据仅旧代码不识别，后续有界淘汰可能降级。详见 [兼容与发布](backend-p4-migration-plan.md)。

首轮P4聚焦33通过后遇测试误用已detach的ORM实例，修正夹具保存ID后48项通过；初始失败XML保留。后来补4项来源/边界用例，再补2项真实规划选择续接用例，为最终54。沙箱socketpair初始化阻塞的测试进程已仅按本轮专用参数停止，最终在允许本机套接字的环境执行。真实进程联调初次503为网关固定地址白名单；随后DNS到随机端口方案也因客户端保留8767失败，最终固定空闲loopback8767成功；未放宽生产规则。首次隔离PG失败证据保留backend-p4-postgres-initial-evidence.json，两次临时集群均已停止/删除。SQLite初次292通过/35跳过证据另存。最终复核用两个新增用例复现snapshot_id随时刻/筛选变化造成规划选择循环（backend-p4-selection-before-tests.xml）；修正为家庭内容稳定ID后重跑双DB全量与HTTP，未修改Agent算法。修复前296/315全量证据另存preselection文件，最终数字来自最终XML。

本机无Docker CLI，**镜像未构建**；未执行真实DeepSeek付费调用、Android真机、生产部署/迁移/写入、生产负载/备份恢复演练、Nginx可选测试。旧AnyIO/Starlette/Alembic弃用警告未升级框架消除。不把健康检查或编译导入当成这些未验证项目通过。

## 11. 已实现、待实现与P5条件

| 能力 | 本地实现/测试 | 已部署 |
|---|---|---|
| 唯一规划读取、认证、同快照事实/来源、未知降级 | 已实现，本次双DB/HTTP验证 | 否 |
| P1/P2/P3执行/幂等/可信引用 | 保留且全量回归 | 本轮未部署；不据旧报告断言正式最新状态 |
| 显式最低库存0和有限调整来源 | 已有入口真实写入，保守保留限制 | 否 |
| 消费覆盖、缺货史、人工库存核实 | 无真实源，保持未知 | 否 |
| 跨批次商品目录、提前期/包装偏好 | 未实现，不猜历史迁移 | 否 |
| 可信输入完整时的预测/建议算法 | 原实现保留，测试夹具可复算 | 不声明生产数据已足够 |
| 自动补货提交 | 继续false，拒绝门禁已测 | 未开启 |

P5应先审查本次真实路径与V1 envelope，后端/Agent同步配置内部令牌和网络隔离；运维在另行授权窗口备份并演练恢复，确认0008/0009和应用版本，完成Docker构建、Nginx内网边界、Android真实流程与弱网恢复验收。AI/业务人员应审核商品分类和安全规则；产品/Android/后端应先设计明确盘点和消费覆盖的写入来源与版本绑定，再评审是否能启用预测。当前可发布范围应明确为“可信事实读取+准确不可用”，不能按完整自动预测/采购上线。P5正式发布尚未获授权，所有写入和部署仍需另行授权。
