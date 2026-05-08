---
name: docs-writer
description: Write or improve SimBoard documentation for developers and users, keeping it accurate to the repo's current structure, workflows, and anti-drift documentation rules.
---

# Docs Writer

## Overview

Write durable SimBoard documentation that matches the repository as it exists now. Prefer code, manifests, the Makefile, and current routes over stale prose.

## Use When

- Updating READMEs or `docs/**` after behavior, workflow, or architecture changes
- Writing onboarding, setup, feature, or developer workflow documentation
- Correcting drift between documentation and the codebase

## Workflow

1. Inspect the relevant code, commands, and existing docs before writing.
2. Treat code, manifests, workflows, and `Makefile` targets as authoritative when prose disagrees.
3. Update the most specific existing doc instead of duplicating content.
4. Keep commands, paths, and terminology aligned with the repo.
5. Note anything that could not be verified directly.

## Repo Rules

- Prefer existing doc locations: `README.md`, `backend/README.md`, `frontend/README.md`, and `docs/**`.
- Follow the anti-drift policy in `AGENTS.md`: do not hardcode volatile versions, counts, or config values.
- Document backend tooling as `uv`-based and frontend tooling as `pnpm`-based.
- Prefer repo make targets for setup, dev, lint, test, and pre-commit flows.
- Reference `.envs/example/*` for templates and `.envs/local/*` for developer-local values.
- Keep terminology consistent with the current product and routes, including cases, runs, compare, upload, docs, and simulation metadata.

## Guardrails

- Do not document unimplemented or aspirational behavior as current behavior.
- Do not copy the same long workflow into multiple files unless one document is acting as navigation.
- Do not invent setup or operational steps that are not backed by the repo.
