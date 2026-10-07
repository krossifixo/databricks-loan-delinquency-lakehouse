# Lakebase operational serving

Two serving paths into the Lakebase instance `loan-delinquency-db`:

1. Direct write (`sync_to_lakebase.py`) -> `loan_risk_scored`, `at_risk_summary`, `collection_cases` in Postgres `public`. Evidence: `../evidence/05_lakebase_serving.txt`.
2. Native UC synced table (`synced_table_spec.json`) -> `loan_delinquency_pg.serving.loan_risk_scored_synced`, SNAPSHOT-synced from Delta via the Lakebase database catalog. Evidence: `../evidence/05b_lakebase_synced_table.txt`.

Recreate the synced table:
`databricks database create-synced-database-table --json @synced_table_spec.json -p fevm-serverless-stable-fslt65`
