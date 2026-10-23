# MagicVVu P3 数据库迁移与安全回滚

日期：2026-10-23。只在隔离环境执行过；没有运行正式迁移、重启或切换镜像。

## 1. 依赖与变更范围

实际迁移链单一head：`20261017_0007 → 20261023_0008 → 20261023_0009`。正式只读核实仍为0007，发布P1/P2/P3代码时必须审查并依次应用0008、0009；不得恢复另一条历史0008或创建平行head。

0009文件：`backend/server/alembic/versions/20261023_0009_open_discard.py`。只替换三个命名CHECK：

| 表 / CHECK | 新规则 |
| --- | --- |
| draft_operations / ck_operation_action | 原四动作加OPEN、DISCARD。 |
| business_events / ck_business_event_type | 原四事件加既有P7/V1语义Opened、Discarded。 |
| business_events / ck_business_event_quantity | StockMoved、Opened必须NULL；其他事件包括Discarded必须>0且≤1,000,000,000。 |

PostgreSQL使用原生ALTER TABLE约束操作，不复制或回填业务行。未改库存列、精度、状态CHECK或opened_at，未删表/行、未重写历史JSON、未改P2会话表。SQLite空账本由Alembic batch完成；**有执行账本的SQLite明确拒绝迁移**，因为父表被RESTRICT引用，不能用关闭外键换取重建。拒绝发生在DDL前，保留原revision与数据。这是明确的本地SQLite迁移限制；正式发布目标为PostgreSQL。

不增加“所有历史DISCARDED数量必须为0”的回溯约束，以保留旧手动操作数据。P3新增all及partial扣零由同事务业务逻辑保证数量0/状态DISCARDED；数据库原数量非负及新事件约束仍开启。

## 2. 实际隔离验证

命令：`.venv\Scripts\python.exe tools/p72_local_postgres_tests.py --stage p3`。

本工具启动本次新建的PostgreSQL17.11临时目录、随机loopback端口和私有测试密码，无系统服务；测试fixture验证DB名为magicvvu_p7_execution_test和真实data_directory匹配后才写入。测试结束已停止并删除仅本次data目录。

空库流程：upgrade head → downgrade0008 → upgrade head → downgrade0007 → upgrade head → downgrade0006 → upgrade head；全部exit0。真实Uvicorn在迁移后启动，health和ready通过。完整执行日志在 [backend-p3-migration-log.txt](backend-p3-migration-log.txt)，运行及清理证据在 [backend-p3-postgres-evidence.json](backend-p3-postgres-evidence.json)。

带数据流程位于 `test_migration_preserves_ledger_and_p2_and_blocks_unsafe_downgrade`：在独有测试schema迁到0008，实际HTTP执行CONSUME产生旧operation/receipt/event/decision，加入P2绑定和会话行；0008→0009→0008→0009每步逐字段比较所有旧业务行不变，再通过原operation_id恢复原样回执。新OPEN执行后降级0008报RuntimeError，revision仍0009、行不变、PG约束均validated。真实结果保存在 [JSON样例的populated_migration](backend-p3-postgres-examples.json)，最终JUnit中该用例通过。

另用外键ON的SQLite0008账本验证：升级0009在DDL前明确拒绝，旧数据相等、revision仍0008、foreign_key_check为空。未将这个拒绝写成“SQLite带数据升级通过”。

## 3. 正式发布前的审查与备份方案（尚未执行）

1. 后端/DB负责人确认目标确实为获准的正式PostgreSQL实例、当前revision、单一head和P1/P2代码齐全；确认无并行确认写入窗口，评估ALTER锁等待。
2. 在另行获准的维护窗口暂停相关写入。使用受控连接配置运行pg_dump自定义格式全库备份，包含库存、任务、草稿、账本、事件及P2会话；密码通过受控环境或pgpass，不写入命令、报告或Git。备份放在现有Docker Volume之外的受控目录，保留校验和、时间和访问权限。
3. 用pg_restore --list核对归档，并在另一隔离PostgreSQL17实例真实恢复，检查revision、各业务表行数、约束、代表性旧operation_id回执；只有恢复演练成功才继续。正式全库恢复演练本阶段未执行。
4. 审查0008的会话表及降级保护、0009三个CHECK；在发布包的原有Alembic环境执行upgrade head。保持MAGICVVU_OPEN_EXECUTION=false和MAGICVVU_DISCARD_EXECUTION=false；先验证旧四动作、P2适配/鉴权和只读健康。
5. Android及Agent契约联调后，另行获准分动作启用能力并验收，不把测试fixture启用配置带入正式环境。没有新迁移前不可开启写入新事件。

上述为待审批方案，不是已执行的正式步骤；没有删除/重建任何既有Docker Volume或数据库。

## 4. 回滚限制

优先应用回滚：关闭两个能力开关，保留0009以及全部历史事实；已提交操作仍用旧operation_id恢复，旧代码应保持追加字段兼容。回滚到P1/P2版本前需评估其是否能读取新事件，不能把读不懂的新事件伪装成消费或删掉。

`downgrade0008`先检查所有OPEN/DISCARD operation及Opened/Discarded事件。只要存在任一种就报错，**不能删除审计记录来强行降级**。没有新事件时PG可恢复原CHECK，已有原四动作与P2数据保留，已在隔离带数据往返验证。SQLite只要有执行账本则拒绝约束重建。

0008已有P2会话记录时也会阻止危险降级；0007已有执行审计时禁止降级删账本。要回到更早模式，保留数据库结构并回滚应用，或由DB负责人在明确恢复目标/停写/审计批准后执行独立备份恢复流程；本阶段没有执行这样的恢复。

迁移失败时先停止后续发布并查询实际alembic_version和约束状态，不自动换镜像或删除表。PG DDL由迁移事务保护；仍需现场核实锁、连接与实际结果。HTTP超时不等于业务失败，与数据库迁移回滚是不同问题。
