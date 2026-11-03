# P7 Android 草稿确认接入（第四阶段）

本轮基于 dev `db55fda1262f55d46eba8fa0c2dc3b23aee75cab` 与本地尚未推送的第三阶段后端 0.9.0。生产仍为 0.8.0。不能用远程旧后端覆盖本地执行模块，也不能将本轮 Debug APK 作为生产验收。

## 运行与连接

先通过 SSH 核对 `magicvvu-p7-execution-20261017-backend-1` 的健康、镜像、网络和 IP。本轮 IP 为 `172.24.0.4`，容器重建后必须重新读取。它没有发布宿主机端口。

确认本机 18082 未占用后，独立运行：

```text
ssh -N -o BatchMode=yes -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes -L 127.0.0.1:18082:172.24.0.4:8000 magicvvu
```

模拟器使用 `http://10.0.2.2:18082`。USB 真机可以单独核查 `adb -s <设备> reverse --list` 后配置 `adb -s <设备> reverse tcp:18082 tcp:18082`，App 使用 `http://127.0.0.1:18082`；本轮没有物理真机验收。不要开放公网端口，不改动既有生产隧道或服务器 127.0.0.1:8000。

`AgentClient.capabilities` 每次业务会话都先检查 health.version=0.9.0、isolated_test=true，再读取已登录用户的 execution-capabilities，检查协议和 owner。验证失败不会发送 AI/确认/取消请求。阶段四客户端特意限定为隔离测试服务，未来生产切换需要独立交付。

```powershell
$env:JAVA_HOME='C:/Users/Cavia/.gradle/jdks/eclipse_adoptium-21-amd64-windows.2'
./gradlew.bat :app:assembleDebug :app:assembleDebugAndroidTest :app:testDebugUnitTest :app:lintDebug --offline -PmagicvvuApiUrl=http://10.0.2.2:18082
```

## 数据与状态

`AssistantEntry` 保存完整公开任务、草稿、preview、execution 和独立正式回执，提供 task_id、request_id、draft_id、operation_id、双 revision、候选、allowed_fields、error_code 和分层状态。AI 的回复与旧 inventory_written=false 不用于判断业务成功。

`AssistantStore` 按服务地址、用户 ID、家庭 ID 保存任务 outbox；不保存 Token。凭据继续使用 CloudCredentials / Android Keystore。原消息体和 request_id 在第一次发送前同步持久保存，完整确认 JSON 与 operation_id 在 POST commit 前保存。保存失败即停止发送。任务由页面外协程持有；关闭拉绳不会取消正在提交的请求。

重开、Activity 重建或进程重启后仅自动 GET 恢复。操作 ID 存在时先查 operations，再查任务/草稿 execution。404 不会创建新 ID；需要用户点击“用原确认请求恢复提交”，只能重用原 JSON。取消、澄清同样保存原请求和修订后发送。退出登录清除该账号本机活动任务绑定；服务器回执仍保留。家庭切换后旧响应不得进入新家庭视图，所有发送与结果接受均重新检查作用域。

版本冲突保持冲突状态，刷新当前库存供核对；不能通过恢复任务把它重新变成待确认，更不能覆盖 expected_version 后自动提交。已执行但刷新失败时保留 committed 回执与“重新刷新库存”提示。

## 公开 API

`AgentClient` 只使用当前用户 Bearer 调用以下实际公开接口：

| 方法 | 路径 | 请求/结果 |
| --- | --- | --- |
| GET | /api/v1/agent/execution-capabilities | 服务端能力、精度、白名单约束 |
| POST | /api/v1/agent/messages | household_id、text、稳定 request_id、household_timezone |
| GET | /api/v1/agent/tasks/{task_id} | 公开完整任务，revision 取实际值 |
| POST | /api/v1/agent/clarifications/{task_id} | revision、当前 allowed_fields 中的非空 answers |
| GET | /api/v1/drafts/{draft_id} | 原草稿、revision、preview |
| GET | /api/v1/drafts/{draft_id}/execution | 独立决策状态、双 revision、receipt |
| POST | /api/v1/drafts/{draft_id}/commit | operation_id、draft_revision、task_revision、edits |
| POST | /api/v1/drafts/{draft_id}/cancel | draft_revision、task_revision |
| GET | /api/v1/operations/{operation_id} | 持久化正式回执 |

本轮实际网关在澄清完成、结果不再包含 clarification context 时可能保留 task revision；客户端核对真实 task/execution 修订，不假设每次状态变化都递增。

## 界面与限制

保留四栏、首页助手、猫又拉绳与深浅主题，云端 Chat 进入结构化卡片；本地游客问答继续使用原实现。保留原有拉绳 720ms 动画修改，并合入 dev 上游 Mewstow 品牌文件。

| 动作 | 客户端编辑 | 执行 |
| --- | --- | --- |
| ADD | name、quantity、unit、location、purchased_at、label_expiry | 位置必填；后端确认后新增 |
| MOVE | to_location | 显示原/目标位置，保护批次/数量/版本 |
| CONSUME | quantity、unit | 显示当前库存、预期剩余；正式 Consumed 回执后成功 |
| PLAN_ADD | quantity、unit | 仅明确数量的手动计划；不购买、不入库 |
| OPEN / DISCARD | 不开放确认 | 保留回复、草稿/预览，提示手动入口 |

使用后端 editable_fields 与客户端白名单的交集。库存六位、采购三位小数，位置 100 字；超限报错，不舍入或截断。规划依据、action、batch_id、expected_version、身份等从不进入 edits。

“第二个”只解释当前最后一条有效澄清候选，不引用更早历史；实际续接仍检查最新任务状态和 revision。多批次不默认第一项。公开受信引用仍关闭，“它”等跨提问指代要求明确名称。rules 对“买2包纸巾”可能返回 unsupported，App 不改写原文。

## 验收工具

`tools/seed_execution_android.py` 只能在第三阶段 backend 容器内经 SSH stdin 执行；明确校验 DB_NAME、DB_HOST 与 ISOLATED_APP_TEST。每次新建合成账号、家庭和库存，不清空既有状态。输出包含随机合成密码，调用方必须捕获到 Git 之外的私有文件，不能写日志或报告。

`tools/run_execution_android.py` 从私有文件读取夹具、验证 localhost18082 健康后执行仪器测试并脱敏日志。`--process-restart` 分别运行 prepare/restore，并在中间对指定测试设备上的 com.example.teamapp 执行 force-stop；两个测试校验实际 PID 不同。

```text
python tools/run_execution_android.py --adb <adb.exe> --device emulator-5554 --fixture <Git之外的私有夹具JSON> --output <验收日志> --install
python tools/run_execution_android.py --adb <adb.exe> --device emulator-5554 --fixture <同一私有夹具JSON> --output <进程恢复日志> --process-restart
```

Debug 中有非导出的 AssistantHarnessActivity，仅用独立偏好文件验证完整页面和 Activity 重建；release 不包含该类与清单项。物理设备、发布签名、HTTPS 生产访问与商店上线均未交付。

完整实测数量、失败修复记录、APK 摘要、服务器保护与回退见第四阶段验收报告。P1/P2 两项 LF/CRLF 冻结摘要问题沿用第三阶段记录，本轮不改数据/manifest/断言，也不重复付费模型测试。
