# Agent 内部 Jev 决策模块

Jev 是现有 Agent 内的可选模块，复用现有 Python、Pydantic、httpx 和 pytest，没有独立环境、依赖文件或服务进程。2026-11-01 增加了 P8.6 的可选业务接入，并按用户追加授权完成服务器 AI 镜像替换，**线上默认关闭**；独立实验入口继续保留。接入行为仍待测试负责人验证。

独立实验入口仍只处理显式标记为 `synthetic: true` 的合成场景。新增业务适配器使用不同的最小输入，不将真实请求伪装成合成数据；通过原 P8.6 读取/解析流程工作，不提供库存或采购写入工具。

## P8.6 可选接入（2026-11-01，待测试负责人验证）

仅接入 `conversation.autonomous.app:create_app` 的 `/agent/dialogue/run`。原 P7、P8.4、P8.5 工厂与独立实验 CLI 不因这个开关自动切换。没有新增 App 设置、公开开关接口或请求字段。

服务端启动配置选择 `JEV_MODE=off`（默认）或 `JEV_MODE=assist`；Python 工厂也可显式传入 `create_app(jev_mode="off", ...)` 或 `create_app(jev_mode="assist", ...)`，参数优先于环境变量。显式 `off` 会取消路由器注入，不读取 Jev 密钥、不加载业务适配器。配置在创建服务时固定，改变后需重建应用/重启对应进程。

`assist` 模式读取服务端进程的 `TYPESAFE_API_KEY`，继续使用原 `jev-1.13.0` 和累计一美元账本，不自动解密 Windows 本机凭证。不另开服务，不切换现有 DeepSeek 引擎。

- 原字面控制、序号选择和明确引用等零模型路径先执行，通常不调用 Jev。
- 其余请求在原总时限内最多增加一次 Jev 请求，将四节点与说话方式/多动作判断批量求值，子预算最多两秒。
- 当前只对没有活动任务、引用或候选选择的明确单物品数量/位置查询尝试省略 DeepSeek 理解；名称必须是原文中的严格字面片段，后续仍由原作用域读取器核对事实。
- 多个节点需一致、最高选项概率至少 0.9、confidence 至少 0.8、多动作概率不超过 0.2，才考虑该窄范围分支。这些是未校准的保守初值，不代表已验收准确率。
- 其他任务继续交给原 DeepSeek/代码流程，只附加有限的 Jev 枚举提示，不让 Jev 提取任意字段、选取业务 ID 或绕过确认。
- 若 Jev 高把握判断为询问、计划、否定，而原计划试图生成变更，则要求用户明确意图；不直接执行变更。
- 缺密钥、限流、预算不足、响应错误、超时或存储不可用均返回原流程。回退仍受原总截止约束，不保证额外获得一整轮时间。

适配器只接收本轮原文、当前是否存在活动任务/引用的布尔值及逐件库存语义，不发送库存行、聊天历史、用户/家庭 ID 或执行回执。原鉴权与上下文校验先于 Jev 调用。

新增 `runtime.py` 保持实验 `DecisionRequest.synthetic=true` 和旧评测资料原样。响应不增加顶层字段，在已有 `trace` 内增加 `action="jev"` 的步骤及 `jev` 元数据；实际 Jev HTTP 尝试计入 `model_calls`，并单独记录 USD、token、来源和节点结果。原后端以字典接收 trace，无需改动业务后端；统计比较时仍需分别汇总 DeepSeek 人民币和 Jev 美元，不能直接相加。

Docker 仅复制 Jev Python 运行文件，测试、样本和凭证不进入镜像；模块缓存链接到现有 `/app/agent/.cache/jev`。部署时须继续持久化原 Agent 缓存，沿用既有账本，不能清零或用空账本代替累计记录。源码同步白名单已补齐运行文件；服务器已在原 AI 镜像上叠加相关文件，发布为 `magicvvu/agent:p9-jev-172dbc3b84b8`，健康接口返回 `jev_mode=off`、`jev_status=disabled`。后端、数据库、私有环境和缓存挂载保持不变。

按用户要求，本轮接入与部署没有运行测试、评测或真实调用，仅核对容器健康、配置和源码摘要。启用/关闭、故障回退、复合计数、权限和逐件库存行为由测试负责人验证。发布、备份与回退见 [V1-P9 阶段记录第七节](../../docs/versions/V1-P9/阶段工作记录.md)，脱敏证据在 [`reports/jev-integration/production-20261101/`](../../reports/jev-integration/production-20261101/)。

## 当前验证状态

交付记录见 [validation-summary.json](validation-summary.json)，实现与限制见 [开发与验收记录](开发与验收记录.md)。

四节点、HTTP 协议校验、预算、模拟与回放、CLI、300 条样本均已实现。2026-10-24 已通过本机加密密钥完成一个合成场景的真实冒烟验证：`jev-1.13.0` 两次请求成功，四节点均返回有效响应，总耗时约 2.35 秒，账本费用 0.0001302 美元。该样例最终为 `CLARIFY`，仍需检查多动作判断和澄清策略；单次连通验证不能作为模型准确率或稳定性验收。

