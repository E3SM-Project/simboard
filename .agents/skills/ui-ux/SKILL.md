---
name: ui-ux
description: Evaluate SimBoard frontend usability, information hierarchy, and interaction design, and recommend design changes grounded in the existing design system before implementation.
---

# UI/UX

## Overview

Evaluate SimBoard interfaces and propose design improvements. This skill decides what to build; `frontend-engineer` implements it. Treat `docs/design-system.md` as the baseline for conventions.

## Use When

- A UI change needs a design decision: layout, navigation, filtering, selection, comparison, or metadata presentation
- Reviewing a screen or flow for confusing, redundant, or inefficient interactions
- Choosing between interaction patterns, or proposing a pattern the design system does not cover

Skip this skill for straightforward implementation that follows existing conventions.

## Workflow

1. Read `docs/design-system.md`, then inspect the affected routes, components, and nearby screens in `frontend/src`.
2. Identify the user task and evaluate hierarchy, workflow efficiency, feedback states, responsiveness, and accessibility.
3. Prefer existing conventions and canonical implementations. When proposing something new, explain why existing patterns are insufficient; cite external design systems only as supporting evidence.
4. Present recommendations with the problem, proposal, tradeoffs, affected components, and priority. Separate consistency fixes from changes that need a product or architecture decision.
5. Wait for approval before implementation. When a decision changes a convention, update `docs/design-system.md` with the implementation.

## Guardrails

- Do not implement changes as part of an evaluation.
- Do not present proposals as established conventions.
- Do not introduce new UI libraries, visual styles, or dependencies to match external systems.
- Preserve SimBoard's existing visual identity unless a change has clear usability or accessibility justification.
