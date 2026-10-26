# Simulator + PostgreSQL demo runbook

## Team handoff before the demo

1. Confirm with the group that the saver reads `DATABASE_URL=postgresql://USERNAME:PASSWORD@localhost:5432/group7_desksystem`, and record any dependency/install command and the exact process that calls the saver. Each teammate supplies their own credentials locally.
2. After the schema task merges `database/001_initial_schema.sql`, identify the table that stores desk snapshots plus its desk ID column. Apply it using [the database guide](../database/SETUP.md).
3. Have one teammate who did not write the guide create the database and tables on their computer. Record any unclear step and fix the guide.
4. Choose one laptop for the live demo. Check PostgreSQL, pgAdmin, the simulator, Python, the schema, the API key, and the persistence module in that checkout. Keep credentials out of slides and screen sharing; simulator access logs also include the API key in request paths.

## Live sequence

1. In pgAdmin, show `SELECT current_database(), current_user;` on `group7_desksystem`, then show the expected tables in **Schemas → public → Tables**.
2. Start the simulator in its directory with stable demo settings:

   ```powershell
   cd wifi2ble-box-simulator
   python simulator/main.py --port 8000 --desk-poweroff-chance 0 --desk-collision-chance 0 --no-user-simulation
   ```

3. Show the simulator's desk list and one detail response, or run the console application to show the fetched desk data. If using a browser, hide the address bar because the API key is part of the URL.
4. In another terminal, set `DESK_API_KEY` and `DATABASE_URL` as in [the database guide](../database/SETUP.md). Run the integrated application or saver using the documented command. Note the desk ID it handles.
5. In the Query Tool, query the desk table by that ID using the actual table and column names from the merged schema. Show that the saved row matches the simulator desk's ID and at least one value such as height. If the saver updates existing rows, run it again after changing a desk value and show the updated row rather than an accidental duplicate.

The final two database steps can only be rehearsed after both the schema and saver are merged. Before then, run the simulator and database checks separately. A successful API response alone does not demonstrate persistence.
