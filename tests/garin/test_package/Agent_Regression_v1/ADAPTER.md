# 更换软件版本时的适配接口

评分脚本仅依赖Python标准库。local_p0适配器需要原项目的依赖。以后可以添加 adapters/my_version.py，使用：

```bash
python run.py --adapter adapters.my_version --version V2-commit123
```

适配器是同步函数`evaluate(case: dict, config: dict) -> dict`。每条用例开始前建立隔离fixture，每条结束后清理；不得连接真实用户库存，不得从expected生成被测软件输出。

## message返回值

```python
{
    "result": {  # 来自真实被测程序；统一映射为此格式
        "status": "needs_confirmation",
        "intent": "ADD",
        "reply": "...",
        "trace_id": "实际追踪ID",
        "original_text": "买了2盒牛奶",
        "draft": {"action":"ADD", "name":"牛奶", "quantity":"2", "unit":"盒",
                  "batch_id":None, "expected_version":None, "location":None,
                  "purchased_at":None, "label_expiry":None},
        "facts": [], "candidates": [], "missing_fields": []
    },
    "before": {"inventory": "独立读取的实际库存", "events": "实际事件", "plans": "实际清单"},
    "after": {"inventory": "调用后独立读取", "events": "调用后独立读取", "plans": "调用后独立读取"},
    "execution": "说明真实模型/规则，真实后端/Mock"
}
```

before/after是完整可比较JSON快照，不要包含每次读取都会变化的时间戳。AI服务本身不能提供状态证明时，应从测试后端读取。无法获取证据时抛NotImplementedError，不能硬填相等值。当前local_p0直接比较Mock完整state，消息阶段没有草稿持久化；新版网关如允许保存草稿，应比较库存、事件和采购清单等业务状态，把草稿保存单独留证。

draft严格检查字段集合及值（显式null也必须存在）；数量用Decimal比较，不以浮点近似判断。facts按ID排序比较完整对象；candidates比较预期ID集合和家庭归属。流式输出需等到完整响应后再归一化。

## flow与scenario

flow包含按顺序执行的steps。local_p0演示了HTTP请求、响应捕获、引用、HTTP状态码、业务字段和事件增量断言。后续真实适配器需实际调用软件并检查状态。返回`{"failures": [...], "steps": [...], "execution": "..."}`；空failures表示适配器真实检查全部通过。不能直接返回空列表跳过检查。非确定性ID用capture捕获，不写死。

scenario是人工设计的场景规格，尚无自动实现。未来实现对应驱动后，可按相同flow观察格式返回并扩展评分入口；同时把kind改为flow并写好可执行步骤，更新套件版本。未实现必须抛NotImplementedError，记录BLOCKED。

## 固定库存 seed-v1

所有默认用例在每次运行前从此状态开始；版本均为1，日期均null。

|ID|家庭|名称|数量|单位|位置|状态|
|---|---|---|---:|---|---|---|
|milk-1|h1|牛奶|2|盒|冰箱上层|ACTIVE|
|milk-2|h1|牛奶|3|盒|冰箱下层|ACTIVE|
|bandage-1|h1|创可贴|10|片|客厅/医药箱|ACTIVE|
|detergent-1|h1|洗衣液|500|ml|null|ACTIVE|
|tissue-0|h1|纸巾|0|包|储物柜|FINISHED|
|private-1|h2|大米|2|kg|厨房|ACTIVE|

默认作用域u1/h1；跨家庭测试使用u2/h2。库存事件、草稿及采购计划初始为空。不能按顺序累积前一个样本的库存变化。

## 增加新用例

复制同类JSON行，使用新唯一ID；填写category、scope、fixture、gate、source、human_reviewed与expected。模糊规则用review，不擅自设置唯一意图。人工确认后记录reviewer/date。每次修改重建manifest哈希并更新CHANGELOG.md；运行器会额外记录实际读取文件的哈希。
