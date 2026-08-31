---
name: draft-upstream-pr
description: Commit a focused SimBoard change, push it to the contributor fork, and open a terse draft pull request against the upstream repository using the repository template.
---

# Draft Upstream PR

## Overview

Prepare a focused, reviewable draft PR without bypassing repository checks or altering unrelated work. The upstream repository is the PR base; push the feature branch to the contributor fork unless the requested remote strategy differs.

## Use When

- A user asks to commit, push, and open a draft PR against SimBoard upstream.
- A completed change needs a PR body that follows `.github/pull_request_template.md`.

## Workflow

1. Inspect `git status`, `git diff --check`, the full diff, recent commits, branch tracking, and remotes.
2. Read `.github/pull_request_template.md` and confirm the issue number, base branch, and upstream repository.
3. Run required checks from the repository root. Do not bypass failing hooks; report environmental blockers and resolve them before committing.
4. Stage only the intended files and create a concise commit message consistent with recent history.
5. Push the branch to the contributor fork, then create a draft PR against upstream with `gh`.
6. Use the PR template. Keep the Description to a short introduction followed by logically grouped bullets. Mark only checklist items that were verified, state skipped checks and reasons accurately, and include deployment notes when needed.
7. Return the commit hash, branch, PR URL, verification results, and any remaining limitations.

## Guardrails

- Never use `--no-verify`, force-push, amend, or commit unrelated changes unless explicitly requested.
- Do not open a PR until the branch is pushed and its diff against the target base is reviewed.
- Do not claim unrun checks passed.
- Preserve the repository template headings and required issue-closing reference.
