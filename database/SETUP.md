# Local PostgreSQL setup

Each teammate creates their own local database. The shared convention proposed for the Python saver is:

- Database: `group7_desksystem`
- Host: `localhost`
- Port: `5432`
- Configuration variable: `DATABASE_URL`
- URL: `postgresql://USERNAME:PASSWORD@localhost:5432/group7_desksystem`

Confirm this exact convention with the persistence task before merging code that reads the URL. Use your own PostgreSQL username and password. If they contain URL punctuation such as `@`, `:`, `/`, or `%`, [percent-encode](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING-URIS) those characters in the URL. Never commit a real password. The root `.gitignore` ignores `.env` files; [`.env.example`](../.env.example) contains placeholders only.

## Team handoff

Share this guide and [`.env.example`](../.env.example) with the team now. Nobody needs to connect to another teammate's computer: each person creates `group7_desksystem` on their own PostgreSQL server.

- **Schema task:** put the versioned PostgreSQL creation script at `database/001_initial_schema.sql`. Share the resulting table and column names with the persistence task, especially how desk identity and observations are stored.
- **Persistence task:** confirm `DATABASE_URL` and its URL format, read it from the environment in the saver process, and document the Python dependency and command needed to call `save_desk(desk_record)`. Do not commit credentials.
- **Application integration owner:** once the saver exists, document the command that fetches simulator desks and calls it. Until then, the existing console application only prints API data.
- **Your setup/demo task:** confirm another teammate can follow the database steps, then rehearse the read → save → database query flow after the schema, saver, and application command are merged.

## 1. Create and check the database

1. Install PostgreSQL and pgAdmin if needed, then start your local PostgreSQL server. In pgAdmin, connect to that server with your own PostgreSQL account. Check that it listens on `localhost:5432`, or use the actual local port consistently if your installation differs.
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
$env:DATABASE_URL = 'postgresql://USERNAME:PASSWORD@localhost:5432/group7_desksystem'
```

If `psql` is on your PATH, check that this **exact URL** connects (pgAdmin's separate saved connection does not test `DATABASE_URL`):

```powershell
psql --dbname=$env:DATABASE_URL -c 'SELECT current_database(), current_user;'
```

On Windows, `psql.exe` is usually under `C:\Program Files\PostgreSQL\<version>\bin` if the command is not on PATH. You can also use PostgreSQL's SQL Shell. A successful result should name `group7_desksystem` and your local PostgreSQL role.

For bash/zsh:

```bash
export DATABASE_URL='postgresql://USERNAME:PASSWORD@localhost:5432/group7_desksystem'
```

You can keep a private root `.env` based on [`.env.example`](../.env.example), but **the current Python application does not load `.env` or read `DATABASE_URL`**. Setting the variable now establishes the agreed configuration format; database writes require the persistence integration. If that code adds `.env` loading, update this section with its exact command. Avoid pasting a real URL into screenshots, issues, or chat.

## 3. Apply the schema when available

The schema task will add `database/001_initial_schema.sql`; it is not in this repository yet. After it is merged:

1. Open **group7_desksystem → Query Tool** and confirm the connection selector still names `group7_desksystem`.
2. Use the Query Tool's **Open File** button to load `database/001_initial_schema.sql` from this checkout. Review the loaded SQL, then use **Execute script** (F5) once on this new database. Check the **Messages** tab for errors. If there is an error, stop and resolve it with the schema task before trying the script again; parts of a script may already have run.
3. Refresh **group7_desksystem → Schemas → public → Tables**, or run:

   ```sql
   SELECT table_name
   FROM information_schema.tables
   WHERE table_schema = 'public'
     AND table_type = 'BASE TABLE'
   ORDER BY table_name;
   ```

   Compare the returned names with the `CREATE TABLE` statements in the committed schema file. Do not expect tables merely from creating the database.

## 4. Run the current simulator and application

The commands below use **PowerShell**. In VS Code, choose **PowerShell** from the terminal profile menu (the arrow beside the `+` button). If your existing terminal tab says `cmd`, type `powershell` and press Enter before running commands that begin with `$`. A PowerShell prompt starts with `PS`; Command Prompt does not understand `$env:...` or `Get-Content`.

From the repository root, initialize the simulator submodule once if it is missing:

```powershell
git submodule update --init --recursive
```

In terminal 1, start the simulator from its own directory, because it uses paths relative to that directory:

```powershell
cd wifi2ble-box-simulator
python simulator/main.py --port 8000
```

In a second terminal at the repository root, load the first local development API key from `wifi2ble-box-simulator/config/api_keys.json`, then run the current console application:

```powershell
$keys = Get-Content .\wifi2ble-box-simulator\config\api_keys.json | ConvertFrom-Json
$env:DESK_API_KEY = $keys[0]
python .\DeskSystemPROJECT\DeskSystemPROJECT.py
```

To inspect the raw simulator data in the same second terminal:

```powershell
$desksUrl = "http://localhost:8000/api/v2/$($env:DESK_API_KEY)/desks"
$deskIds = Invoke-RestMethod -Uri $desksUrl
$deskIds
Invoke-RestMethod -Uri "$desksUrl/$($deskIds[0])" | ConvertTo-Json -Depth 10
```

This shows the desk IDs followed by one desk's `config`, `state`, `usage`, and `lastErrors`. The simulator prints request URLs containing the development API key in its access logs, so hide those logs during screen sharing. Stop the simulator with Ctrl+C in terminal 1 when finished.

Later, after the saver is integrated, set the database URL in the **same terminal as the saver** before running its command:

```powershell
$env:DATABASE_URL = 'postgresql://USERNAME:PASSWORD@localhost:5432/group7_desksystem'
python DeskSystemPROJECT/DeskSystemPROJECT.py
```

Replace the last command if the persistence task supplies a different saver entry point. The application currently fetches and prints desk data from the simulator. It does **not** save rows to PostgreSQL yet. Successful console output therefore proves the simulator and API client work, while the Query Tool and table check prove the separate database setup. Follow the [demo runbook](../docs/simulator-database-demo.md) for the combined check once the saver is merged.

## Troubleshooting

- **Server missing or connection refused:** start PostgreSQL and check its host and port in pgAdmin's server connection properties.
- **Authentication failed:** use the PostgreSQL role and password for your own server; the pgAdmin master password and simulator API key are different credentials.
- **Wrong database in Query Tool:** close that Query Tool tab and open one by right-clicking `group7_desksystem` itself. Check `SELECT current_database(), current_user;` again.
- **No tables:** confirm `001_initial_schema.sql` has been merged and executed in `group7_desksystem`, then refresh **Tables**. If the script reported an error, resolve it with the schema task before rerunning.
- **Application prints desks but tables stay empty:** this is expected until the database saving code is integrated. After integration, check that `DATABASE_URL` is set in the same terminal as the saver process.
