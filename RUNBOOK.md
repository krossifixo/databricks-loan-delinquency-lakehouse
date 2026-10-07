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

---

## 9. Live demo script (customer-facing)

Total time: ~15 minutes. Tell a story from raw data to a business decision. Keep the **app** as the hero; show the plumbing briefly so they trust it, then spend the most time on the app and Genie.

### Pre-demo checklist (do 5 minutes before)
1. Log in to the workspace `fevm-serverless-stable-fslt65`.
2. **Warm the warehouse:** open a SQL editor and run `SELECT 1` on warehouse `dd8909b1ec28c7ce` (serverless cold-start is a few seconds; do it now so nothing stalls on stage).
3. **Open the app** in a tab: https://loan-collections-cockpit-7474658995900491.aws.databricksapps.com (first load wakes it; leave it open).
4. **Open the Genie space** in another tab (Loan Delinquency Risk — Collections Genie).
5. Have the Lakeflow pipeline page and the Catalog page for `serverless_stable_fslt65_catalog.loan_delinquency` open in tabs.
6. (Optional) re-run the smoke test (`evidence/08`) so you know the write-back works.

### The flow
1. **Set the scene (1 min, no screen).** "You lose money when loans that are current today quietly roll into 30+ days past due and then charge off, and collections only finds out after the fact. We built a system that predicts the roll one cycle early so your team can act first. Everything you'll see is one Databricks platform, and all data here is synthetic."

2. **Raw data + Lakeflow ingest (2 min).** Show the Catalog: the raw CSVs landed in a Volume, then the Lakeflow pipeline turned them into clean, trustworthy tables. Open the pipeline graph: "bronze is the raw copy, silver is cleaned and validated — these red/green checks are data-quality rules that drop bad rows automatically — and this gold `delinquency_training` table is model-ready, 51,573 labeled examples." Point out it ran in about a minute.

3. **Unity Catalog governance (1 min).** On a table, show the Lineage tab (raw -> bronze -> silver -> training), the comments, the tag (`domain = finance`), and that access is a single grant. "One place governs who can see what, with full lineage for audit."

4. **The model (1.5 min).** Show the registered model in the Catalog (Models) and its metrics. Talk track: "It scores every current loan for the chance it rolls next month. The number that matters to collections is **lift: the model's top 5% is 3.7x more likely to actually roll than average** — so the same number of calls catches far more real problems."

5. **The app — spend the most time here (5 min).** Switch to the app.
   - **KPIs** up top: 5,000 loans scored, 153 high-risk, $4.4M exposure.
   - **AI briefing:** read the GenAI summary aloud — "the system writes this plain-language brief and a recommended action every run."
   - **At-risk queue:** filter to High, sort by risk score. "This is the collections to-do list, worst dollars first."
   - **Open a case:** pick the top loan, assign to a team, click Open case. Scroll to **Recent cases** to show it persisted. "That action is written back operationally in real time."

6. **Genie — let them drive (2 min).** In the Genie tab, type a plain-English question, e.g. "Which FICO band has the highest delinquency rate?" or "Show the top 5 highest-risk loans." Show that it writes the SQL and returns governed results. "Your risk and collections leads can ask their own questions, no SQL, no analyst in the loop."

7. **Lakebase (30 sec, optional).** "The scored queue is also served from Lakebase, Databricks' operational database, so an app can read it in milliseconds — that's what makes the cockpit feel instant."

8. **Close (1 min).** "From a raw file to a decision in one governed platform: ingest, govern, predict, serve, ask, and act. Next step is to validate this on a scrubbed slice of your real book and measure the roll-rate improvement." Hand to the KPIs on the deck.

### If something is slow
- Warehouse/Lakebase cold start: keep talking; it resolves in seconds. The pre-demo warm-up avoids this.
- App won't load: fall back to the Genie tab and the Catalog, and show `evidence/` query results — the story still lands.

---

## 10. What each Databricks service does (beginner-friendly)

Plain-language explanation of every piece used, no jargon.

- **Delta tables** — the storage format for all tables here. Think of it as a spreadsheet that is reliable at huge scale: it tracks versions, handles updates safely, and is fast to query.
- **Unity Catalog** — the catalog and security guard for all data and AI. It is the single place that lists every table, model, and file, controls who can access each one, and records lineage (what came from what). Analogy: the library catalog plus the librarian who checks your card.
- **Volumes** — governed folders for files (like the raw CSVs) inside Unity Catalog, so even loose files are governed and discoverable.
- **Lakeflow (Declarative Pipelines)** — the assembly line that takes raw data and turns it into clean, trustworthy tables, step by step, with built-in quality checks. You declare what the result should look like and it figures out how to build and refresh it.
- **Bronze / Silver / Gold** — the three quality stages on that assembly line: bronze = raw copy as-landed, silver = cleaned and validated, gold = business/model-ready. (These are a naming convention, not separate products.)
- **Expectations** — the quality checks inside Lakeflow (for example "balance must be >= 0"). Rows that fail can be dropped or flagged, so bad data does not silently poison results.
- **SQL warehouse** — the engine that runs SQL queries. "Serverless" means it starts on demand and you do not manage any servers; it just runs your query and scales itself.
- **MLflow** — the system that trains, tracks, and versions machine-learning models. It records each model's accuracy metrics and stores the model so it can be reused and governed like any other asset.
- **Model (registered in Unity Catalog)** — the trained predictor itself, catalogued and versioned next to the data, so it is governed and auditable, not a loose file on someone's laptop.
- **GenAI / `ai_query` (Foundation Model APIs)** — a built-in call to a large language model from SQL. Here it reads the day's risk numbers and writes a short, plain-English briefing with a recommended action — the "AI analyst" that explains the queue.
- **Lakebase** — Databricks' operational (transactional) database, Postgres under the hood. It serves data to apps with millisecond latency, so a live application can read the scored queue instantly and write back actions like opening a case.
- **Synced table** — an automatic, governed copy of a Unity Catalog table kept up to date inside Lakebase, so the app gets fast operational reads without anyone writing a custom copy job.
- **Genie** — the natural-language interface to your governed data. A business user types a question in plain English and Genie writes the SQL and returns the answer, using only the tables and permissions Unity Catalog allows.
- **Databricks App** — a web application that runs directly on Databricks (no separate hosting). Here it is the "collections cockpit" that shows the ranked at-risk queue, the AI briefing, a Genie link, and the open-a-case button — the business-facing front door to everything above.
- **Service principal** — the app's own identity. The app signs in as this non-human account to read and write data under controlled, least-privilege permissions, rather than borrowing a person's login.
