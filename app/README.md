# Collections Cockpit — Databricks App (Streamlit)

Business-facing surface for the journey. Reads the ML-scored at-risk queue and the
GenAI briefing from the governed serving tables (via the SQL warehouse using the app's
service principal), links to the Genie space for NL questions, and writes collection-case
actions back to `app_collection_cases`.

- URL: https://loan-collections-cockpit-7474658995900491.aws.databricksapps.com
- Deploy: `databricks sync app <workspace_path>` then `databricks apps deploy loan-collections-cockpit --source-code-path <workspace_path>`
- The app SP needs: USE CATALOG/SCHEMA + SELECT on the schema, MODIFY on app_collection_cases, CAN_USE on the warehouse.

See `../evidence/07_databricks_app.txt`.
