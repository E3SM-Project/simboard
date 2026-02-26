# SimBoard — Claude Instructions

> **Canonical source:** [`AGENTS.md`](../AGENTS.md) is the single source of truth for AI development rules.
> Read and apply `AGENTS.md` in full before generating any code or responses.

## Claude Behavior

- Apply all rules from `AGENTS.md` to every response and code generation task.
- Read relevant source files before making changes — do not assume file contents, module structure, or configuration.
- Do not generate code that violates the architectural constraints, coding standards, or dependency policies defined in `AGENTS.md`.
- Do not hallucinate files, modules, or configuration that are not present in the repository.
- Do not hardcode dependency versions, CI matrix values, or other volatile configuration — reference the authoritative source files listed in `AGENTS.md`.
- When running commands, follow the development workflow and testing conventions defined in `AGENTS.md`.
- When uncertain about project conventions, consult `AGENTS.md` and the key reference files it lists before responding.
