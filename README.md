# Team-project

CS353 团队项目仓库，所有成员在 `dev` 共享开发，通过 `dev → main` 发布稳定版本。默认分支为 `dev`。

仓库地址：https://github.com/MagicVVu/Team-project

## 分支与合并

| 分支 | 用途 | 更新方式 |
| --- | --- | --- |
| `main` | 稳定、可演示、可提交的阶段版本 | 联调通过后，由 `dev` 发起 PR |
| `dev` | 全员共享开发、联调 | Update / Pull 后直接 Commit、Push，无需开发 PR |

仓库只保留 `dev`、`main`，不使用个人开发分支。拥有写入权限的成员可以直接推送 `dev`，不要求 PR 或状态检查。`main` 仍通过本仓库 `dev → main` PR 更新，分支检查通过、分支已同步目标分支且讨论已解决后即可合并，不强制同伴批准。两个分支均禁止强推和删除，管理员同样受约束。

仓库负责人：[@MagicVVu](https://github.com/MagicVVu)，负责 AI；CaviarHidon 负责前后端，summerdong2006-dot 负责 UI 设计，Garin-cyber 负责测试，Gracie1103 阅读项目资料并撰写文档。成员工作分支统一为 `dev`，受邀成员接受邀请后写入权限生效。详见 [团队分工表](docs/team.md)。

## 第一次加入

```bash
git clone https://github.com/MagicVVu/Team-project.git
cd Team-project
git branch --show-current
```

新克隆默认进入 `dev`。已有本地副本先保存未提交修改，再执行一次切换与远程跟踪记录清理：

```bash
git fetch --prune origin
git switch dev
```

## 每天开发

所有成员都在 `dev` 工作，按自己负责的目录提交。开始 Update / Pull 前，先提交或暂存尚未完成的本地修改；更新方式使用 Merge，保留共享分支历史。

```bash
git switch dev
git pull --no-rebase origin dev
# 开发完成后，确认待提交文件；只添加与本次任务有关的文件
git status
git add <本次修改的文件>
git commit -m "feat: describe the change"
git push origin dev
```

Android Studio 中选择 `dev`，日常直接使用 **Update → 开发 → Commit → Push**，Update 方式选择 Merge。Push 因队友先提交而被拒绝时，再 Update，解决冲突后重新 Push；不要强推。

`commit` 保存本地版本，`push` 上传到共享 `dev`。其他成员在 `dev` 点击 Update 即可拉取。重要或跨模块修改建议提前沟通，但日常提交不需要创建 PR。

## 阶段发布

负责人确认联调与测试通过后，在 GitHub 创建 **base: main / compare: dev** 的 PR。使用 GitHub CLI 时可以执行：

```bash
gh pr create --base main --head dev
```

分支检查通过、已同步目标分支且讨论已解决后即可合并，无需同伴批准。若 PR 提示需更新，将最新 `main` 合并到 `dev` 并推送，再等待检查完成。发布后将 `main` 的合并提交同步回 `dev`，保持后续发布顺畅。

已有副本可运行 `git fetch --prune origin` 清理失效的远程跟踪记录；该命令不会自动删除本地旧分支。清理旧分支前先确认工作已经保存。

查看 `dev` 获取最新开发内容，查看 `main` 获取稳定版本。

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
