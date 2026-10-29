# P8.5 后端记忆与阶段保存：服务器发布记录

2026-10-29，Asia/Shanghai。已通过 `ssh magicvvu` 修改服务器后端源码、构建并切换正式后端；不是仅完成本地代码。

## 当前线上状态

- 镜像：`magicvvu/backend:p85-memory-20261029`。
- 镜像ID：`sha256:d57618b837ebad1e40ec74e75d5c3ebf608984707fc7ca9fc58ca05d0156c4e3`。
- 后端健康：healthy；后端新消息协议：`p85-dialogue-1`；现有 AI 协议同为 P8.5。
- 正式后端7个更新运行文件与候选摘要全部一致，见 source-manifest.json、verification.json。
- 当前公开 DialogueMetadata 同时接受 `p84-dialogue-1` 和 `p85-dialogue-1`。实际线上 OpenAPI 保存在 production-backend-openapi.json。
- 与发布前相比，Compose 有效配置只有后端镜像和显式协议开关两项变化；网络、TLS、认证、数据库连接、资源限制及其他服务配置一致，见 compose-diff.json。

## 实现内容

1. 从数据库真实已完成 ConversationTurn 构建 archive，按用户、家庭、当前 conversation_id 和原 created_at 的30天窗口筛选。reset 通过新 conversation_id 隔离旧会话；排除未完成轮次，最多100片段，超限标记 has_more。
2. 历史片段采用数据库保存的原文、最终公开回复和已验证 subjects。memory_id 按用户/家庭/会话/原请求确定性生成，不使用模型生成的业务对象ID。
3. 理解前与核对前分别构建同修订的 context/archive。保存完整理解计划、理解时快照和原 context_revision；resolve 接收原 plan_context_revision，不通过改写修订号消除冲突。
4. 分阶段保存 understanding、understood、resolving、resolved、responding、prepared 及 completed；调用 AI 前提交阶段记录，释放数据库连接。
5. memory_delta 在 resolve 后及最终完成事务内二次校验。核对范围、会话、修订、原请求ID、原文、原文哈希、确定性 memory_id、片段时间、原备用回复及不含伪造引用。
6. 完成时在原任务/草稿/会话事务内保存 `dialogue_v2.memory_delta`、`final_reply`、可信 `completed_at` 和 `episode_v1`。episode 使用表达后的最终回复，原 delta 保留表达前备用回复，二者不混用。
7. 只有本次后端实际提供的 archive 原引用可以进入返回白名单；仍逐字段比对，并再次检查来源任务、修订、权限和有效期。引用保持原签发/到期时间，检索历史不续期。
8. 当前回合完成时间晚于引用签发，避免将核对前 delta 时间错误地用于后来签发的引用。旧记录若没有可信完成时间，保留原创建时间和历史正文，省略无法证明时间关系的对象引用，不伪造时间。
9. 公开响应不泄露原始 archive/delta；合并 memory.truncated。回复、任务、草稿与记忆同事务完成；重复原请求返回原响应，已完成回复不重写。
10. P8.4 仍保存/读取 dialogue_v1；P8.5 使用 dialogue_v2。配置切换或关闭后，恢复始终按记录协议调度，已保存计划不再次调用理解模型。

实现入口：backend/server/app/services/memory_archive.py、dialogue.py、session_memory.py，及 app/dialogue_schemas.py。

## 验证与边界

服务器候选镜像在独立 PostgreSQL 17 容器和独立数据库上运行 **63项测试全部通过，0失败、0跳过**，见 pg-regression.xml。使用真实后端鉴权、真实 AI ASGI 路由/读取流程和真实数据库持久化，模型使用确定性测试引擎，不调用付费供应商。

覆盖：跨十轮回到旧话题并读取改变后的库存、最终表达与备用回复分别保存、完成时间/原引用有效期、100片段上限、30天窗口、不同家庭/会话隔离、排除未完成轮次、reset、伪造增量拒绝、重复请求、已保存计划恢复、P8.4/P8.5切换及关闭开关后的恢复、会话修订冲突和既有任务/草稿链路。

初次服务器测试继承了原镜像的P8.4开关，旧单阶段用例因此错误进入阶段路径；测试进程显式清空全局开关、由各夹具选择协议后，63项全部通过。未修改生产业务来迁就测试。早期本地失败记录保留为 initial-*.xml，其中数量和时区断言已改为按数值/时间语义比较，服务器最终通过报告为准。

正式发布后的只读检查确认：健康通过、实际配置启用P8.5、公开Schema支持双协议、7文件摘要匹配。会话21条、库存31条、任务27条、草稿9条、执行记录7条与发布前一致；无数据库迁移或业务库存写入。

线上OpenAPI与本地交付在仅归一化既有Pydantic Decimal字符串正则差异后完全一致；7个运行源文件原始SHA256精确一致。

**生产内正向聊天未测试。** 自动审批拒绝了创建临时生产验收身份/家庭的动作，理由是用户授权线上部署但未明确授权向生产库写入测试记录。该动作没有执行；正向验证改在独立 PostgreSQL 环境完成，正式环境只读核验。未据此声称真机、付费模型或生产聊天验收已通过。

Android 仍需接入新版公开 conversation/conversation-turns 流程，旧 conversation-messages 入口不自动获得全部会话记忆能力。本次完成并启用的是服务器后端能力。

## 发布与恢复材料

服务器目录：`/srv/magicvvu/releases/backend-p85-memory-20261029`。

- compose.before.yaml：原正式 Compose，受限权限，不下载或展示其中密钥。
- old-image.txt、backend-inspect.private.json：原镜像与配置备份。
- baseline-app、host-source-before：原容器代码及更新前服务器代码。
- compose.candidate.yaml、overlay/app、Dockerfile：候选配置和7文件覆盖层。
- build.log、build-tests.log、pg-tests-final.log、deploy.log：构建、测试与发布日志。
- verification.json、production-backend-openapi.json：发布后只读证据。

本次基于原运行镜像覆盖指定7文件，保留原商品归组等线上代码。服务器原后端源码目录也同步了对应7文件。发布脚本有健康失败时恢复原 Compose/镜像的处理，本次未触发。

后续如需停止新消息使用P8.5，应优先将新消息开关改回P8.4而保留当前双协议后端，以继续恢复已经保存的P8.5请求。完整旧镜像回滚前须评估切换后是否已有P8.5进行中请求，不能让未知结果跨协议重试。

独立测试数据库容器与测试网络已移除；生产数据库、AI容器及其预算账本未替换。下载到本目录的证据不包含私有令牌和Compose秘密配置。

当前本地契约：contracts/；重新导出可使用 `python tools/p85_adapter_export_contracts.py --output reports/p85-backend-memory/contracts`。本地导出元数据标记未部署，实际已部署状态以本目录服务器证据为准。
