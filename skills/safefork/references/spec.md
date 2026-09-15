# SafeFork v1 规范

## 目标与边界

SafeFork 的目标是让 Fork 持续获得上游 Git 分支与标签，同时保证 Fork 已有历史和独有引用不会被定时任务破坏。

同步对象只有：

- `refs/heads/*`
- `refs/tags/*`

不包含 GitHub Releases、Issues、Pull Requests、Actions 历史、仓库设置、Secrets、Wiki、Packages 或 Git LFS 对象。

## 控制面

`sync-control` 应设为 Fork 默认分支，只保存工作流与说明。代码分支保持上游提交图不变。这样既满足 GitHub `schedule` 只从默认分支运行的限制，也不会为了保存工作流而污染上游代码历史。

若上游也出现名为 `sync-control` 的分支，自动同步必须停止，不能覆盖控制面。

## 引用决策

| 来源与目标状态 | 决策 |
| --- | --- |
| 上游分支不存在于 Fork | 创建同名分支 |
| 两端分支 SHA 相同 | 不写入 |
| Fork 分支是上游分支祖先 | `force=false` fast-forward |
| Fork 分支领先、分叉或无共同历史 | 停止，不写入 |
| 上游标签不存在于 Fork | 按原始 tag ref SHA 创建 |
| 同名标签 SHA 相同 | 不写入 |
| 同名标签 SHA 不同 | 停止，不移动标签 |
| Fork 独有分支或标签 | 保留 |
| 上游删除分支或标签 | 保留 Fork 现有引用并报告 |

任一冲突应在第一次写入前终止整次计划。API 在写入中途失败时可能留下已完成的安全写入，因此摘要必须逐项记录实际写入。

## 安全不变量

1. Fork 的 `parent.full_name` 必须等于配置的 `SAFEFORK_UPSTREAM`。
2. 规划时锁定上游和 Fork 的引用 SHA；写入前重新检查来源快照和目标分支。
3. 分支更新只能使用 fast-forward；标签只能首次创建。
4. 定时任务禁止 merge、force update 和 DELETE。
5. 写入后允许短暂最终一致性重试，再核对实际 SHA。
6. `dry_run` 必须零写入。
7. 任何读取不完整、权限失败、来源变化或未知关系都 fail closed。

主分支文件数量阈值只是异常删除闸门，不证明代码安全或语义正确。

## 验收

至少验证以下场景：

- 引用完全一致：成功，零写入。
- 新上游分支：只创建该分支。
- 已有分支可快进：只更新该分支，`force=false`。
- Fork 独有分支：保留。
- 分支分叉或上游改写：失败，零写入。
- 新标签：只创建缺失标签，annotated tag 的 ref SHA 保持一致。
- 标签冲突：失败，零写入。
- 来源或目标在规划期间变化：失败。
- 写入后首次读取仍是旧值：重试后验证成功。
- dry-run：所有检查执行，零 POST/PATCH/DELETE。
- 所有场景：不得发出 DELETE 或 `force=true`。

远端验收不能只看 Action 绿色状态。应分别列出上游与 Fork 的 heads/tags，确认所有上游引用同名同 SHA，并单独列出保留的 Fork-only 引用。

## 回滚同步测试

回滚测试是一次显式的历史改写，不属于 SafeFork 定时行为。

1. 设置 `SAFEFORK_PAUSED=true` 并确认没有运行中的同步任务。
2. 记录远端代码分支当前 SHA 与其第一父提交 SHA。
3. 使用精确的 `--force-with-lease=refs/heads/<branch>:<recorded-sha>` 回退；不要使用裸 `--force`。
4. 不自动创建备份分支。只有用户明确要求时才创建，并提前展示名称。
5. 保持暂停，先运行 `dry_run`；确认计划只有预期 fast-forward。
6. 若要测试定时触发，解除暂停并等待 `schedule`；否则手动运行。
7. 验证目标分支回到上游锁定 SHA，再恢复暂停变量。

测试期间记录的原始 SHA 可用于短期恢复；如果目标分支已被其他操作改变，应停止，不能取消 lease 保护。

## 令牌

普通 ref 写入需要 `contents: write`。当上游提交新增或修改 `.github/workflows/*` 时，`GITHUB_TOKEN` 可能被 GitHub 拒绝；使用只授权目标仓库 Contents 与 Workflows 写权限的 fine-grained PAT，保存为 `SAFEFORK_PAT`。不得把令牌写入仓库。
