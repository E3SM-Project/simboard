# Contributing to SimBoard

Use this file for contribution workflow. For local setup, architecture, and developer onboarding, see [docs/developer/README.md](docs/developer/README.md).

## Start With an Issue

Start from an issue when the work is not trivial.

- bug reports: `.github/ISSUE_TEMPLATE/bug_report.yml`
- enhancements: `.github/ISSUE_TEMPLATE/enhancement_request.yml`
- planning work: `.github/ISSUE_TEMPLATE/planning_task.yml`
- DevOps work: `.github/ISSUE_TEMPLATE/devops.yml`

If no issue exists, open one first or document the reason the change is intentionally small and self-contained.

## Branches and Commits

- branch from `main`
- use short-lived, descriptive branch names
- keep commits focused and reviewable
- avoid mixing behavior changes, refactors, and unrelated cleanup in one commit

No repository branch naming convention is documented, so prefer clarity over personal shorthand.

## Pull Requests

Use the PR template in `.github/pull_request_template.md`.

Each PR should:

- link the relevant issue when applicable
- explain the change and motivation
- note any required documentation updates
- note any deployment or migration steps if applicable

## Required Checks Before Opening a PR

Run the relevant checks from the repository root:

```bash
make backend-test
make frontend-lint
make pre-commit-run
pnpm --dir frontend run type-check
```

If your change only touches one subsystem, still prefer running the nearest relevant checks rather than skipping validation entirely.

## Review Expectations

- keep diffs small enough to review safely
- add or update tests when behavior changes
- include schema or migration notes when persistence changes
- update documentation when workflows or capabilities change

## Where to Go Next

- developer guide: [docs/developer/README.md](docs/developer/README.md)
- backend details: [backend/README.md](backend/README.md)
- frontend details: [frontend/README.md](frontend/README.md)
- operations and deployment docs: [docs/README.md](docs/README.md)
