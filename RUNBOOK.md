# Runbook — Early Delinquency Intervention Lakehouse

**What this is:** an end-to-end Databricks data journey that predicts which currently-current auto loans will roll 30+ days past due next cycle, and surfaces a ranked collections queue to a business app. Everything below is synthetic data; no real customer data.

**Repo:** https://github.com/krossifixo/databricks-loan-delinquency-lakehouse
**App:** https://loan-collections-cockpit-7474658995900491.aws.databricksapps.com

---

## 1. The problem and the outcome
A consumer auto-lender loses money when loans that are current today roll into 30+ DPD and then charge-off, while collections reacts only after a loan is already delinquent. This build predicts the roll **one cycle ahead** so collections can intervene early. Outcome: lower early-stage roll rate, fewer roll-to-charge-offs, lower net charge-offs, and a more efficient collections team.

## 2. Architecture at a glance (data flow)
```
Raw CSV (synthetic)                      <- data/generate_data.py
   -> UC Volume landing zone
   -> LAKEFLOW pipeline (bronze -> silver -> delinquency_training)   [Unity Catalog governed]
   -> ML model (MLflow, UC-registered) scores current loans -> loan_risk_scored
   -> GenAI (ai_query) writes a plain-language briefing -> at_risk_summary
   -> LAKEBASE serving (direct write + native UC synced table)
   -> GENIE space (natural-language questions over the governed tables)
   -> DATABRICKS APP (collections cockpit): queue + briefing + case actions
```

## 3. Environment / resource inventory
- Workspace: `fevm-serverless-stable-fslt65` (profile `fevm-serverless-stable-fslt65`)
- Unity Catalog: catalog `serverless_stable_fslt65_catalog`, schema `loan_delinquency`
- SQL warehouse (serverless): `dd8909b1ec28c7ce`
- Lakeflow pipeline: `loan_delinquency_ingest` (id `5720209f-9188-44fc-9ac4-7e4b0fd95c53`)
- ML model (UC): `serverless_stable_fslt65_catalog.loan_delinquency.delinquency_risk_model` (v1)
- Lakebase instance: `loan-delinquency-db` (host `ep-rapid-hill-d2oltmgm.database.us-east-1.cloud.databricks.com`)
- Lakebase DB catalog: `loan_delinquency_pg`; synced table `loan_delinquency_pg.serving.loan_risk_scored_synced`
- Genie space: `Loan Delinquency Risk — Collections Genie` (`01f1c272286c1c379ae5aa850af96c97`)
- App: `loan-collections-cockpit` (SP `a2c59ebf-343f-424b-9604-0f15a8e1ec33`)

## 4. Stage-by-stage: what was built, how it works, how to run it

### Stage 1 — Lakeflow ingest  (`pipelines/loan_delinquency_pipeline.sql`)
- `data/generate_data.py` creates `loans.csv` (5,000) and `payments.csv` (60,000) with real delinquency signal, uploaded to the UC Volume `.../raw_landing/`.
- The pipeline reads them with `read_files` into `loans_bronze` / `payments_bronze` (streaming tables), cleans/types to `loans_silver` / `payments_silver` (materialized views with EXPECT data-quality constraints), and builds `delinquency_training`: one row per loan-month that is **current** this month, labeled `target_delinquent_next` = did it roll 30+ DPD next month (51,573 rows).
- Run: `databricks pipelines start-update 5720209f-9188-44fc-9ac4-7e4b0fd95c53 -p fevm-serverless-stable-fslt65`.

### Stage 2 — Unity Catalog govern  (`sql/03_governance.sql`)
- Schema + table comments, a governed tag (`domain=finance` — the metastore enforces allowed tag-policy values), table tags (`layer=gold`), and a `SELECT` grant to `account users`. Data-quality expectations in the pipeline are the governance-via-DQ layer.