## 使用现有环境运行

在现有 `agent` 目录执行。以下 `python` 指已经安装项目依赖的解释器；本次验证实际使用 `D:\python\python3.13.5\python.exe`。

```powershell
python -m jev check
python -m jev budget
python -m jev decide --input jev/datasets/example.json
python -m jev node intent_router --input jev/datasets/example.json
python -m jev evaluate --provider mock --split dev
python -m jev evaluate --provider mock --split calibration
python -m jev evaluate --provider mock --split test
python -m jev report --input jev/.cache/reports/example/run.json --output jev/.cache/reports/rebuilt
```

`check` 和 `budget` 为同步只读检查，不创建事件循环或账本，不发起模型请求。Mock 是故意保持简单的字面规则基线，不是 Jev 仿真模型。默认不调用真实 API。

真实调用需要先在自己的终端安全注入 `TYPESAFE_API_KEY`，然后显式选择 `live`：

```powershell
python -m jev check
python -m jev decide --provider live --input jev/datasets/example.json
python -m jev evaluate --provider live --split dev
```

密钥只读取当前进程环境，不自动读取任何 `.env` 或其他服务私有配置。不要将密钥写进样本、命令参数、源码或聊天。没有密钥时返回 `MODEL_NOT_CONFIGURED`，不创建预算账本。

### Windows 本机隐藏输入与加密保存

也可以使用模块内的显式启动脚本，在弹出的密码输入框中粘贴密钥，并用 Windows 当前用户的 DPAPI 加密保存到被 Git 忽略的 `.cache/credentials`。脚本只向本次 Python 子进程注入环境变量，结束后恢复原进程变量，不修改系统/用户全局环境或旧服务配置。

```powershell
# 首次配置并只做本地检查，不调用模型：
powershell -NoProfile -ExecutionPolicy Bypass -File jev/local.ps1 -Configure
# 首次配置后运行一次合成场景（最多两个真实请求）：
powershell -NoProfile -ExecutionPolicy Bypass -File jev/local.ps1 -Configure -Action Smoke
# 后续显式加载本机加密密钥：
powershell -NoProfile -ExecutionPolicy Bypass -File jev/local.ps1 -Action Check
powershell -NoProfile -ExecutionPolicy Bypass -File jev/local.ps1 -Action Smoke
# 用假密钥验证本机 DPAPI 保存/读取，不读取真实密钥、不联网：
powershell -NoProfile -ExecutionPolicy Bypass -File jev/local.ps1 -SelfTest
```

脚本不接收密钥参数，也不会输出密钥。加密内容只能由对应 Windows 账户解密，不应复制到其他机器使用。普通 `python -m jev` 仍只读进程环境，不会自动读取本机加密文件；要使用加密文件需显式运行上述脚本。

配置和合成检查的脱敏状态写入 `.cache/setup/state.json`，模型结果写入 `.cache/setup/live-smoke.json`；预算仍沿用模块原有的一美元累计账本。替换密钥使用 `-Configure`，不会重置账本。

每次成功真实调用会录制去除原始输入的响应。重放同一场景：

```powershell
python -m jev decide --provider replay --input jev/datasets/example.json
```

回放按模型、问题版本、完整状态摘要和选项顺序匹配。缺失返回 `REPLAY_MISS`，损坏返回 `INVALID_REPLAY`；不会自动转真实调用。回放记录中的 token 为历史用量，本次费用为零。

退出码：`0` 表示命令完成（包括正常返回需要澄清）；`1` 表示提供方、配置、预算或运行依赖失败；`2` 表示输入或本地文件不合法。

## Python 接口和事实边界

```python
import asyncio
from pathlib import Path
from jev import Engine, DecisionRequest

request = DecisionRequest.model_validate_json(
    Path("jev/datasets/example.json").read_text(encoding="utf-8")
)
result = asyncio.run(Engine().evaluate(request))  # 默认 Mock
print(result.final_action, result.reasons)
```

真实提供方显式创建：

```python
from jev.config import Config
from jev.providers import LiveProvider

engine = Engine(LiveProvider(Config.from_environment()))
```

`DecisionRequest` 包含原文、请求 ID、带时区时间及 `Facts`。后者包含由夹具/未来调用方提供的已提取字段、候选、选定对象、缺项、冲突、任务状态和能力。默认事实未知。`scope_valid` 等只是实验输入，不构成实际鉴权证明。

四节点为 `intent_router`、`event_classifier`、`clarification_gate`、`action_gate`。完整流程最多两次请求：第一轮判断意图、事件、说话方式和多动作，第二轮在明确上游结果与场景事实基础上判断澄清和动作。节点独立返回成功、跳过或失败；结果保留实际来源、概率、模型版本、费用、耗时与错误。单独运行某个节点时，最终动作固定为 `WAIT`，避免将局部判断误当成完整策略。

