# Deployment Documentation

Recommended reading order:

1. [Deployment and Release Guide](deployment-and-release.md)
2. [NERSC Spin Runbook](nersc-spin-runbook.md)
3. [Set Up an Ingestion Workflow](setup-ingestion-workflow.md)
4. [HPC API Token Authentication](hpc-api-token-authentication.md)
5. [Read-Only Database Access](read-only-database-access.md)

| Document                                                        | Purpose                                                                                                     |
| --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| [Deployment and Release Guide](deployment-and-release.md)       | CI/CD, image tagging, release rollout, migrations, rollback, and deployment troubleshooting.                |
| [NERSC Spin Runbook](nersc-spin-runbook.md)                     | NERSC Spin and Rancher operational setup, workload configuration, secrets, ingress, and service management. |
| [Set Up an Ingestion Workflow](setup-ingestion-workflow.md)     | Step-by-step setup for performance, v3, cron, and diagnostics workflows.                                    |
| [HPC API Token Authentication](hpc-api-token-authentication.md) | Token-based authentication for automated HPC ingestion jobs.                                                |
| [Read-Only Database Access](read-only-database-access.md)       | SSH-tunneled PostgreSQL access for the `simboard_readonly` account.                                       |
