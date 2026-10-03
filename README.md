# Team-project

CS353 团队项目仓库，采用 `feature-* → dev → main` 协作流程。

仓库地址：https://github.com/MagicVVu/Team-project

## 分支与合并

| 分支 | 用途 | 合并方式 |
| --- | --- | --- |
| `main` | 稳定、可演示、可提交的阶段版本 | 联调通过后，由 `dev` 发起 PR |
| `dev` | 团队日常整合 | 各功能分支通过 PR 汇入 |
| `feature-frontend` | 前端页面 | PR 到 `dev` |
| `feature-backend` | API、后端业务与鉴权 | PR 到 `dev` |
| `feature-agent` | Agent、LLM、RAG 与工具调用 | PR 到 `dev` |
| `feature-ui` | UI 设计与设计资料 | PR 到 `dev` |
| `feature-tests` | 测试与验证 | PR 到 `dev` |

`feature-team-setup` 是团队分工配置 PR 的临时分支，合并后可删除，不是成员的日常开发分支。

`main` 和 `dev` 要求通过 PR 合并，至少获得一位其他成员批准，并通过分支流向检查、解决审查讨论。禁止强制推送和删除这两个分支；规则同样约束管理员。

仓库负责人：[@MagicVVu](https://github.com/MagicVVu)，负责 AI；CaviarHidon 负责前后端，summerdong2006-dot 负责 UI 设计，Garin-cyber 负责测试，Gracie1103 阅读项目资料并撰写文档。账号、分支、访问方式与审查安排见 [团队分工表](docs/team.md)。

## 第一次加入

```bash
git clone https://github.com/MagicVVu/Team-project.git
cd Team-project
git switch dev
git pull --ff-only origin dev
# 将 feature-agent 替换成自己负责的功能分支
git switch feature-agent
```

上述功能分支已预先创建。新任务也可以从最新 `dev` 创建独立分支：

```bash
git switch dev
git pull --ff-only origin dev
git switch -c feature-your-task
git push -u origin feature-your-task
```

## 每天开发

先提交或暂存尚未完成的本地修改，再同步：

```bash
git switch dev
git pull --ff-only origin dev
git switch feature-agent
git pull --ff-only origin feature-agent
git merge dev
# 开发完成后，确认待提交文件；只添加与本次任务有关的文件
git status
git add <本次修改的文件>
git commit -m "feat: describe the change"
git push
```

在 GitHub 发起 PR 时，明确选择 **base: dev** 和自己的功能分支。阶段发布时选择 **base: main / compare: dev**。如果使用 GitHub CLI，可以执行：

```bash
gh pr create --base dev --head feature-agent
```

`commit` 将修改保存为本地版本，`push` 才会上传到自己的远程分支；上传后仍需 PR 和审查，代码才会进入 `dev`。

PR 合并后，下次工作重复上面的同步步骤。阶段版本发布时，负责人创建 `dev → main` PR，由另一位已加入成员批准、完成检查后合并。

分支清理后，可运行 `git fetch --prune origin`，更新远程分支列表并清除已删除分支的远程跟踪记录。这个命令不会自动删除其他成员已经创建的本地分支。

只阅读项目内容的成员可以直接在 GitHub 查看 `dev` 获取最新已整合内容，查看 `main` 获取已发布的稳定版本。

## 项目目录

```text
frontend/       前端
backend/        后端
agent/          Agent、LLM、RAG
database/       数据库与迁移
docs/           设计、会议与协作文档（UI 资料放在 docs/ui/）
tests/          测试
requirements.txt  Python 依赖清单（技术栈确认后填写）
```

这是协作初始化骨架，暂未包含应用代码或运行命令。技术栈确定后，各模块应补充安装、配置、运行与测试说明。

详细规则见 [CONTRIBUTING.md](CONTRIBUTING.md)。密钥放入本地 `.env`，示例配置可以提交到 `.env.example`。提交前检查是否含密钥、缓存或构建产物。
