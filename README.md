# SafeFork

SafeFork 是 GitHub Fork 的非破坏性同步规范：同步上游分支和标签，但不创建 merge commit，不强制移动引用，也不删除 Fork 独有内容。

## 默认行为

- 上游新分支：在 Fork 创建同名分支。
- 上游已有分支：只有在 Fork 可 fast-forward 时才更新。
- 上游新标签：复制原始 tag ref，包括 annotated tag。
- 同名异 SHA 标签、分叉分支、上游改写历史：停止并报告。
- Fork 独有分支和标签：保留。
- GitHub Releases、Issues、Actions 历史、仓库设置和 LFS 对象：不属于 Git refs，不在同步范围内。

这不是 1:1 镜像。真正镜像必须允许删除或强推，与“保留 Fork 数据”的安全目标冲突。

## 使用

将 [工作流模板](skills/safefork/assets/safe-fork-sync.yml) 放到 Fork 的独立默认分支 `sync-control`，再设置：

- 仓库变量 `SAFEFORK_UPSTREAM=owner/repo`
- 仓库变量 `SAFEFORK_PRIMARY_BRANCH=main`（按上游默认分支调整）
- Actions Secret `SAFEFORK_DEPLOY_KEY`：仅可写入目标 Fork 的 deploy key 私钥

首次运行请选择 `dry_run`。完整规则、验收和回滚测试见 [规范](skills/safefork/references/spec.md)。

在 Codex 中安装本仓库的 `skills/safefork` 后，可直接说：`使用 $safefork 安全同步 owner/repo 的 Fork`。
