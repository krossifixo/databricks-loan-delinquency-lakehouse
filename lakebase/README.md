# Lakebase operational serving (final architecture)

Instance `loan-delinquency-db`. Three tables:

| Table | Role | Maintained by |
|---|---|---|
| `serving.loan_risk_scored_synced` | At-risk queue (scored loans) | Native UC **synced table** (SNAPSHOT from the Delta source) — `synced_table_spec.json` |
| `public.at_risk_summary` | GenAI briefing (1 row) | `sync_to_lakebase.py` (pulled from UC each ML run) |
| `public.collection_cases` | Operational case write-back | Created empty; the Databricks App INSERTs here |

The Databricks App authenticates as its **service principal** (Postgres role created via
`databricks postgres create-role`), reads the synced queue + briefing, and writes cases —
all directly against Lakebase. Least-privilege grants: SELECT on the queue + briefing,
INSERT/SELECT on collection_cases.

Recreate the synced table: `databricks database create-synced-database-table --json @synced_table_spec.json -p fevm-serverless-stable-fslt65`
Seed the other two tables: `python3 sync_to_lakebase.py`

Evidence: `../evidence/05_lakebase_serving.txt`.

## Querying the Lakebase tables from Databricks (UC)
The synced table auto-registers in UC. Tables created directly in Postgres must be registered once (no data copy — UC reads live from Lakebase):
```
databricks schemas create public loan_delinquency_pg -p fevm-serverless-stable-fslt65
databricks database create-database-table loan_delinquency_pg.public.collection_cases \
  --database-instance-name loan-delinquency-db --logical-database-name databricks_postgres -p fevm-serverless-stable-fslt65
databricks database create-database-table loan_delinquency_pg.public.at_risk_summary \
  --database-instance-name loan-delinquency-db --logical-database-name databricks_postgres -p fevm-serverless-stable-fslt65
```
Then query anywhere in Databricks, e.g. `SELECT * FROM loan_delinquency_pg.public.collection_cases ORDER BY created_at DESC;`
