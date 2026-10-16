# MagicVVu 云端后端 v0.7

此目录保存从 `magicvvu:/srv/magicvvu/magicvvu-starter/backend` 导出的 v0.6 服务及 v0.7 购物清单接口，作为云端服务的可维护源码。仓库原有 `backend/app.py` 是设备快照 AI 网关，入口与本服务不同。本服务入口为 `app.main:app`，构建上下文是本目录。

本次无需数据库迁移，继续使用 `20261014_0005`。沿用现有登录、家庭权限和 P1 只读 AI 网关。

## 接口

所有接口携带 `Authorization: Bearer <登录令牌>`。基础路径：

`/api/v1/households/{household_id}/shopping-list`

| 方法 | 后缀 | 作用 |
| --- | --- | --- |
| GET | 无 | 家庭唯一共享清单信息 |
| GET | `/items` | 分页读取购物项 |
| POST | `/items` | 添加待购物品，返回 201 |
| PATCH | `/items/{item_id}` | 修改未购物品 |
| DELETE | `/items/{item_id}` | 删除未购物品，返回 204 |
| POST | `/items/{item_id}/purchase` | 勾选购买并原子入库 |

查询参数 `status=pending`（默认）、`purchased` 或 `all`；`limit=50`（1–100）、`offset=0`。返回 `items`、`total`、`limit`、`offset`。按创建时间倒序、ID 升序排序；分页期间发生新增/删除时应刷新列表。

新增请求：

```json
{"name":"牛奶","quantity":"2.125","unit":"盒"}
```

名称及单位去除首尾空白且不可为空。数量大于 0、最多三位小数、最大 `999999999.999`，与现有购物表精度一致。修改支持其中任意字段，不接受空对象或显式 null。禁止客户端设置添加者、购买者或勾选状态。

购买请求必须发送 JSON 对象，无需补充字段时发送 `{}`：

```json
{"storage_location":"冰箱","expires_on":"2027-01-01"}
```

返回 `item`、`inventory_item`、`newly_stocked`。库存包含 ID、名称、数量、单位、位置、到期日期、购买日期、来源购物项、创建者、状态与版本。数量使用 JSON 字符串，避免浮点精度损失。购买日期沿用服务器 UTC 日期。

同一项重复购买返回同一库存 ID，`newly_stocked=false`，保留第一次购买的购买者、位置和日期；重复请求中的新位置/到期日期不覆盖已有库存。并发购买通过 PostgreSQL 行锁及来源唯一约束防止重复入库。不同购物项即使同名也创建独立批次。

已购买条目继续保留，可通过 `status=purchased` 查询；修改/删除返回 409，再买一次应创建新条目。旧的已购项若没有关联库存，返回 409，需人工核对，避免重复入库。

未登录返回 401；非家庭成员或跨家庭购物项返回 404；请求字段不合法返回 422。清单缺失返回 409，不擅自生成历史清单。

## 本地测试

```powershell
cd backend/server
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -q tests
```

测试使用临时 SQLite，不需要真实数据库密码。`tests/check_shopping_postgres.py` 另用于独立 PostgreSQL 的真实行锁、并发购买、编辑/购买竞争、删除/购买竞争、事务回滚和家庭隔离验证。它要求 `DB_NAME=magicvvu_shopping_test`、`SHOPPING_TEST_ISOLATED=yes` 和空数据库，先执行 `alembic upgrade head`，不得连接业务库。

## 部署

先备份现有 `backend/`、`deploy/compose.yaml` 和 PostgreSQL 自定义格式转储，并验证备份可读；构建新镜像 `magicvvu/backend:shopping-v0.7` 后，只更新 Compose 中 backend 的镜像标签并重建该服务。部署期间后端短暂重启。保留既有数据库、agent、网络、环境密钥和端口绑定。

如需回退，恢复备份的 Compose 配置及 backend 源码，并重新启动 backend，旧镜像 `magicvvu/backend:agent-gateway-v0.6` 仍可使用。本版本无需数据库降级；新增购物记录属于现有表的兼容数据。
