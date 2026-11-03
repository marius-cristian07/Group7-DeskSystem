# Local PostgreSQL setup

Each teammate creates their own local database. The Python application uses:

- Database: `group7_desksystem`
- Host: `127.0.0.1`
- Port: `5432`
- Configuration variable: `DATABASE_URL`
- URL: `postgresql://USERNAME:PASSWORD@127.0.0.1:5432/group7_desksystem`

Use your own PostgreSQL username and password, not the pgAdmin master password. If they contain URL punctuation such as `@`, `:`, `/`, or `%`, [percent-encode](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING-URIS) those characters in the URL. Never commit a real password. The root `.gitignore` ignores `.env` files; [`.env.example`](../.env.example) contains placeholders only.

## 1. Create and check the database

1. Install PostgreSQL and pgAdmin if needed, then start your local PostgreSQL server. In pgAdmin, connect to that server with your own PostgreSQL account. Check that it listens on `127.0.0.1:5432`, or use the actual local port consistently if your installation differs.
2. In Object Explorer, right-click **Databases → Create → Database...**. Name it `group7_desksystem`, leave the other settings at their defaults, and save. If it already exists, use that database instead of creating another.
3. Right-click **group7_desksystem → Query Tool**. Check the database name in the Query Tool tab or connection selector before executing any SQL.
4. Run:

   ```sql
   SELECT current_database(), current_user;
   ```

   Expect `group7_desksystem` and the PostgreSQL user you connected as. An empty **Schemas → public → Tables** folder is normal before the schema is applied.

pgAdmin documents [database creation](https://www.pgadmin.org/docs/pgadmin4/latest/managing_cluster_objects.html) and [Query Tool execution](https://www.pgadmin.org/docs/pgadmin4/latest/query_tool.html).

## 2. Configure the connection

Set `DATABASE_URL` for the process that will save desk data. The example below is for PowerShell; replace both placeholders with your own credentials. This value lasts for the current terminal session:

```powershell
$env:DATABASE_URL = 'postgresql://USERNAME:PASSWORD@127.0.0.1:5432/group7_desksystem'
```

For bash/zsh:

```bash
export DATABASE_URL='postgresql://USERNAME:PASSWORD@127.0.0.1:5432/group7_desksystem'
```

The application reads `DATABASE_URL` from the environment for `sync` and `move`; `show` only needs the simulator API key. It does not load `.env` files automatically. Avoid pasting a real URL into screenshots, issues, or chat.

## 3. Apply the schema

The schema is in [`database/001_initial_schema.sql`](001_initial_schema.sql). Apply it to a new `group7_desksystem` database once. If its tables already exist, skip this step.

1. Open **group7_desksystem → Query Tool** and confirm the connection selector still names `group7_desksystem`.
2. Use the Query Tool's **Open File** button to load `database/001_initial_schema.sql` from this checkout. Review the loaded SQL, then use **Execute script** (F5) once on this new database. Check the **Messages** tab for errors. If there is an error, inspect which tables were created before trying the script again; parts of a script may already have run.
3. Refresh **group7_desksystem → Schemas → public → Tables**, or run:

   ```sql
   SELECT table_name
   FROM information_schema.tables
   WHERE table_schema = 'public'
     AND table_type = 'BASE TABLE'
   ORDER BY table_name;
   ```

   Expect `desk`, `desk_readings`, `desk_errors`, and `desk_commands`. Creating the database alone does not create these tables.

## 4. Run the current simulator and application

Complete [project setup](../SETUP.md) once, then start the simulator, backend, and React from the repository root:

```powershell
python run.py
```

PostgreSQL remains your existing local service. Open a second terminal at the repository root for these optional database exercises and set its credentials:

```powershell
$env:DESK_API_KEY = (Get-Content wifi2ble-box-simulator/config/api_keys.json -Raw | ConvertFrom-Json)[0]
$env:DATABASE_URL = 'postgresql://USERNAME:PASSWORD@127.0.0.1:5432/group7_desksystem'
```

Replace `USERNAME` and `PASSWORD` with your local PostgreSQL credentials. Run the commands you want to try:

```powershell
.\.venv\Scripts\python.exe DeskSystemPROJECT/DeskSystemPROJECT.py show
.\.venv\Scripts\python.exe DeskSystemPROJECT/DeskSystemPROJECT.py sync
.\.venv\Scripts\python.exe DeskSystemPROJECT/DeskSystemPROJECT.py move DESK_ID 1000
```

On macOS/Linux, use `.venv/bin/python`. For simulator-only startup, see the manual commands in [SETUP.md](../SETUP.md).

`show` prints current simulator data without saving it. `sync` saves a new reading for every available desk. For `move`, replace `DESK_ID` with an ID printed by `show` or `sync`; it requests a height from the simulator, saves the command result, and saves a follow-up reading if accepted. See the [Sprint 2 workflow guide](../docs/sprint2-workflow.md) for more detail.

To verify the saved data in pgAdmin's `group7_desksystem` Query Tool, run these queries one at a time:

```sql
SELECT reading_id, desk_id, position_mm, status, recorded_at
FROM desk_readings ORDER BY reading_id DESC LIMIT 10;

SELECT command_id, desk_id, target_position_mm, status, requested_at
FROM desk_commands ORDER BY command_id DESC LIMIT 10;
```

## Troubleshooting

- **Server missing or connection refused:** start PostgreSQL and check its host and port in pgAdmin's server connection properties.
- **Authentication failed:** use the PostgreSQL role and password for your own server; the pgAdmin master password and simulator API key are different credentials.
- **Wrong database in Query Tool:** close that Query Tool tab and open one by right-clicking `group7_desksystem` itself. Check `SELECT current_database(), current_user;` again.
- **No tables:** execute `001_initial_schema.sql` in `group7_desksystem`, then refresh **Tables**. If the script reported an error, inspect the database before rerunning it.
- **`show` prints desks but tables stay empty:** `show` is read-only; run `sync` to save readings. Set `DATABASE_URL` in the same terminal as the application.
