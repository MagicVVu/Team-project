当前V1 AI收尾配置为 [v1模块](v1/README.md)（V1-P6，AI0.6.0），支持原有草稿/风险/预测及按位置反查、明确用完、关注摘要和提交后只读反馈。[交付与接入说明](../docs/versions/V1-P6/README.md)区分AI完成与正式发布；现有数据库网关不改，Jev暂缓。以下保留P0及各阶段原有使用说明。

# V1-P0 AI 开发包

V1-P5 的确认文字输入与现有数据库任务适配见[interaction/README.md](interaction/README.md)。AI侧已实现与同步，464项回归通过；规则60/60、真实模型59/60完整检查。数据库网关保持不变，App语音接入及正式发布待验收。

独立的 V1-P1 只读 AI 服务见 [p1/README.md](p1/README.md)：新增开封、整批移动、丢弃与结构化澄清续接，无新增 Mock 演示页。以下 P0 的运行方式与接口保持不变。

V1-P2 的基础风险、本地规则与统一 Manager 入口见 [p2/README.md](p2/README.md)。P2 复用 P1 操作链路，原 P0/P1 服务接口保持不变；正式前后端接入仍待验收。

V1-P3 的消费统计、条件耗尽预测、补货建议与单项草稿见 [p3/README.md](p3/README.md)。AI 实现与独立评测通过，源码已按模块同步服务器；后端规划上下文及真实预测效果待验收。

V1-P4 修复本轮测试发现的基础查询、名称、数量、日期及Android网关问题，P2/P3继承共用链路修复。交付、回归证据和离线复跑入口见 [P4记录](../docs/versions/V1-P4/README.md)。P4尚未同步远端或完成设备验收。

实现边界：AI 服务只生成草稿和读取库存事实；正式库存写入由已认证的业务后端负责。`mock` 模式另外提供内存后端替身和工程演示页，不代表正式数据库链路已验收。

## 本机直接运行

使用电脑已有的 `D:\python\python3.13.5\python.exe`；本次没有继续安装新的 Python 或修改现有依赖。实际使用版本见 `requirements.lock.txt`，支持 Python 3.12–3.13。

在 PowerShell 中：

```powershell
Set-Location 'D:\软件\大三\cs353团队项目\Team-project\agent'
& 'D:\python\python3.13.5\python.exe' -m uvicorn p0.app:app --host 127.0.0.1 --port 8765
```

打开 [工程演示](http://127.0.0.1:8765/) 或 [Swagger](http://127.0.0.1:8765/docs)。默认使用简单规则基线，不产生模型费用。演示页选择 DeepSeek 后才会使用已有 `DEEPSEEK_API_KEY`。程序不自动加载 `.env`；`.env.example` 仅列出配置键。

默认开发 token 为 `demo-local`（家庭 h1）；`demo-other-household` 对应 h2，用于隔离测试。自定义 `DEMO_TOKEN` 后，通过页面 URL 的 `?token=...` 使用；这些只属于本地 Mock，不能用于正式环境。

## 验证与评测

```powershell
& 'D:\python\python3.13.5\python.exe' -m pytest -q
& 'D:\python\python3.13.5\python.exe' export_contract.py
& 'D:\python\python3.13.5\python.exe' -m eval.run --engine rules --split test
# 以下真实调用需要已有密钥、可用网络和七天内核实的费率：
& 'D:\python\python3.13.5\python.exe' -m eval.run --engine deepseek --split dev --limit 3
& 'D:\python\python3.13.5\python.exe' -m eval.run --engine deepseek --split test
```

评测逐条结果保存在 `eval/results/`。150 条 AI 构造样本分为 90 开发 / 60 保留测试；标注尚需人工复核。冻结后不修改保留集或据其失败案例调 Prompt。更改解析逻辑后应使用新版本的保留集进行独立复测，不把旧结果当成新版本结果。

模型采用 JSON 输出、非思考模式、最多 768 输出 tokens；无 SDK 自动重试，模型请求总时限 10 秒。预算 SQLite 保存于 `.cache/p0/budget.sqlite`，调用前按输入字节上界与输出上限预留费用，未知用量保留预留费用。累计上限 20 元，Mock 重置不会清空预算。`eval/pricing.json` 使用 2026-10-08 核实的高峰、缓存未命中费率；超过七天或切换模型后，程序拒绝付费调用，需要重新核实更新费率。

## 正式服务接入

```powershell
$env:P0_MODE = 'service'
$env:P0_ENGINE = 'deepseek'
$env:BACKEND_BASE_URL = 'http://127.0.0.1:8080'
# 在本地安全配置 AI_SERVICE_TOKEN 和 BACKEND_TOOL_TOKEN，勿提交真实值。
& 'D:\python\python3.13.5\python.exe' -m uvicorn p0.app:app --host 127.0.0.1 --port 8766
```

正式服务仅有 `/health`、`/agent/message` 和文档接口，无演示页、Mock 重置或业务写入接口。缺少服务认证或后端工具配置时启动失败。后端调用 AI 时传服务 Bearer token 与已认证的 `X-User-Id`、`X-Household-Id`；浏览器不能自行指定家庭。AI 只调用 `GET /internal/v1/inventory/search`，其读凭据仍由业务后端核验用户成员关系与资源归属。

产品版本名为 `V1-P0`；运行包名 `p0`、配置变量 `P0_MODE` / `P0_ENGINE` 保持现有接口名称。

生成的 `docs/versions/V1-P0/ai-openapi.json` 是 AI 服务契约；`docs/versions/V1-P0/openapi.json` 是 Mock 已实现的团队契约草案，含请求和成功响应类型。后端保存草稿、确认写入和撤销时须使用自己的真实事务、唯一约束与乐观锁，不能复制内存 Mock 作为生产数据库层。

## 目录

- `p0/`：类型、只读 AI Manager、规则 / DeepSeek / Jev 预留适配器、读工具、Mock。
- `demo/`：工程演示页面，正常流程和异常入口。
- `eval/`：样本、费率快照、评测器、真实结果。
- `tests/`：契约、可靠性、模型故障、数据划分检查。

交付索引、需求、接口例子、页面状态与验收见仓库 `docs/versions/V1-P0/`。Jev 尚未验证；真实访谈、视觉原型定稿与正式数据库联调留有明确接入负责人。
