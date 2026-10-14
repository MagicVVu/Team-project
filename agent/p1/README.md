# V1-P1 只读 AI 服务

本阶段支持文字开封、整批移动、部分／全部丢弃及结构化澄清续接，同时支持新增、定量消耗、库存／位置查询和用户指定的采购草稿。AI 只读取事实、生成待确认草稿，不保存任务、不写库存、不执行撤销。正式前后端接入与数据库验收另行完成。

按现有 Android 首页 AI 对话面板、录入核对表单和物品详情设计输出；不提供新增 Mock 服务、演示页或假库存运行模式。现有 P0 服务不变。

## 运行与配置

在 `agent` 目录，使用现有 Python 3.12–3.13 和锁定依赖，无需新增依赖：

```powershell
# AI_SERVICE_TOKEN、BACKEND_TOOL_TOKEN 通过安全的本地环境提供，不写入仓库。
$env:BACKEND_BASE_URL = 'http://127.0.0.1:8080'
$env:P1_ENGINE = 'deepseek' # 或 rules；未配置时默认 deepseek
& 'D:\python\python3.13.5\python.exe' -m uvicorn p1.app:create_app --factory --host 127.0.0.1 --port 8767
```

不自动加载 `.env`。缺少 AI 服务认证或后端读工具配置时启动失败；后端尚未运行时，可以启动已配置的服务并查看文档，但需要库存的请求会明确返回 `TOOL_UNAVAILABLE`，不会伪造事实。无需后端即可运行下述测试和离线评测。

P1 是**内部服务**：业务后端调用时携带 `Authorization: Bearer <AI_SERVICE_TOKEN>`、`X-User-Id`、`X-Household-Id`，身份必须来自后端认证。App 不应持有此服务 token。读工具使用独立 `BACKEND_TOOL_TOKEN`，只能发 GET：

- `/internal/v1/inventory/search?name=...` → `{data:{batches:[Batch]}}`；不指定 name 时查询家庭库存。
- `/internal/v1/inventory/batches/{id}` → `{data:{batch:Batch}}`。

后端仍须验证用户成员关系及批次归属。AI 同时检查响应家庭、重复 ID 和按 ID 查询的目标一致性。

## 验证

```powershell
& 'D:\python\python3.13.5\python.exe' -m pytest tests -q
& 'D:\python\python3.13.5\python.exe' -m p1.export_contract
& 'D:\python\python3.13.5\python.exe' -m eval.p1.run --engine rules --split test
# 会产生模型费用；仅在费率已核实且有预算、密钥与网络时执行：
& 'D:\python\python3.13.5\python.exe' -m eval.p1.run --engine deepseek --split dev
& 'D:\python\python3.13.5\python.exe' -m eval.p1.run --engine deepseek --split test
```

`eval/p1/fixtures.py` 仅为测试和离线评测提供输入快照，没有 HTTP 服务或写操作，不在运行服务中加载。P1 数据集为独立 `p1-1`：150 条 AI 构造表达、90 开发／60 保留，50 个场景组各有 3 种措辞；人工复核尚未完成。按组隔离，保留集冻结；生成脚本拒绝覆盖现有文件。规则基线效果仅针对该合成集合，不代表真实用户泛化。

P0/P1 共用原有 `agent/.cache/p0/budget.sqlite`，累计上限 20 元，升级不重置。沿用 `eval/pricing.json` 的七天有效期、保守高峰费率、最多 768 输出 tokens、不思考模式和无自动付费重试。P1 为每次完整处理设置 10 秒总截止时间，覆盖模型与库存读取。结构化续接不调用模型。

结果、局限与验收状态见 [本阶段说明](../../docs/versions/V1-P1/README.md)，接口与页面映射见 [AI 接口说明](../../docs/versions/V1-P1/ai-contract.md)。
