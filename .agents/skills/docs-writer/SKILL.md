---
name: docs-writer
description: Write or improve SimBoard documentation for developers and users, keeping it accurate to the repo's current structure, workflows, and anti-drift documentation rules.
---

# Docs Writer

## Purpose

Write durable human-facing documentation for SimBoard. Cover onboarding, architecture, workflows, features, deployment notes, and developer usage guidance based on what the repository actually does today.

## When To Use

- Updating READMEs after behavior or workflow changes
- Writing feature docs, onboarding steps, architecture notes, or usage documentation
- Clarifying developer setup, validation commands, or deployment/development workflows
- Cleaning up stale docs so they match the codebase

## Inputs Expected

- The audience and documentation goal
- The behavior, workflow, or architecture being documented
- Source files or commands that should be treated as authoritative
- Scope constraints such as README-only, docs-only, or feature-local docs

## Outputs Required

- Updated Markdown in the right repo location
- Accurate commands, paths, and file references
- Clear note of any behavior that could not be verified directly
- Minimal duplication across docs

## Repo-Specific Conventions

- Use the repo's existing documentation locations first: `README.md`, `frontend/README.md`, `backend/README.md`, and `docs/**`.
- Follow the anti-drift policy in `AGENTS.md`: do not hardcode dependency versions, counts, or volatile config when the authoritative source is a manifest, lockfile, workflow file, or source default.
- When setup or development steps are involved, prefer the repo make targets from `Makefile`.
- Document backend tooling as `uv`-based and frontend tooling as `pnpm`-based.
- When environment setup matters, reference `.envs/example/*` as templates and `.envs/local/*` as developer-local values.
- Keep pre-commit guidance rooted at the repository root, matching the current repo instructions.
- If a change affects user-facing flows, keep terminology consistent with SimBoard's domain: simulations, cases, machines, ingestion, compare, upload, and E3SM metadata.

## Constraints / Anti-Patterns

- Do not turn planning notes into durable docs; that belongs to `feature-planner`.
- Do not document unimplemented behavior or aspirational architecture as if it already exists.
- Do not duplicate the same long workflow in multiple files unless one file is serving as navigation.
- Do not invent operational steps that are not backed by the repository.
- Do not hardcode versions or other volatile values when a referenced source is the stable answer.

## Example Task

Update `README.md` and `docs/README.md` after a new local development workflow is added, using existing make targets and environment file locations rather than embedding fragile, version-specific setup details.
