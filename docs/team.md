# 团队分工

仓库地址：https://github.com/MagicVVu/Team-project

所有成员统一在 `dev` 开发，按目录和职责协作；`main` 保存稳定发布版本。仓库负责人 [MagicVVu](https://github.com/MagicVVu) 负责 AI、权限、联调协调和阶段发布。

| GitHub 账号 | 职责 | 工作分支 | 主要目录 | 权限 |
| --- | --- | --- | --- | --- |
| [CaviarHidon](https://github.com/CaviarHidon) | 前端与后端开发 | `dev` | `frontend/`、`backend/` | 协作者，可直接推送 `dev` |
| [summerdong2006-dot](https://github.com/summerdong2006-dot) | UI 设计 | `dev` | `docs/ui/`；页面实现与 CaviarHidon 协同 | 协作者，可直接推送 `dev` |
| [Garin-cyber](https://github.com/Garin-cyber) | 测试与验证 | `dev` | `tests/` | 协作者，可直接推送 `dev` |
| [Gracie1103](https://github.com/Gracie1103) | 阅读项目内容，撰写文档；不承担代码开发 | `dev` | 阅读代码、Issues 和 PR，在 `docs/` 撰写文档 | 同等写入权限，接受邀请后生效 |
| [MagicVVu](https://github.com/MagicVVu) | AI、Agent、LLM、RAG 与工具调用；项目整合 | `dev` | `agent/` | 仓库负责人 |

## 加入与日常工作

新克隆默认进入 `dev`。已克隆的成员保存本地修改后，切到 `dev`，再使用 Android Studio 的 **Update → 开发 → Commit → Push**。Update 选择 Merge。

受邀成员需要先登录对应 GitHub 账号，接受仓库邀请；接受后即可直接推送代码或文档到 `dev`。拥有相同写入权限不改变职责，Gracie1103 不要求承担代码开发或代码审查。

个人仓库的写入权限覆盖整个仓库，目录职责通过团队约定执行。跨目录改动提前沟通；Push 被拒绝时先 Update、解决冲突，再 Push。

## 检查与发布

- 日常开发直接提交到 `dev`，不需要个人分支、PR 或同伴批准。每次提交前运行相关检查。
- CaviarHidon 协调前后端，summerdong2006-dot 确认设计效果，Garin-cyber 记录测试结果，MagicVVu 协调 AI 与集成改动。
- 负责人确认联调结果后创建 `dev → main` PR，完成分支检查并解决讨论后合并，无需同伴批准。
- 两个分支均禁止强推和删除。`main` 还要求 PR 和状态检查，管理员同样受约束。
