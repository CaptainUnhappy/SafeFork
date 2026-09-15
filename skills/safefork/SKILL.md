---
name: safefork
description: Create, audit, repair, or run non-destructive GitHub Fork synchronization for upstream branches and immutable tags. Use when the user asks to SafeFork a repository or safely sync a Fork without merge, force updates, or deletions.
---

# SafeFork

Use SafeFork to preserve upstream Git refs without turning the Fork into a destructive mirror.

Read [references/spec.md](references/spec.md) before creating or changing a remote setup. Use [assets/safe-fork-sync.yml](assets/safe-fork-sync.yml) as the maintained workflow source; customize only repository-specific values and documented thresholds.

## Operating workflow

1. Inspect the target repository, its parent, default branch, all `refs/heads/*`, all `refs/tags/*`, workflow state, and recent runs.
2. Separate observed facts from assumptions. Verify that the named target is a real Fork of the intended upstream.
3. Produce a dry-run plan. Classify every upstream branch as create, equal, fast-forward, or blocked; classify every tag as create, equal, or conflict.
4. For an explicitly requested SafeFork setup or sync, apply only additive or fast-forward changes. A normal SafeFork request authorizes those scoped writes, not force updates, deletions, merges, repository creation beyond the named target, or backup refs.
5. Verify every changed ref by reading it back. Compare the full upstream/Fork ref sets again and report preserved Fork-only refs separately.
6. Treat scheduled-run health and ref equality as different checks. Do not call synchronization complete merely because an Action succeeded.

## Invariants

- Keep an isolated default control branch, normally `sync-control`, because scheduled workflows run only from the default branch.
- Never create merge commits during synchronization.
- Never use force updates or delete refs in scheduled synchronization.
- Never move an existing tag. Same name with a different SHA is a hard conflict.
- Never overwrite a diverged or Fork-ahead branch.
- Lock source and target snapshots before writes; stop if either changes unexpectedly.
- Preserve Fork-only branches and tags.
- `dry_run` must perform zero writes.
- Do not create backup branches unless the user explicitly requests one and sees its exact name.
- Use a write-enabled deploy key restricted to the target Fork for ref pushes. Keep its private key only in the `SAFEFORK_DEPLOY_KEY` Actions Secret; do not substitute a broad user PAT merely for convenience.

GitHub Releases, Issues, Actions history, repository settings, secrets, and LFS objects are outside SafeFork ref synchronization. If the user asks for a perfect mirror, explain that deletion and history rewriting conflict with SafeFork, then require a separate explicit destructive-mirror request.
