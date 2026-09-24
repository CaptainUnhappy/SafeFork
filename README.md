# SafeFork

SafeFork 是 GitHub Fork 的非破坏性同步规范：同步上游分支和标签，但不创建 merge commit，不强制移动引用，也不删除 Fork 独有内容。

## 默认行为

- 未指定目标名称时，Fork 命名为 `<上游仓库名>-SafeFork`；已有该后缀时不重复追加。
- 上游新分支：在 Fork 创建同名分支。
- 上游已有分支：只有在 Fork 可 fast-forward 时才更新。
- 上游新标签：复制原始 tag ref，包括 annotated tag。
- 同名异 SHA 标签、分叉分支、上游改写历史：停止并报告。
- Fork 独有分支和标签：保留。
- GitHub Releases、Issues、Actions 历史、仓库设置和 LFS 对象：不属于 Git refs，不在同步范围内。

这不是 1:1 镜像。真正镜像必须允许删除或强推，与“保留 Fork 数据”的安全目标冲突。

显式指定的仓库名称和所有者优先。否则默认使用当前登录的 GitHub 账号；若默认名称被无关仓库占用，或同一上游已有不同名称的 Fork，SafeFork 会停止并请求选择，不自动加数字或重命名。

## 使用

将 [工作流模板](skills/safefork/assets/safe-fork-sync.yml) 放到 Fork 的独立默认分支 `sync-control`，再设置：

- 仓库变量 `SAFEFORK_UPSTREAM=owner/repo`
- 仓库变量 `SAFEFORK_PRIMARY_BRANCH=main`（按上游默认分支调整）
- Actions Secret `SAFEFORK_DEPLOY_KEY`：仅可写入目标 Fork 的 deploy key 私钥

首次运行请选择 `dry_run`；确认计划后执行正式同步并核对 refs。绿色零写入记录不代表真实写入已通过验收。

模板使用完整提交历史进行普通 push，计划每小时检查一次；GitHub 定时调度可能延迟或丢弃，不提供准时保证。完整规则、验收和回滚测试见 [规范](skills/safefork/references/spec.md)。

`sync-control` 不会自动继承本仓库后续修复。排障或维护既有 Fork 时，应核对已部署工作流的 `SAFEFORK_TEMPLATE_VERSION` 和模板内容；发现漂移后先升级工作流并执行 `dry_run`，有真实待同步引用时再验证写入路径。

在 Codex 中安装本仓库的 `skills/safefork` 后，可直接说：`使用 $safefork 安全同步 owner/repo 的 Fork`。

## 许可证

Copyright (c) 2026 CaptainUnhappy

本仓库原创代码、工作流模板及配套规范文档采用 [Mozilla Public License 2.0（MPL-2.0）](LICENSE)。

MPL 允许商用和二次开发。对外分发受 MPL 覆盖的文件及其修改时，须遵守 MPL 的源码提供和许可要求，并保留版权与许可声明；具体义务以许可证全文为准。

本许可证不改变被同步上游项目或第三方依赖的许可证。此前以 MIT 发布的历史版本仍可按对应版本的许可证使用。
