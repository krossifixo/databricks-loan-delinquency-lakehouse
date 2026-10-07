# Collections Cockpit — Databricks App (Streamlit, Lakebase-native)

Business-facing surface. Authenticates as its own **service principal**, mints a short-lived
Lakebase credential at runtime, and talks directly to the Lakebase database:
- reads the at-risk queue from `serving.loan_risk_scored_synced` (UC synced table),
- reads the GenAI briefing from `public.at_risk_summary`,
- writes collection-case actions to `public.collection_cases`.

Links to the Genie space for natural-language questions.

- URL: https://loan-collections-cockpit-7474658995900491.aws.databricksapps.com
- SP: a2c59ebf-343f-424b-9604-0f15a8e1ec33 (Lakebase Postgres role + least-privilege table grants).
- Deploy: `databricks sync app <ws_path>` then `databricks apps deploy loan-collections-cockpit --source-code-path <ws_path>`.

See `../evidence/07_databricks_app.txt`.
