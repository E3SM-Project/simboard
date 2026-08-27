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
