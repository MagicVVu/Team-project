# 团队分工

仓库地址：https://github.com/MagicVVu/Team-project

仓库负责人：[@MagicVVu](https://github.com/MagicVVu)，负责 AI 开发、仓库权限、审查协调和阶段整合。

| GitHub 账号 | 职责 | 功能分支 | 主要目录 | 访问方式 |
| --- | --- | --- | --- | --- |
| [CaviarHidon](https://github.com/CaviarHidon) | 前端与后端开发 | `feature-frontend`、`feature-backend` | `frontend/`、`backend/` | 协作者，接受邀请后可写 |
| [summerdong2006-dot](https://github.com/summerdong2006-dot) | UI 设计 | `feature-ui` | `docs/ui/`；页面实现与 CaviarHidon 协同 | 协作者，接受邀请后可写 |
| [Garin-cyber](https://github.com/Garin-cyber) | 测试与验证 | `feature-tests` | `tests/` | 协作者，接受邀请后可写 |
| [Gracie1103](https://github.com/Gracie1103) | 阅读项目内容，撰写文档；不承担代码开发 | 无需开发分支 | 阅读 `docs/`、代码、Issues 和 PR | 直接阅读公开仓库，不授予协作者写入权限 |
| [MagicVVu](https://github.com/MagicVVu) | AI、Agent、LLM、RAG 与工具调用；项目整合 | `feature-agent` | `agent/` | 仓库负责人 |

日常保留 `main`、`dev` 以及上表中的五个职责分支。`feature-team-setup` 仅用于提交团队分工配置 PR，合并后可删除。

## 加入与权限

CaviarHidon、summerdong2006-dot、Garin-cyber 的写入邀请已于 2026-10-03 发出。请登录对应 GitHub 账号，查看 GitHub 通知或邮箱中的仓库邀请并接受；接受后才能直接向仓库功能分支推送代码、文件并参与有效审查。

首次加入时，使用 README 中的完整仓库地址克隆，然后切换到自己负责的分支。CaviarHidon 可分别在前端、后端分支提交对应模块的修改。

当前仓库为公开的个人仓库。Gracie1103 无需接受邀请即可阅读内容；其角色是文档阅读与撰写，没有授予代码写入权限，也不要求承担代码审查。需要把其文档收入仓库时，由有写入权限的成员提交文档 PR。

个人仓库的协作者角色具有仓库写入权限，不能将这三位成员的写入权限限制到各自目录；分工通过约定与 PR 审查执行。main/dev 的分支保护仍对所有成员生效。

## 审查与阶段发布

- CaviarHidon 协调前端与后端改动；summerdong2006-dot 确认 UI 设计与实现效果；Garin-cyber 核对测试和验证结果；MagicVVu 协调 AI 和集成改动。
- PR 作者不能给自己的 PR 提供有效批准。至少请另一位已经接受邀请、具有写入权限的成员审查；作者为 MagicVVu 时，也需要其他成员批准。
- CODEOWNERS 当前将自动审查请求交给负责人 MagicVVu。受邀成员接受前不登记为自动代码所有者；按本表手动选择其他已加入的成员作为 Reviewer。
- 功能和设计、测试文件均通过 `feature-* → dev` PR 汇入。Garin-cyber 完成验证后记录结果，再由负责人组织 `dev → main` 的阶段发布 PR。
