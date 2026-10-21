"""LOCAL P2 AUTHORING ONLY: derive full paths from the captured deployed AST.
Does not contact a server, import app code, or deploy anything.
"""
import ast
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = ROOT / 'runtime-sources/backend/app'
main = ast.parse((SOURCE / 'main.py').read_text(encoding='utf-8'))
imports = {}
for n in main.body:
    if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith('app.routers.'):
        for a in n.names:
            imports[a.asname or a.name] = n.module.split('.')[-1]
included = []
for n in main.body:
    if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == 'include_router':
        assert not n.value.keywords, 'New include_router options need manual audit'
        included.append(imports[n.value.args[0].id])

# Reviewed decisions, including routes deliberately withheld pending approval.
WITHHELD = {
 '/api/v1/ready': 'host-only readiness; Android does not call it',
 '/api/v1/auth/register': 'unverified signup disabled; approval needed before exposing registration',
 '/api/v1/agent/reference-messages': 'reserved adapter always returns 503; no Android caller',
 '/api/v1/households/{household_id}/shopping-list': 'metadata route not called by current Android main source',
 '/api/v1/households/{household_id}/consumption-events': 'only instrumentation tests found; ordinary App caller unconfirmed',
}
FEATURES = {'auth': '账号/会话', 'households': '家庭与成员/邀请', 'inventory': '库存', 'shopping': '采购清单', 'agent_gateway': 'AI消息/任务/草稿', 'draft_execution': '能力/确认执行/回执', 'ai_inventory': 'Agent内网库存工具', 'main': '健康/就绪'}
rows = []
for module in ['main', *included]:
    file = SOURCE / ('main.py' if module == 'main' else f'routers/{module}.py')
    tree = ast.parse(file.read_text(encoding='utf-8'))
    prefix = ''
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and n.value.func.id == 'APIRouter':
            for k in n.value.keywords:
                if k.arg == 'prefix': prefix = ast.literal_eval(k.value)
                if k.arg == 'dependencies': raise RuntimeError('Router-level dependencies need manual audit')
    for n in tree.body:
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)): continue
        for d in n.decorator_list:
            if not isinstance(d, ast.Call) or not isinstance(d.func, ast.Attribute) or d.func.attr not in ['get', 'post', 'patch', 'put', 'delete']: continue
            path = prefix + ast.literal_eval(d.args[0])
            internal = path.startswith('/internal/')
            dependencies = [ast.unparse(x.args[0]) for x in ast.walk(n.args) if isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == 'Depends' and x.args]
            authenticated = 'get_identity' in dependencies
            auth = '服务Bearer + X-User/Household + 活跃用户/家庭校验' if internal else ('会话Bearer + 活跃用户校验' if authenticated else '无会话认证')
            allow = not internal and path not in WITHHELD
            ai = module in ['agent_gateway', 'ai_inventory', 'draft_execution']
            label = f'{module}_{n.name}'
            rows.append({'method': d.func.attr.upper(), 'path': path, 'function': n.name, 'source': str(file.relative_to(ROOT)), 'line': n.lineno, 'auth': auth, 'module': module, 'feature': FEATURES[module], 'ai_related': ai, 'internal': internal, 'allow': allow, 'reason': 'current Android main source caller verified' if allow else ('Docker-only service endpoint' if internal else WITHHELD[path]), 'label': label, 'proxy_read_timeout_seconds': 30 if ai else 20})
