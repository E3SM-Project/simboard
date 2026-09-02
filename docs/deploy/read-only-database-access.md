# Read-Only Database Access

Use this guide to connect to the SimBoard development PostgreSQL database with
the `simboard_readonly` account. The account is intended for inspecting data;
it must not be used by the application, migrations, or ingestion jobs.

## Prerequisites

- Authorization to use the `simboard_readonly` account and its password.
- SSH access to Perlmutter with your own NERSC account.
- A PostgreSQL client. Any client that can connect to PostgreSQL over a local
  TCP port will work.

The database endpoint is internal to NERSC Spin. Reach it through Perlmutter;
do not attempt to expose the database service publicly.

## Connection details

| Setting | Value |
| --- | --- |
| Database | `simboard` |
| Database user | `simboard_readonly` |
| Internal database host | `db-loadbalancer.simboard.development.svc.spin.nersc.org` |
| Internal database port | `5432` |
| SSH host | `perlmutter-p1.nersc.gov` |
| SSH port | `22` |

Use the password provided through an approved private channel. Do not store it
in this repository, a shared document, or a connection profile that is not
protected by your operating-system account.

## Option 1: Create an SSH tunnel (works with any client)

On your workstation, leave this command running while you use your database
client. Replace `YOUR_NERSC_USERNAME` with your NERSC login name.

```bash
ssh -N -L 15432:db-loadbalancer.simboard.development.svc.spin.nersc.org:5432 \
  YOUR_NERSC_USERNAME@perlmutter-p1.nersc.gov
```

Then configure the database client to connect to:

| Client setting | Value |
| --- | --- |
| Host | `127.0.0.1` |
| Port | `15432` |
| Database | `simboard` |
| Username | `simboard_readonly` |
| Password | Password supplied for this account |

Keep the SSH session open for the entire database session. To stop access,
close the SSH session.

For example, after opening the tunnel, `psql` can connect with:

```bash
psql -h 127.0.0.1 -p 15432 -U simboard_readonly -d simboard
```

`psql` will prompt for the database password.

## Option 2: Use your client’s SSH tunnel feature

Many database clients can create the same tunnel themselves. Configure the
PostgreSQL connection using the **internal database host** and port from the
table above, then enable the client’s SSH tunnel/proxy option with:

| SSH setting | Value |
| --- | --- |
| SSH host | `perlmutter-p1.nersc.gov` |
| SSH port | `22` |
| SSH username | Your NERSC username |
| Authentication | Your normal approved NERSC SSH method |

Set the database username to `simboard_readonly` and enter the separately
provided database password. The screenshots shared with this guide show these
same two groups of settings in DBeaver, but the values apply to any client with
SSH tunneling support.

## Verify the connection

Run the following query after connecting:

```sql
SELECT current_user, current_database();
```

It should return `simboard_readonly` and `simboard`. Reads, such as `SELECT`
queries, should succeed for granted tables. Commands that change data or
schema, such as `INSERT`, `UPDATE`, `DELETE`, `CREATE`, or `ALTER`, should be
denied.

## Getting started: ingestion and operations queries

The `ingestions` table is the audit record for each upload or HPC-path
ingestion. Join it to `machines` to see where the data came from, and to
`executions` and `cases` to inspect the records it created. The queries below
are read-only and use date filters or `LIMIT` to keep exploratory queries
small.

### Recent ingestion activity

Use this first to see the most recent ingestion attempts and their outcomes.

```sql
SELECT
  i.created_at,
  m.name AS machine,
  i.source_type,
  i.status,
  i.created_count,
  i.duplicate_count,
  i.error_count,
  i.source_reference
FROM ingestions AS i
JOIN machines AS m ON m.id = i.machine_id
ORDER BY i.created_at DESC
LIMIT 25;
```

`success`, `partial`, and `failed` are the ingestion status values. A
non-zero `error_count` or a `partial`/`failed` status is worth investigating.

### Recent incomplete or failed ingestions

This narrows the audit trail to outcomes that may need attention.

```sql
SELECT
  i.created_at,
  m.name AS machine,
  i.status,
  i.error_count,
  i.created_count,
  i.duplicate_count,
  i.source_type,
  i.source_reference
FROM ingestions AS i
JOIN machines AS m ON m.id = i.machine_id
WHERE i.status IN ('partial', 'failed')
   OR i.error_count > 0
ORDER BY i.created_at DESC
LIMIT 50;
```

### Daily ingestion volume by machine

Use this operational summary to look for gaps, spikes, or a rise in errors.

```sql
SELECT
  date_trunc('day', i.created_at) AS day,
  m.name AS machine,
  COUNT(*) AS ingestion_count,
  SUM(i.created_count) AS executions_created,
  SUM(i.duplicate_count) AS duplicates,
  SUM(i.error_count) AS errors
FROM ingestions AS i
JOIN machines AS m ON m.id = i.machine_id
WHERE i.created_at >= CURRENT_TIMESTAMP - INTERVAL '14 days'
GROUP BY day, m.name
ORDER BY day DESC, m.name;
```

Change the interval to suit the investigation. For example, use `7 days` for
a shorter operational view.

### Executions created by recent ingestions

This joins ingestion audit records to their resulting execution and case
records. It is useful when an ingestion count looks unexpected.

```sql
SELECT
  i.created_at AS ingested_at,
  m.name AS machine,
  i.status AS ingestion_status,
  c.name AS case_name,
  e.execution_id,
  e.status AS execution_status,
  e.compset,
  e.grid_name
FROM ingestions AS i
JOIN machines AS m ON m.id = i.machine_id
JOIN executions AS e ON e.ingestion_id = i.id
JOIN cases AS c ON c.id = e.case_id
ORDER BY i.created_at DESC, c.name, e.execution_id
LIMIT 100;
```

To investigate one ingestion, add `WHERE i.id = 'INGESTION_UUID'` before the
`ORDER BY` clause, replacing `INGESTION_UUID` with the identifier shown by
your client.

### Current execution status overview

This gives a compact view of the catalog's execution states by machine.

```sql
SELECT
  m.name AS machine,
  e.status AS execution_status,
  COUNT(*) AS execution_count
FROM executions AS e
JOIN cases AS c ON c.id = e.case_id
JOIN machines AS m ON m.id = c.machine_id
GROUP BY m.name, e.status
ORDER BY m.name, e.status;
```

Execution statuses include `created`, `queued`, `running`, `failed`, and
`completed`; `unknown` is used when no more specific state is available.

## Troubleshooting

- **SSH authentication fails:** confirm that you can SSH to Perlmutter with
  the same NERSC account before configuring the database client.
- **Connection refused on `127.0.0.1:15432`:** confirm the SSH tunnel is still
  running and that no other local program is using port `15432`.
- **Database authentication fails:** verify that the database username is
  exactly `simboard_readonly` and obtain a fresh password from the account
  administrator if necessary.
- **Database host cannot be resolved locally:** this is expected. The internal
  hostname is resolved from Perlmutter through the SSH tunnel, not from your
  workstation.