调试第二轮节点必须显式提供上游结果：

```python
from jev.schemas import Node, NodeState

full = await engine.evaluate(request)
upstream = {
    n.value: full.nodes[n].answer for n in (Node.INTENT, Node.EVENT)
} | full.auxiliary
single = await engine.evaluate_node(
    Node.ACTION, NodeState(request=request, upstream=upstream)
)
```

CLI 的第二轮 `node` 输入对应 `{"request": <DecisionRequest>, "upstream": <四个第一轮答案>}`。缺失上游返回 `UPSTREAM_REQUIRED`，不擅自调用前置模型。

## 业务约束

- 变更最多建议 `CONFIRM`；没有 `EXECUTE` 或数据库执行器。
- 字段缺失、单位冲突、目标不唯一、事件矛盾要求澄清。
- 事实未知、范围未核实、能力不可用、任务未就绪、引用失效、版本未核实或终态批次，返回等待。
- 明确的询问、否定、假设、未来计划不能因模型高置信而变为可确认的库存变更。
- 复用 `p0.domain` 中无副作用的单位校验与转换，检查超库存；不导入旧 Manager、数据库客户端或旧 Jev 占位。
- “全部用完”是语义标签 `FINISHED`，不代表自动新增数据库事件。未来由旧业务的消耗/终态逻辑承接。
- confidence 只被保留和评测。首版 `calibrated=false`，不以分数自动授权业务动作。
- `raw_action` 是模型建议，`final_action` 是约束合并后的建议；两者均不是已执行回执。

## 真实调用和费用

固定 `jev-1.13.0`，固定官方 HTTPS 地址，不跟随重定向，不使用代理环境、不重试、不自动降级。单请求截止 4 秒，完整流程总截止 10 秒，评测串行。

费率版本为 2026-10-23 核对的每百万输入 token 0.042 美元、输出免费。以整数纳美元记账，避免浮点累计误差。每次 HTTP 尝试前按 65,536 输入 token 上界预留，只有合法响应及 usage 验证通过后才按实际量结算。错误、取消或未知 usage 保留全部预留；上限 1 美元，跨进程原子检查、跨运行保留，不自动增加额度。

账本位于本模块 `.cache/budget.sqlite`，不复用、覆盖或重置 DeepSeek 人民币账本。不要删除账本规避累计额度；未知用量可以通过预算命令检查，首版不提供自动退款或重置命令。

官方依据：[API](https://docs.typesafe.ai/api/system-one)、[模型及费率](https://docs.typesafe.ai/models)、[置信度含义](https://docs.typesafe.ai/confidence)。费率和模型发生变化时，应先核对并版本化配置，再开始新实验。

## 数据和报告

`datasets/samples.jsonl` 共 300 条、100 组、20 类合成场景。每组同义/语气变体保持在同一切分中：开发 180、校准 60、保留 60。默认加载会验证 manifest 文件哈希。样本原文/场景与预期标签分别存储；标签、切分和审核字段不进入模型 payload。

这是 AI 编写的合成数据，`human_reviewed=false`，没有真实音频；同一商品与共享词汇限制了外推能力。不要把离线 Mock 高分、回放结果或未人工审核标签作为真实模型产品验收。保留集不用于调参；如发现标签缺陷，必须版本化记录，不能静默修改。

报告包含四节点准确率/macro-F1/混淆矩阵、澄清召回和冗余率、潜在危险原始动作建议及拦截数、最终动作准确率、调用次数、已结算或保留费用、P50/P95、失败和未尝试样本数。Mock、Replay、Live 分别标记。Mock 耗时不包含真实网络；本模块耗时也不是 App 端到端耗时。

```powershell
python -m pytest jev/tests -q
# 旧 P4 测试还需要仓库根目录在导入路径：
$env:PYTHONPATH = (Get-Location).Path + [IO.Path]::PathSeparator + (Resolve-Path '..').Path
python -m pytest tests jev/tests -q
```

真实冒烟测试默认跳过；只有同时提供 Jev 密钥和 `JEV_RUN_LIVE_SMOKE=1` 才会产生付费请求，仍使用同一个累计预算。Windows 受限沙箱如阻止 asyncio 的本机 socketpair，应在允许本机事件循环的测试环境运行，不需要修改应用代码。

## 原独立阶段边界与后续上线

2026-10-24 的独立阶段没有修改旧流程。2026-11-01 已按用户授权增加上述可选适配器及构建/同步文件声明，并完成服务器 AI 版本替换，Jev 仍默认关闭；没有修改旧实验数据、旧 `Decision` 或数据库执行协议。正式请求使用业务适配输入，不能伪装成 `synthetic=true`。

未来接入仍须验证原有鉴权、引用、任务修订、库存版本、确认和事务；本模块不替代这些检查。