assert len({(r['method'], r['path']) for r in rows}) == len(rows)
(ROOT / 'route-inventory.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
uuid = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
lines = ['# DRAFT P2 — map entries only; included inside http-context map.', '# Generated from reviewed deployed routes. Default is denied.']
for r in rows:
    if not r['allow']: continue
    path = re.sub(r'\{[^}]+\}', lambda _: uuid, r['path'])
    # nginx map literal strings are case-insensitive; use case-sensitive regex
    # for ALL routes so method/path matching remains strict like FastAPI.
    key = '~^' + r['method'] + ':' + path + '$'
    lines.append(f'"{key}" {r["label"]};')
(ROOT / 'nginx-route-map.conf').write_text('\n'.join(lines)+'\n', encoding='utf-8')
purposes = {
 'health_check':'Android写操作前版本/目标预检', 'readiness_check':'主机数据库就绪',
 'register':'未验证手机号注册（运行开关关闭）', 'login':'手机号密码登录并创建会话',
 'current_user':'当前用户', 'logout':'撤销当前会话', 'update_profile':'修改显示名称',
 'update_household':'家庭重命名，仅owner/admin', 'create_household':'创建家庭',
 'list_households':'列出本人家庭', 'list_members':'家庭成员', 'issue_invitation':'创建单次邀请，仅owner/admin',
 'join_household':'消费有效邀请码加入家庭', 'new_message':'AI消息及持久化任务',
 'clarification':'AI补充信息', 'get_task':'恢复本人AI任务', 'get_draft':'读取本人草稿',
 'search_batches':'Agent按家庭搜索库存', 'get_batch':'Agent读取家庭批次',
 'list_inventory':'家庭库存列表', 'create_inventory':'添加库存', 'edit_inventory':'编辑库存',
 'adjust_inventory':'调整库存数量', 'delete_inventory':'软删除库存',
 'get_shopping_list':'采购清单元信息', 'list_items':'采购条目分页', 'create_item':'新增采购条目',
 'update_item':'修改待采购条目', 'delete_item':'删除待采购条目', 'purchase_item':'原子购买入库',
 'capabilities':'Android写操作前能力预检', 'reference_message':'保留接口，当前固定503',
 'execution':'草稿执行状态', 'commit':'按版本确认执行草稿', 'cancel':'取消草稿',
 'operation':'本人操作回执/恢复', 'internal_operation':'Agent按用户/家庭读取内部回执',
 'consumption_events':'家庭消耗事件，当前仅测试代码调用',
}
text = '''# P2 路由与安全审计（离线草案）

## 依据与完整性

2026-10-21 通过SSH读取当前Backend镜像源码，不导入/启动应用。镜像为
`magicvvu/backend:p72-units-736c2299edda`，镜像ID见 `P2-runtime-audit.json`。
实际启动模块 `app.main:app`；Agent启动模块为 `conversation.app:create_app`。
源码原始SHA256及脱敏源码见运行审计JSON和 `runtime-sources/`。

解析 `main.py` 中实际注册的7个router，组合每个 `APIRouter(prefix=...)` 与具体decorator路径。
得到38个API操作，已与 **运行中的 `/openapi.json` 所含38个操作逐项比对，集合完全一致**；
不是只使用工作区源码或路由局部片段。运行schema只从服务器loopback读取，没有公开它。

以下是未来入口决策，不代表已经配置Nginx。`允许`仅表示可转交Backend，认证与数据权限仍由Backend决定。
仅有当前Android main代码调用证据的30个操作进入白名单；3个内部操作和5个其他操作不进入白名单。
依据来自本地 `frontend/.../data/CloudApi.kt`、`CloudStore.kt`、`AgentClient.kt`；本次只读交叉核对，未改Android。

## 完整API清单

超时列为拟定Nginx上游读取间隔超时，非业务保证；全部当前API为JSON，无已发现的SSE/WebSocket。
`AI`表示AI相关业务，确认执行/任务查询不等于调用外部模型。

| Method | 完整路径 | 认证 | 功能 | Android公网决策 | 内部 | AI | 读取超时/流式 | 部署源码 |
|---|---|---|---|---|---|---|---|---|
'''
for r in rows:
    decision = '允许' if r['allow'] else ('禁止' if r['internal'] else '暂不开放/待确认')
    text += f'| {r["method"]} | `{r["path"]}` | {r["auth"]} | {purposes.get(r["function"],r["feature"])} | {decision} | {"是" if r["internal"] else "否"} | {"是" if r["ai_related"] else "否"} | {r["proxy_read_timeout_seconds"]}s / JSON | [{r["module"]}:{r["line"]}]({r["source"]}#L{r["line"]}) |\n'
text += '''
## 框架默认路由与未知路由

当前部署的 `FastAPI(...)` 没有关闭默认文档。只读GET实测 `/docs`、`/redoc`、
`/docs/oauth2-redirect`、`/openapi.json` 均200。环境里有没有docs开关不能替代当前代码行为。

| 路径 | Method | 认证 | 用途 | 公网策略 |
|---|---|---|---|---|
| `/openapi.json` | GET/HEAD（FastAPI默认路由） | 无 | schema | 禁止 |
| `/docs` | GET/HEAD | 无 | Swagger UI | 禁止，含子路径 |
| `/docs/oauth2-redirect` | GET/HEAD | 无 | 文档OAuth跳转 | 禁止 |
| `/redoc` | GET/HEAD | 无 | ReDoc | 禁止，含子路径 |
| `/debug`、`/metrics`、`/admin`及子路径 | 未发现已注册业务路由 | 不推断 | 运维/调试保留空间 | 一律禁止 |
| `/internal`、`/internal/`及子路径 | 包含上述3个GET | 服务凭据 | Docker内网工具 | 一律禁止 |
| 所有未列出的路径/方法 | 任意 | 不推断 | 包括未来新增路由 | 默认404，不转发 |

HEAD/OPTIONS没有为业务API另行开放。当前原生客户端没有浏览器CORS预检依赖。
白名单使用规范UUID路径，客户端现有UUID均是标准带连字符形式；尾斜线、非规范UUID未开放，
不会自动扩大到全部 `/api/v1/`。Query不参与路径白名单，仍原样交给Backend验证，日志不记录。

## 认证和数据隔离

- 运行版本使用Argon2密码哈希、随机opaque Bearer token、服务端保存token SHA256，默认12小时到期；并非JWT。
- `get_identity` 校验会话存在、未撤销、未到期及用户active，缺凭据返回401；本机 `GET /api/v1/users/me` 实测401。
- 家庭库存/采购依赖成员关系且按家庭过滤。同家庭成员按现有共享规则访问库存，不能将这误述为同家庭内也完全按创建者隔离。
- AI任务/草稿/操作回执校验当前用户及家庭成员身份；写入保持版本校验和原有幂等语义。
- 家庭rename/invitation中的owner/admin属于家庭业务角色，不是宿主机管理接口，App确有调用，保留Backend角色校验。
- 内部 `_authorize` 校验独立 `BACKEND_TOOL_TOKEN`，并校验可信X-User/Household及活跃家庭成员关系；Agent的 `AI_SERVICE_TOKEN` 也已配置（只记录存在性）。
- Nginx不创建身份、不验证/重写Bearer；覆盖外部可伪造的Forwarded头并清空内部身份头。

## 待确认和不可自动扩大的范围

1. **注册**：App有注册入口，但服务器 `AUTH_ALLOW_UNVERIFIED_SIGNUP=false`，运行代码明确警告不适合公网开放注册。
   草案拒绝注册；这意味着新用户注册流程不可用，已有测试账号登录可用。不得宣称所有App功能无条件兼容。
   若需要手机注册，要另行确认防滥用/身份验证和开放范围，不能仅为通过验收打开注册开关。
2. **ready**：主机检查继续从loopback访问，App只需要health，不公开数据库就绪信息。
3. **reference-messages**：保留协议当前固定503，当前AgentClient未调用，拒绝；不因AI相关就公开。
4. **shopping-list元信息**：当前main客户端只取 `/shopping-list/items`，元信息操作暂不开放；若真实安装包依赖需提供对应源码/调用证据再审核。
5. **consumption-events**：仅发现instrumentation测试调用；业务main客户端调用未确认，暂不开放。后续确认要保留测试能力时单独加精确GET。

## AI完整链路、超时和中断

Android `CloudApi`（连接5s、读取20s）→ Backend `agent_gateway._call_ai`
（连接3s，其余httpx阶段13s、无重定向、trust_env=false）→ Docker `agent:8767` →
`conversation.app`/`p3.app` 创建 `conversation.Manager` → 继承 `v1.Manager/Operation`，
整个Agent operation受 `asyncio.timeout(10)` 约束。DeepSeek payload `stream:false`，
模型请求也有10s墙钟约束且无SDK自动重试；内部库存工具HTTP读取5s，位于operation总预算内。
不能把每个5s/10s/13s简单相加，也不能把httpx阶段超时当成整个Backend请求绝对上限。

Agent通过 `http://backend:8000/internal/...`（具体配置目的主机只读核验见运行证据/固定网关设计）回读，
不经公网Nginx。公网阻断 `/internal/` 保留内网调用能力。当前Backend没有注册
`/internal/v1/planning/context`，而Agent RemoteReader包含该可选依赖；代码定义了
`PLANNING_CONTEXT_UNAVAILABLE`降级。此既有能力缺口不在P2修复，不声称完整规划功能已通过实测。

草案普通API读取20s、AI相关30s、连接3s、发送15s，给数据库操作/序列化留余量。
Android读取仍为20s，因此手机可能先于Nginx超时；P4需按专门测试构建审查，P2不修改。
`proxy_read_timeout`是两次读取之间的空闲超时，不是全请求硬截止。
当前没有流式输出：保留JSON请求缓冲，关闭响应缓冲和响应磁盘临时文件；未来增加流式协议必须重新审计。
请求体上限64KiB，与当前1000字符AI输入、1500字节补充字段及小型库存JSON相容；当前没有音频/图片上传API，照片由客户端本地保存。

客户端断开时 `proxy_ignore_client_abort off` 让Nginx关闭上游连接，但ASGI同步/异步处理或已提交事务不保证被撤销。
`proxy_next_upstream off` 禁止代理自动重放写请求。必须用既有request_id/operation_id和回执恢复，不能以超时推断“写入未发生”。

## 安全结论

当前运行登录函数未调用LoginGuard，也无已确认的账号级公网防爆破措施，不能从工作区较新代码推断线上已有。
草案补充每源IP登录5次/分钟、全站登录10次/分钟（均突发3）、API每源10次/秒（突发30）、总并发16，返回429。
这只是单手机低并发场景的入口缓解，分布式攻击、持有其他有效账号、应用级审计与实际设备绑定仍未解决。
P2只完成配置和静态检查；Nginx语法、转发、限流和日志行为均需P3在实际安装版本验证。
'''
(ROOT / 'route-security-audit.md').write_text(text, encoding='utf-8')
print(f'{len(rows)} deployed API operations; {sum(r["allow"] for r in rows)} allowed; {sum(not r["allow"] for r in rows)} withheld/internal')
