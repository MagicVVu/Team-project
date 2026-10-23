"""Generate P4 handoffs from actual final artifacts; refuse failed acceptance."""
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/'reports'


def junit(side):
    root=ET.parse(REPORTS/f'backend-p4-{side}-tests.xml').getroot()
    suites=[root] if root.tag=='testsuite' else list(root.findall('testsuite'))
    total={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    assert not total['failures'] and not total['errors'], (side,total)
    total['passed']=total['tests']-total['skipped']
    return total


counts={side:junit(side) for side in ('sqlite','postgres','agent')}
pg=json.loads((REPORTS/'backend-p4-postgres-evidence.json').read_text(encoding='utf-8'))
assert pg['exit_code']==0 and pg['postgres_stopped'] and pg['cluster_removed']
assert pg['http_contract']['exit_code']==0
schema=json.loads((REPORTS/'backend-p4-schema-validation.json').read_text(encoding='utf-8'))
assert schema['failures']==0
http=json.loads((REPORTS/'backend-p4-http-evidence.json').read_text(encoding='utf-8'))
assert http['agent_stopped'] and http['real_loopback_http']
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()

mapping=[
('scope','household_members + users.is_active','家庭作用域在快照事务首条SELECT重新校验','service token不等于用户权限','401/404拒绝，全部按家庭过滤'),
('snapshot_id / as_of','服务端SHA256 / 首条SELECT数据库clock_timestamp或strftime','同事务可见家庭内容/来源标识，as_of独立采集','不是客户端时间；不是人工核实时间','同内容跨筛选ID稳定；每次重新读取DB，as_of不可由请求覆盖'),
('event_watermark','business_events + draft_operations.committed_at','全部家庭已可见语义事件内容散列','不是递增序号、WAL LSN或精确提交时间','包含ID/类型/数量/单位/before/after/occurred/recorded，禁止当范围游标'),
('shopping_version','shopping_lists + shopping_list_items全量内容','同快照家庭全清单含来源FK、数量、购买状态','60位散列整数，非递增版本；有极小碰撞概率','只作保守变化标识，不允许据此自动提交'),
('items_complete / history_complete','有界查询成功且未超1000批/20000事件','传输完整，可重现同一MVCC读取','不证明现实消费已全部记录','超限409；查询失败503；不返回部分成功'),
('items[].item_key / batches[].id','inventory_items.id','稳定批次ID；不合并同名或相似名','没有商品目录或可信跨批次product_id','一批次一item；product_id=null'),
('name / unit / quantity / version / location / status','inventory_items真实对应列 + 原to_p1_batch','六位Decimal、规范单位、真实版本状态','旧件等不受支持单位仍存在可能','不猜包装换算；不兼容数据409'),
('category','inventory_items.category','仅food/medicine/household精确值映射','中文自由分类无审核映射','unknown并在来源保留raw_category，药品不猜'),
('purchased_at / label_expiry / opened_at','purchased_on / expires_on / opened_at','真实保存日期，不改变其业务粒度','日期不等于标签类型/储存条件/审核事实','返回原日期；is_opened仅已存在日期时true，否则null'),
('label_date_type / label_context_valid / storage_condition / label_storage_condition','无真实业务列/写入来源','unknown / null','不能用位置名字或物品名字推断','本轮不编规则、不写审核记录'),
('events[].id / item_key / kind / quantity / unit','business_events真实行 + event_type确定性映射','仅Consumed参与原消费净量算法','Moved/Opened数据库quantity NULL','V1兼容数量0占位，provenance保留NULL；丢弃仍独立'),
('events[].occurred_at / recorded_at / committed','business_events.occurred_at / draft_operations.committed_at /事务可见性','已提交事务中行及operation可见','committed_at为应用事务内登记时间，不是PG精确commit timestamp','开封日不覆盖事件时间；不声称墙钟保证等于提交时刻'),
('operation_id / household / actor / batch / relation','provenance.events按真实event_id提供','真实关联可追溯','V1 Event不允许额外字段；DB不支持语义撤销/纠正','来源在data外；related_event_id=null，不将REVERSED状态猜成撤销消费'),
('coverage / recording_completeness_source','当前无覆盖、每日消费确认或缺货记录模型','[] / null，完整性unknown','无事件不等于零；连续事件不等于完整','保留RECORDING_COMPLETENESS_UNKNOWN / NO_COMPLETE_COVERAGE_DAYS'),
('known_quantity_adjustments','现有history_json新增结构化kind、变更前后','只证明仍保留的adjust/edit_quantity，不算Consumed','最多30条，旧展示文字无可靠语义','仅provenance列证据，adjustment_history_complete=false，不推日覆盖'),
('usable_quantity_verified / stock_verification','无人工核实写入来源','false / null','updated_at、添加、编辑或执行成功均不是盘点','STOCK_VERIFICATION_REQUIRED，不提供耗尽日期/可用量保证'),
('preferences.minimum_stock','minimum_quantity + 显式请求的结构化历史证据','旧正值是真实存储值；新显式零有来源','旧零为默认值，无法辨别；历史证据会被淘汰','旧零null；显式零返回0；证据淘汰后零降级null'),
('preferences.version / source','inventory_items.version / provenance.minimum_preference','保守复用库存版本；有证据时记录actor/time/unit/version','不存在独立偏好版本；旧正值无精确操作者/时间','不伪造精确来源，source标明来源列或authenticated_inventory_input'),
('coverage_days / lead_days / order_unit / pack_size','无保存源','null','不能生成默认偏好','沿用EXPLICIT_PURCHASE_PREFERENCES_REQUIRED及原算法门槛'),
('pending[].id / item_key / quantity / unit','shopping_list_items.id / source_inventory_item_id /真实列','仅同家庭明确FK关联，六位Decimal规范化','名称匹配、采购入库来源反向关联不能证明待购商品身份','不猜匹配；无关联的待购使pending_complete=false'),
('pending[].status / confirmed / visibility','is_checked / 已持久化共享清单事实','purchased或pending；confirmed=true=已是业务清单行','不代表本轮AI自动确认；draft不写购物表','已购不计待购扣减；保留原确认执行边界'),
('pending_complete / provenance.shopping','家庭列表存在且全部待购可关联并表示','全家庭读取成功；含未关联/已购明细与内容版本','关联不确定仍有重复采购风险；缺列表不是空列表','无列表或无关联/不受支持数量单位的待购置false；不遗漏其他家庭内列表'),
('automatic_planning_commit','原capabilities与执行拒绝门禁','false','规划基准尚无后端确认重验能力','不通过PLAN_ADD绕过；AI不直接写库存/采购')]
(REPORTS/'backend-p4-field-mapping.json').write_text(json.dumps([
 dict(zip(('schema_field','database_source','completeness','gap','handling'),row)) for row in mapping],ensure_ascii=False,indent=2),encoding='utf-8')
table='| Schema字段 | 数据库来源 | 完整性 | 缺口 | 处理 |\n|---|---|---|---|---|\n'+'\n'.join('| '+' | '.join(row)+' |' for row in mapping)
test_table='| 环境 | 通过 | 跳过 | 失败/错误 | 证据 |\n|---|---:|---:|---:|---|\n'+'\n'.join(
 f"| {side} | {v['passed']} | {v['skipped']} | 0 | [JUnit](backend-p4-{side}-tests.xml) |" for side,v in counts.items())

main=f'''# MagicVVu 后端 P4 规划数据验收报告

日期：2026-10-23。工程：`D:/project/Team_Project_Shared/Team-project`。本地已实现可信只读事实接入、认证及一致性修正，未部署。真实消费覆盖/库存盘点来源缺失，预测和智能补货维持准确降级；不声明已具备生产完整预测输入。

## 1. Git 与 P3 基线

开始前 `git rev-parse --show-toplevel` 确认上述内层根，工作区干净，HEAD=`{head}`（b935c38，后端和ai对接，添加了open记录等字段）。P1/P2/P3 已存在于这个本地提交，和任务背景所说“可能尚未提交”有所不同。未reset/clean/强制checkout，未提交或推送。没有适用AGENTS.md。先阅读P1/P2/P3主报告、P3迁移/前端交接、V1-P6 Schema/契约、实际Agent读取与算法、后端服务/模型/测试。P3报告244/263/772仅作历史基线，本次全部重新运行。

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

{table}

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

{test_table}

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

[PG升级/启动/清理证据](backend-p4-postgres-evidence.json)记录PostgreSQL17.11、隔离data_directory、随机端口、未访问正式库、真实health/ready、测试退出0及cluster_removed=true。双方OpenAPI全部本地引用解析通过、路由唯一性回归通过。[Schema结果](backend-p4-schema-validation.json)共{schema['snapshots_validated']}个实际快照通过Draft202012Validator+FormatChecker和Agent模型；校验器jsonschema4.26.0仅安装到.cache/p4-schema-deps，不加生产依赖。样例：[SQLite](backend-p4-sqlite-examples.json)、[PG](backend-p4-postgres-examples.json)。TEST_ONLY键下的完整覆盖夹具不等于业务覆盖。

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
'''
(REPORTS/'backend-p4-planning-report.md').write_text(main,encoding='utf-8')

sample=http['snapshot']
ai=f'''# MagicVVu P4 AI 接口交接

2026-10-23，本地已实现并验证，未部署。唯一正式读取：`GET /internal/v1/planning/context`。旧报告路径`/internal/v1/ai/planning-context`仅为同一服务的隐藏兼容入口。Agent RemoteReader 已请求正式路径，本轮无需改Agent算法或工具路径。协议`v1-planning-context-1`，契约：[后端OpenAPI](backend-p4-backend-openapi.json)、[V1 Schema](../docs/versions/V1-P6/planning-context.schema.json)。

## 请求与认证

```http
GET /internal/v1/planning/context?name=牛奶
Authorization: Bearer <BACKEND_TOOL_TOKEN，仅服务端配置>
X-User-Id: <可信用户UUID>
X-Household-Id: <可信当前家庭UUID>
```

可不填选择条件查询全家庭，name/item_key最多一个；item_key是批次UUID，不能把相似名称当product_id。内部服务令牌与AI_SERVICE_TOKEN分开；后端重新检查active/member，跨家庭404，错误/缺令牌401。Android不持有令牌，不直接访问。POST405。

## 实际响应

以下是本轮真实双进程HTTP+隔离PG业务执行的响应摘取，UUID来自合成测试用户。完整返回及事件operation_id来源见[HTTP证据](backend-p4-http-evidence.json)。

```json
{json.dumps({'data':sample['data'], 'provenance': {'schema_version':sample['provenance']['schema_version'], 'recording_completeness':'unknown','automatic_planning_commit':False}},ensure_ascii=False,indent=2)}
```

示例provenance仅摘录；实际包含items/events/shopping来源。data严格兼容现有V1，不能把外层provenance整体塞进PlanningSnapshot。事件原operation_id、家庭、actor、数据库NULL数量及关系支持状态在`provenance.events[event_id]`，V1 Event仍只保留已有字段。缺省不增加新预测规则。

## 一致性、完整性、新鲜度

as_of来自快照首SELECT数据库时间，库存/账本/共享采购同事务：PG只读Repeatable Read，SQLite显式BEGIN。no-store。snapshot_id绑定全家庭内容/来源，独立于时刻与筛选，同内容ID稳定；每次重新读数据库提供as_of，ID不能替代新鲜度校验。event_watermark是可见账本内容SHA256；shopping_version是60位内容散列整数，均非递增提交序号。已有Agent只作快照一致性比较，不允许据此绕过确认重验。超限409 PLANNING_INCOMPLETE、DB失败503 PLANNING_CONTEXT_UNAVAILABLE、存储事实无法表示409 PLANNING_CONTRACT_INVALID；没有成功的部分数据响应。RemoteReader遇HTTP错误沿用现有TOOL_UNAVAILABLE映射，保持现有错误契约，后端错误detail供日志定位。

items_complete/history_complete=true证明完整读取已有行，**不证明现实所有消费已记录**。coverage=[]和recording_completeness_source=null是核心事实；请继续返回RECORDING_COMPLETENESS_UNKNOWN和NO_COMPLETE_COVERAGE_DAYS。stock_verification=null/usable_quantity_verified=false必须保留STOCK_VERIFICATION_REQUIRED/USABLE_STOCK_REQUIRES_REVIEW；普通更新时间不得替代盘点。

Reader继续拒绝超过300秒/未来超过1秒的快照、不完整items/有cursor；库存核实168小时门槛保留。本轮未扩展任何覆盖/核实来源，不能通过合成fixture或忽略校验使生产输出预测。

## 数量与建议限制

只计Consumed，Discarded/Opened/Moved/Added/普通调整不算消费；Opened/Moved在V1数量0仅适配无数量事实，来源为NULL。operation_id唯一，不能重复累计；不能解析旧history展示文字当事件。原撤销/纠正算法仍支持测试，但当前业务DB没有对应事件写入，不生成假关系。

每个item_key仅对应一个真实批次，无可信跨批次商品ID。所有数量Decimal；单位不兼容时沿用EVENT_UNIT_CONFLICT/INVALID_UNIT，不能猜包装量。pending仅有明确同家庭source_inventory_item_id才能关联；无关联待购使pending_complete=false，不当作0。实际已购状态purchased保留但不扣待购量，外层来源保留全部采购明细。

最低库存旧0=null，新显式业务请求0有结构化来源可返回0；历史最多30条，证据丢失后0降级null。旧正值来自真实minimum_quantity，精确actor/time未知。偏好版本保守复用库存版本。coverage_days/lead_days/order_unit/pack_size未设置均null，不生成默认值。分类仅精确已有枚举，product_id=null，标签类型unknown、储存事实null；规则审核仍需AI/业务同事，后端未造规则。

`automatic_planning_commit=false`。即使建议生成PLAN_ADD草稿，原后端对planning_basis/planning_calculation/SUGGEST_PURCHASE仍拒绝PLANNING_REVALIDATION_UNAVAILABLE；AI不能写采购清单或库存。

AI同事需：同步正式路径/内部token/家庭身份；在UI解释传输完整与记录完整的区别；继续原降级和新鲜度门槛；审核规则与缺失事实的业务来源；未来商品目录/覆盖/盘点契约变更需要版本化联合评审，不自行增加算法默认值。真实DeepSeek及正式服务未验证。本轮Agent全量{counts['agent']['passed']}通过；真实内网HTTP由两个本机Uvicorn进程验证，非模型联测。
'''
(REPORTS/'backend-p4-ai-handoff.md').write_text(ai,encoding='utf-8')

frontend='''# MagicVVu P4 Android 业务数据交接

2026-10-23，本地实现未部署。Android继续用公开认证网关 `POST /api/v1/agent/messages` 或P2会话/可信引用入口，四字段消息契约不变；任务GET仍用于恢复。内部规划路径不属于Android API，禁止在APK保存BACKEND_TOOL_TOKEN/AI_SERVICE_TOKEN或直接调用内部端口。本轮未改Android源代码。

## 当前可接入

消息示例：`{"household_id":"<当前家庭>","text":"牛奶消耗统计","request_id":"<稳定请求ID>","household_timezone":"Asia/Shanghai"}`。恢复与草稿确认继续遵循P2/P3前端交接，不混用引用或客户端自建内部context。

- 消费详情事实：`GET /api/v1/households/{household_id}/consumption-events`（沿用现有公开认证与分页），只计真实Consumed。Discarded/Opened/普通数量调整不显示成吃掉/喝掉。列表分页未结束不能声称全部历史。
- AI结构化统计：任务`result.consumption_summary`包含item_key/name/unit、window_start/window_end_exclusive、observed_days、effective_quantity、effective_events、event_ids、status/reason_codes。窗口为家庭时区完整日，排除今天；显示真实返回窗口，不强行标固定28天。
- 数据更新时间：展示result.evaluated_at和snapshot_id；它是本次计算使用的快照采集时刻，不是库存人工核实时间。普通库存updated_at同样不是核实时间。
- 耗尽依据：result.forecast的current_stock、daily_recorded_consumption、remaining_days、reference_date、summary及reason_codes。只有estimated且有可信数据时显示估计日期；显示“按记录消费，未来不补货、消费接近窗口”的条件，不能标为保证可用。
- 建议：result.recommendations的source/status/current_stock/pending_quantity/target_stock/suggested_quantity/unit/reason_codes。Decimal字符串避免客户端浮点舍入；数量和单位整体展示。没有suggested_quantity时显示不可用，不补0。

## 当前真实不可用状态

现有业务没有消费覆盖或人工库存核实来源，正常出现RECORDING_COMPLETENESS_UNKNOWN、NO_COMPLETE_COVERAGE_DAYS、STOCK_VERIFICATION_REQUIRED、USABLE_STOCK_REQUIRES_REVIEW。统计可能携带effective_quantity=0的算法占位，但status!=complete或observed_days=0时必须显示“记录覆盖不足，无法判断消费量/速率”，**不得展示成0消费**。可以另展示已记录Consumed事件列表及对应范围，文案明确“已记录”，不要等同现实全部消费。forecast.rate/date为null时显示不可用原因。

PENDING_INCOMPLETE表示家庭待购读取/关联不能证明完整；同名待购可能存在，不能以局部空列表标无重复采购。过期快照STALE_PLANNING_SNAPSHOT需重新查询，不延用旧数。PLANNING_INCOMPLETE/PLANNING_CONTEXT_UNAVAILABLE/TOOL_UNAVAILABLE显示暂不能提供完整数据并允许重试，保留原任务请求去重策略。

## 已有偏好与最低库存0

公开库存创建/PATCH已有minimum_quantity。新请求显式包含这个字段时后端保存“明确业务输入”来源，可区分0和未设置；客户端仅在用户明确设置时发送，不能为未设置字段自动补0。PATCH仍要expected_version及稳定operation_id。创建省略该字段沿用DB0，但规划视图标未知。旧记录0无历史证据仍未知；正值是真实规则阈值，旧操作者/时间可能未知。

原StockResponse.minimum_quantity仍是兼容的数值列，**不能仅据公开DTO的0在偏好界面声称用户已设置**；原公开DTO尚无minimum_stock_known/source字段。当前可通过AI结果的不可用原因展示限制；需要专门显示“已设置/未设置”全量偏好时，P5应增加经家庭认证的公开偏好DTO（minimum_stock:null/"0"、source、version），不可让Android读取内部来源区。本轮该偏好展示DTO未实现。

补货覆盖天数、提前期、订货包装均无保存入口，UI显示未设置/暂不可用，不将默认7天/1盒写为用户偏好。“最低库存规则”以用户阈值为目标；“AI记录预测补货”以完整消费窗口速率×覆盖+提前期为目标。source必须区分minimum_stock/recorded_history。当前AI还缺核实/风险事实，不能因为已有最低库存就直接确认自动建议。

继续先读`GET /api/v1/agent/execution-capabilities`，automatic_planning_commit=false。AI预测补货不得直接调用普通PLAN_ADD绕过；用户明确购物计划仍通过原确认草稿/operation_id链路。当前自动建议提交会被后端拒绝PLANNING_REVALIDATION_UNAVAILABLE。

## P5需要新增的业务入口（草案，均未实现）

1. 库存盘点确认：建议公开 `POST /api/v1/households/{household_id}/inventory-verifications`，只允许当前登录成员；请求operation_id、expected_batch_versions完整集合、盘点结果/明确确认及范围。后端应锁定/比对当前完整库存集合与版本，漏批次/新增批次/版本变化返回冲突，绑定操作者/服务端checked_at/source/各批次版本，保留不可变审计记录及幂等回执。不得由新增或编辑自动触发，不得让客户端传user_id/可信checked_at/verified=true。盘点当前数量不等于确认历史消费完整，也不直接等于风险意义上的usable_quantity_verified。
2. 消费记录覆盖：单独明确用户确认的家庭/商品/日期区间及该期间是否全记、是否缺货/未知调整；后端需要业务审核后的完整性证据与中断/纠正规则。不能单凭“库存准确”勾选自动生成过去28天完整记录。该接口和持久模型需产品/AI/后端联合确定，当前没有路由或存量覆盖。
3. 商品目录：显式选择稳定product_id并维护包装/可换算单位，历史批次仅由用户或有审计来源的匹配确认，不按名称批量回填。保留批次日期/状态。当前一批次一item，不做商品级跨批次消费总量。
4. 补货偏好：经认证/版本校验的显式设置/清除；区分null与0，覆盖天数/提前期/订货单位与容量成对校验。先交公开偏好可知状态，再接界面，不能沿旧非空零列猜设置状态。
5. 标签事实：可选登记日期类型、厂家标签、储存条件与来源，位置选择不自动等于冷藏条件；审核安全规则仍由业务/AI同事负责。

上述是后续接口要求而非本轮已完成能力。真实响应见backend-p4-http-evidence.json、backend-p4-sqlite-examples.json；完整覆盖示例键TEST_ONLY不用于产品演示或生产结论。P5需Android真机、弱网/进程恢复、权限切换联测后另行获准发布。
'''
(REPORTS/'backend-p4-frontend-handoff.md').write_text(frontend,encoding='utf-8')

migration='''# MagicVVu P4 数据兼容、迁移与回滚说明

2026-10-23。P4没有新迁移；不为了阶段编号新增0010。真实Alembic唯一head仍20261023_0009，父为0008，保留P3安全约束。本轮不新建消费覆盖/盘点表，因为当前无真实业务触发和可信写入源。

P4只利用已有history_json保存新认证输入的最低库存来源及普通调整结构。数组仍最多30条、兼容原id/hash/message/created_at；增加可忽略kind/minimum_preference/变更前后字段。新写入在原认证、锁、版本和幂等事务中完成。旧零不回填覆盖/偏好；新显式零来源淘汰后降级未知。没有修改任何历史事件、任务、草稿、会话、决策、回执，也无用户库存测试写入。

隔离PostgreSQL17.11从空库升级head并跨0008/0007/0006往返；原P3带P1执行账本+P2会话的0008→0009→0008→0009逐字段保留和回执恢复、写OPEN后禁止降级、约束validated用例本轮再跑通过。日志来自backend-p4-postgres-evidence.json，逐步输出另存backend-p4-migration-log.txt；带数据结果见backend-p4-regression-postgres-p3-examples.json。

SQLite有执行账本时0009 CHECK重建在DDL前拒绝；本轮继续测试拒绝、版本/数据不变、foreign_keys=ON和foreign_key_check无错误。不关闭外键、不清账本、不绕过检查。SQLite完整测试用独立新建数据库，不能把它解释为带账本升级0009已支持。

P4代码回滚无需DDL；保留新history_json结构，旧代码忽略额外字段。旧规划实现的路由缺失/不一致问题可能随应用回滚恢复，需API版本协同；不要删除新来源数据来回滚。0009→0008遇OPEN/DISCARD审计记录不可降级，应只回退兼容应用，保留DB与事件。正式部署仍需单独授权。

P5备份方案（尚未执行）：在获准窗口确认目标DB/现有revision、暂停业务写入或采用一致性备份策略；pg_dump自定义格式含全部表/约束/序列并记录版本校验，限制文件权限、加密传输存储，连接密钥不进入报告；在独立数据库用pg_restore实际恢复并核对库存、事件、任务/草稿/会话/operation回执计数和关键约束及回执恢复；明确RPO/RTO和镜像回退版本后才实施。未演练生产全库备份恢复，不声称P5正式发布已准备完毕。
'''
(REPORTS/'backend-p4-migration-plan.md').write_text(migration,encoding='utf-8')
(REPORTS/'backend-p4-migration-log.txt').write_text('\n\n'.join(str(r['target'])+'\n'+r['log'] for r in pg['migration']),encoding='utf-8')
print(json.dumps({'tests':counts,'validated_snapshots':schema['snapshots_validated'],'head':head,'reports_written':4},ensure_ascii=False))
