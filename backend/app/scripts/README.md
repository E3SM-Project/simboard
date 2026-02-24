# Scripts

This directory contains standalone operational scripts for the backend application.

These scripts are used for administrative and database-related tasks and are not part of the public API surface.

---

## Structure

Scripts are organized by domain:

```
scripts/
├── db/
│   ├── seed.py
│   ├── rollback_seed.py
│   └── simulations.json
└── users/
    ├── create_admin_account.py
    └── provision_service_account.py
```

### Domains

- **db/** — Database seeding and rollback utilities
- **users/** — Administrative and service account management

---

## Execution

All scripts must be executed as modules from the project root to ensure proper import resolution.

Example:

```bash
python -m app.scripts.db.seed
python -m app.scripts.db.rollback_seed
python -m app.scripts.users.create_admin_account
```

Do not execute scripts directly by file path:

```bash
# Avoid
python app/scripts/db/seed.py
```

Module execution ensures:

- Correct package imports
- Proper configuration loading
- Consistent environment behavior

---

## Environment Requirements

Scripts depend on:

- Application configuration (`app.core.config`)
- Database configuration (`app.core.database` or `database_async`)
- SQLAlchemy models and services

Before running any script:

1. Ensure required environment variables are set.
2. Ensure the target database is accessible.
3. Confirm you are using the correct environment (local, staging, etc.).

---

## Design Guidelines

When adding new scripts:

- Keep business logic inside `app.features.*` or service modules.
- Keep scripts thin; they should:
  - Initialize configuration
  - Create database sessions if needed
  - Call service-layer functions

- Avoid duplicating application logic.
- Make scripts idempotent where possible.

---

## Scope

These scripts are intended for:

- Development workflows
- Controlled administrative operations
- Environment setup tasks

If operational complexity increases, these scripts may later be consolidated into a structured CLI entrypoint.