### Stage 3 — ML + GenAI  (`ml/train_model.py`, run as a serverless job)
- Trains a scikit-learn GradientBoosting classifier (one-hot categoricals + numeric features) on `delinquency_training`, logs to MLflow, and registers it in Unity Catalog.
- Metrics: ROC AUC 0.74, PR-AUC 0.09 (base rate 3.2%), **precision@top5% 11.8%, lift 3.7x**.
- Batch-scores the latest snapshot per loan into `loan_risk_scored` (risk_score + tier High/Medium/Low).
- GenAI: `ai_query('databricks-meta-llama-3-3-70b-instruct', ...)` writes a manager briefing to `at_risk_summary`.
- Run: `databricks jobs submit --json @job_submit.json` (notebook on serverless; the notebook `%pip install`s mlflow/scikit-learn).

### Stage 4 — Lakebase serving  (`lakebase/`)
- Two paths. (a) Direct write (`sync_to_lakebase.py`): pulls scored loans + summary from UC and writes Postgres tables `loan_risk_scored`, `at_risk_summary`, `collection_cases`. (b) Native UC synced table (`synced_table_spec.json`): `loan_delinquency_pg.serving.loan_risk_scored_synced`, SNAPSHOT-synced from the Delta source.
- Credential: `databricks database generate-database-credential --json '{"instance_names":["loan-delinquency-db"]}'` -> use the token as the Postgres password (user = your Databricks email, sslmode=require).

### Stage 5 — Genie  (`genie/space_config.json`)
- Space over `delinquency_training`, `loan_risk_scored`, `loans_silver`. Business users ask e.g. "which FICO band is rolling fastest?" and Genie generates governed SQL.
- Ask from CLI: `databricks genie ask "<question>" --warehouse-id dd8909b1ec28c7ce --include-sql`.

### Stage 6 — Databricks App  (`app/app.py`, Streamlit)
- Reads the governed/served tables via the warehouse using the app's service principal.
- Screens / functionality:
  - **KPIs:** loans scored, high-risk count, high-risk exposure ($), average risk score.
  - **AI briefing:** the GenAI summary from `at_risk_summary`.
  - **Genie link:** jumps to the NL space.
  - **At-risk queue:** filter by tier, show top N by risk_score.
  - **Open a collection case:** pick a loan + assignee -> writes to `app_collection_cases` (via `INSERT ... SELECT uuid(), ...`); **recent cases** reads it back.
- Deploy: `databricks sync app <ws_path>` then `databricks apps deploy loan-collections-cockpit --source-code-path <ws_path>`. The app SP needs USE CATALOG/SCHEMA + SELECT on the schema, MODIFY on `app_collection_cases`, and CAN_USE on the warehouse.

## 5. Daily operation
1. New raw data lands in the Volume -> start the Lakeflow pipeline (or schedule it) to refresh bronze/silver/training.
2. Re-run the ML job to re-score -> `loan_risk_scored` and `at_risk_summary` refresh.
3. Lakebase synced table updates on its SNAPSHOT schedule (or re-run the direct write).
4. Collections opens the app, works the High tier top-down, opens cases; asks Genie ad-hoc questions.

## 6. Smoke test (how to verify the whole path)
See `evidence/08_app_smoketest.txt`. It runs the app's exact queries: KPIs, the High-tier queue, an open-case `INSERT ... SELECT`, and the read-back. (This test caught a `VALUES(uuid())` bug — Spark cannot evaluate `uuid()` in an inline VALUES; fixed to `INSERT ... SELECT`.)

## 7. Gotchas / lessons
- The Databricks MCP `execute_sql` had a broken certifi path on the build machine; SQL was run via `databricks api post /api/2.0/sql/statements`.
- Genie `create-space` serialized payload = `{"version":2,"data_sources":{"tables":[{"identifier":"..."}]}}`; tables must be sorted by identifier.
- Serverless jobs are bare: `%pip install mlflow scikit-learn` in the notebook.
- The metastore enforces governed tag policies (allowed values for `domain`, `data_classification`); synthetic data left `data_classification` unset.
- `uuid()` is not allowed in inline `VALUES`; use `INSERT ... SELECT`.

## 8. Evidence index (readable as text, in `evidence/`)
`01` data generation + profile · `02` Lakeflow run · `03` UC governance · `04` ML + GenAI · `05`/`05b` Lakebase serving · `06` Genie transcripts · `07` app deploy · `08` app smoke test.
