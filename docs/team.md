# 团队分工

仓库地址：https://github.com/MagicVVu/Team-project

仓库负责人：[@MagicVVu](https://github.com/MagicVVu)，负责 AI 开发、仓库权限、审查协调和阶段整合。

| GitHub 账号 | 职责 | 功能分支 | 主要目录 | 访问方式 |
| --- | --- | --- | --- | --- |
| [CaviarHidon](https://github.com/CaviarHidon) | 前端与后端开发 | `feature-frontend`、`feature-backend` | `frontend/`、`backend/` | 协作者，接受邀请后可写 |
| [summerdong2006-dot](https://github.com/summerdong2006-dot) | UI 设计 | `feature-ui` | `docs/ui/`；页面实现与 CaviarHidon 协同 | 协作者，接受邀请后可写 |
| [Garin-cyber](https://github.com/Garin-cyber) | 测试与验证 | `feature-tests` | `tests/` | 协作者，接受邀请后可写 |
| [Gracie1103](https://github.com/Gracie1103) | 阅读项目内容，撰写文档；不承担代码开发 | `feature-docs` | 阅读代码、Issues 和 PR；在 `docs/` 撰写文档 | 协作者，接受邀请后可写，与其他队友权限相同 |
| [MagicVVu](https://github.com/MagicVVu) | AI、Agent、LLM、RAG 与工具调用；项目整合 | `feature-agent` | `agent/` | 仓库负责人 |

日常保留 `main`、`dev` 以及上表中的六个职责分支。团队配置使用的临时分支在 PR 合并后清理。

## 加入与权限

CaviarHidon、summerdong2006-dot、Garin-cyber、Gracie1103 的写入邀请已于 2026-10-03 发出。请登录对应 GitHub 账号，查看 GitHub 通知或邮箱中的仓库邀请并接受；接受后即可向功能分支推送代码或文档、创建 PR，并在检查通过后自行合并。

首次加入时，使用 README 中的完整仓库地址克隆，然后切换到自己负责的分支。CaviarHidon 可分别在前端、后端分支提交对应模块的修改。

当前仓库为公开的个人仓库。Gracie1103 可以直接阅读内容；接受写入邀请后，也可以在 `feature-docs` 提交文档并发起到 `dev` 的 PR。拥有相同写入权限不改变其职责，不要求其承担代码开发或代码审查。

个人仓库的协作者角色具有仓库写入权限，不能将这四位成员的写入权限限制到各自目录；分工通过团队约定执行。main/dev 的分支保护仍对所有成员生效。

## 审查与阶段发布

- CaviarHidon 协调前端与后端改动；summerdong2006-dot 确认 UI 设计与实现效果；Garin-cyber 核对测试和验证结果；MagicVVu 协调 AI 和集成改动。
- PR 不强制其他成员批准。自动检查通过、分支已同步目标分支且讨论已解决后，拥有写入权限的提交者可以自行合并；重要或跨模块修改建议主动请相关成员审查。
- CODEOWNERS 会向负责人 MagicVVu 发出可选的审查请求，不阻止自行合并。受邀成员接受前不登记为自动代码所有者。
- 功能和设计、测试文件均通过 `feature-* → dev` PR 汇入。Garin-cyber 完成验证后记录结果，再由负责人组织 `dev → main` 的阶段发布 PR。
