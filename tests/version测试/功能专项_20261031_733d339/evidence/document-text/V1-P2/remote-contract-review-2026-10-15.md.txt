# V1-P2 远端后端契约核对

日期：2026-10-15。通过用户指定的 magicvvu_ai 账号完成只读核对。结论来自实际文件及 HTTP 结果，不再仅依赖交接文档。

## 实际可访问范围

- `/home/magicvvu_ai/workspace/agent` 可读写，是开发工作区，源码为 P1 应用 0.2.0，没有 p2/app.py；不能直接视为正式容器版本。
- `/srv/magicvvu/magicvvu-starter/backend/app` 可读，网关源码不可写。已读取网关、schema、库存 serializer 及相关测试。
- 回环 health、ready、OpenAPI 均为 HTTP 200，后端版本 0.6.0，database=ok。
- 正式 agent 目录不可读、Docker socket 不可访问，非交互 sudo 查询未获授权。不能执行正式发布或核对运行中 AI health。
- AI 工作区 Dockerfile 已核实 Python 3.12、阿里云 PyPI、UID 10002，与本地 P2 材料一致。宿主机 Python 缺应用依赖，不等于容器缺依赖。

OpenAPI、相关源码 SHA256 和 HTTP 结果保存在工作区 `.runtime/p2-integration/backend-v06-readonly-snapshot.json`，不含库存、用户凭据或 .env。

## 契约核对结果

| 项目 | 实际源码行为 | 结论 |
|---|---|---|
| AI 意图与结果 | 校验五种状态和必要元数据，返回完整 dict | 没有按 P1 枚举拒绝 QUERY_RISK |
| 结果持久化 | result_json 保存完整 data，GET 返回完整结果 | 可保留 risks、evaluated_count 和扩展 facts；需实测存储往返 |
| 澄清上下文 | 保存完整 JSON，核对 scope、revision、expires_at | P2 风险上下文的基础字段与机制一致 |
| 答案白名单 | name 已允许，并受最新 allowed_fields 限制 | 可复用风险名称续接 |
| 公开澄清结果 | 仅 revision、allowed_fields、expires_at | 符合 App 与联调客户端约定 |
| 超时 | 连接 3 秒、HTTP 客户端 13 秒 | 可容纳 AI 10 秒总截止时间，负载与故障仍待验收 |
| 库存读取 | 两个 GET、按家庭过滤、数量字符串、版本及四种状态 | 基础 P1/P2 读取兼容，真实身份正向链路待验证 |
| 不兼容数据/数量上限 | 返回 409，不静默截断或改单位 | P2 TOOL_DATA_CONFLICT 映射适用 |

因此，基础 P2 结果和名称续接不需要按原先假设重构网关响应模型。此结论是源码兼容性判断，不是端到端验收。

## 后端仍需协作的事项

1. NewMessage 暂不转发 reminder_days；默认 3 可用，非默认值需增加校验、转发及幂等指纹，避免参数被忽略。
2. 库存 serializer 仅输出 P1 字段，七个风险字段需有来源的增量接入；旧记录先返回待核对，不补造类别、标签或保存条件。
3. 澄清路由仅接受 needs_clarification；status=error 即使保存 context 也不能续接，影响工具超时后的结构化恢复。建议双方冻结恢复语义：仅在用户显式操作时允许带最新 context 且 retryable=true 的 error 任务续接，继续检查身份、修订、有效期和白名单，不自动重发模型。
4. ai_agent_smoke 仅验证不存在身份的负向权限；ai_inventory_smoke 直接调用读取函数并回滚测试事务，均不能替代跨进程真实 HTTP 正向验收。
5. 正式发布由有权限的后端操作者执行；无需给 AI 账号通用 Docker 或管理员权限。需准备专用测试用户、家庭及真实活动库存，安全配置测试用户令牌后运行 HTTP 验收工具。

后续用户明确授权“AI 代码按模块直接放在 ~/workspace/agent，文档留本地”。已完成 16 个运行文件同步、独立 Python 环境安装、导入及公开 HTTP 检查，并核实原有 27 个文件不变。此前被拒绝的交付包上传未执行，新流程不再使用交付包目录；没有正式部署、迁移或库存操作。当前需要专用测试登录态及后端发布协同。
