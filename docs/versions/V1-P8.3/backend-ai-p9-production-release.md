# P9 生产发布记录

2026-10-26（Asia/Shanghai），用户已明确授权“推送和部署生产”。本次按既有受控Compose流程，仅替换backend.image，并执行增量0011迁移；AI镜像、数据库容器、端口、HTTPS入口、认证和自动提交开关保持。

## 发布准备

- 原dev上的历史报告提交f4f6837已保留，与P9提交ce1a0ad无冲突合并。
- 生产仍是P8.2，后端/AI/DB均healthy，约30GB可用空间。
- 新镜像基于实际P8.2镜像，复用Python3.12.15、Pydantic2.14.1、FastAPI0.116.1及其既有依赖，继承原启动入口和TLS挂载。
- P9健康和能力声明更新为V1-P9，新增app.p9_preflight，独立检查0011与新表；不篡改旧P8预检的历史版本要求。
- 元数据及相关回归32 PASS / 2 SKIP，见release-metadata-tests.xml。前一轮完整双库与AI测试证据保留。
- 发布脚本与源码位于服务器`/srv/magicvvu/releases/backend-p9-20261026`，目录0700。完整自定义格式数据库备份、角色备份、Compose/env备份仅保存在服务器私有目录，未进入Git或聊天。
- 在线备份已在独立internal网络、临时PG17中恢复，角色/数据恢复、0011迁移、全部旧字段哈希和alembic check通过。正式后端在演练期间持续运行。
- 首次临时库演练遇到镜像初始化Unix socket临时服务重启窗口，改为TCP就绪后演练通过。正式服务和生产数据未受该演练影响。

## 执行与恢复边界

发布前检查无活动会话租约；短暂停止后端以取得最终一致备份，再执行带5秒锁等待/60秒语句超时的事务迁移，比较全部旧业务字段，然后启动P9后端。数据库和AI不重建。

若尚无P9新业务证据，可回退P8.2应用镜像、保留新增schema；有P9事件后旧版规划读取器不能理解普通账本事件，因此不能无条件切回旧镜像。脚本发现新回执时禁止自动旧镜像回退，应保留数据并修复/前向发布。整库恢复会覆盖后续新写入，未列入自动回退，不会擅自执行。

自动审批曾将生产专用家庭、最多一次付费DeepSeek调用及脱敏生产元数据发布判为需要单独明确授权。用户随后逐项明确批准；下述验收在收到授权后执行。密码、Token、私钥、备份内容和真实用户明细均不推送GitHub。

## 最终发布结果

- 已正常推送到origin/dev，生产源码提交`a70266765242d45a6cfd8432b5fa2a158884e10d`。Git直连GitHub失败后，单次命令使用系统已启用的本机代理完成推送，没有修改全局Git或网络配置。
- 正式后端镜像：`magicvvu/backend:p9-20261026`；镜像ID为`sha256:80cbec534a0cc871385733c6d37ce894547acce2f1dbef4a2499bdcd11943de2`。
- 后端应用与Alembic源码摘要：`0070a7caeb5a4bd4de3a5f729fd7799b1bab81c965817f6bd4132f4f92e91dbd`；镜像标注了源码提交和摘要。
- 正式数据库已从0010迁移到`20261026_0011`。迁移前后17张旧业务表的全部旧字段、行数和哈希一致；只增加预期的新表/列与版本变更。
- P9只读预检16/16通过；backend/agent/db均healthy。AI和数据库容器ID不变；后端环境、挂载、发布端口、Compose环境文件逐项确认不变。
- 最终一致备份已保存并计算SHA256；自定义格式dump为76907字节，含角色的完整备份仅在0700发布目录，不提供普通Git下载链接。
- 发布后日志采样未发现Traceback或FATAL。自动提交仍false、manual_plan_only仍true；AI仍P8.2/DeepSeek，人工规则不伪造或改计数。
- 已按后续明确授权创建一个专用生产验收家庭并完成业务验证；共1次真实DeepSeek模型调用，未重试付费请求。详见下一节。
- 服务器本地同一既有8000→8443 TLS入口验证通过：使用现有公开证书作显式信任锚，开启证书及IP主机名验证；health为P9/200、无认证capabilities为401、内部规划公网路径为404。没有读取私钥或关闭TLS校验。
- 从本机直接访问公网IP:8000以及经现有系统代理补查均超时；外部公网可达性未确认，不能把服务器本地TLS通过等同外网可达。本轮未改变任何网络规则，未为排查开放新端口。
- 完整备份保存在同一服务器的受限目录，已完成隔离恢复演练；这不是异地容灾备份。

## 获准后的生产专用家庭验收

证据：[production-release-acceptance.json](../../../reports/backend-ai-p9/production-release-acceptance.json)与[独立复核](../../../reports/backend-ai-p9/production-release-acceptance-final-check.json)。专用家庭标识`P9_RELEASE_ACCEPTANCE_20261026T044402Z`。

| 项目 | 实际结果 |
| --- | --- |
| ADD/MOVE/CONSUME/PLAN_ADD/OPEN/DISCARD | 六类确认执行、重复提交同回执、原操作读取均通过；草稿来自明确标记的验收夹具，并非六次真实模型生成 |
| AI操作反馈 | 五种库存动作均partial，体现资料/覆盖未知；PLAN_ADD按原库存反馈契约为not_applicable，不伪装采购专用反馈已实现 |
| 采购来源清空/重新关联/延迟重试 | 均通过，旧回执没有覆盖新关联 |
| 采购完成及重试 | 新建批次一次，重复购买没有重复入库，继承商品映射 |
| 商品聚合 | 同商品两批，合计5盒；批次保留 |
| 调整/更正/消费账本 | 调整和更正不计消费；真实Consumed事件恰好1条、数量1盒 |
| 自动建议重验 | 未知风险规则继续阻断；确认返回PLANNING_REVALIDATION_UNAVAILABLE，没有新增自动采购 |
| 真实DeepSeek会话 | 1次请求/1次模型调用成功，查询任务answered；读取两批库存均属于专用家庭，总计5盒 |
| 会话恢复和重新读取 | 原request_id的GET恢复与会话历史通过，没有再次发起付费请求 |
| 测试账号收尾 | 已停用，全部测试会话已撤销，账本和固定草稿保留作为审计证据 |
| 既有业务数据 | 验收前已有100条记录逐条比较，全部未变 |
| 验收后服务复核 | P9只读预检16/16，正式三容器健康，自动提交仍关闭 |

一次性运行标记与详细结果保存在服务器0700发布目录；脚本拒绝自动重跑，避免重复调用模型或重复创建测试家庭。生产测试没有停机、未修改AI代码或真实家庭库存。

其余发布证据在`reports/backend-ai-p9/production-release-deploy.json`、`production-release-build.json`、`production-release-rehearse.json`、`production-release-final-data.json`、`production-release-verify.json`、`production-release-https.json`和`production-release-public-probe.json`。原五份文档中的开发阶段测试与限制保留；后续生产状态以本文件和production-release-*.json为准。
