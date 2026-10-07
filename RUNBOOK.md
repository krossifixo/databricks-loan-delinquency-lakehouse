# Runbook — Early Delinquency Intervention Lakehouse

This runbook explains what was built, what each Databricks service does (in plain language),
how the pieces connect, how to run a live customer demo, and how to recreate every stage. It
is the operational companion to the submission `README.md`.

- **Workspace:** fevm-serverless-stable-fslt65 (`https://fevm-serverless-stable-fslt65.cloud.databricks.com`) · profile `fevm-serverless-stable-fslt65`
- **Analytics catalog/schema:** `serverless_stable_fslt65_catalog.loan_delinquency` · SQL warehouse `dd8909b1ec28c7ce`
- **Lakebase (operational) catalog:** `loan_delinquency_pg` · instance `loan-delinquency-db`
- **App:** https://loan-collections-cockpit-7474658995900491.aws.databricksapps.com
- **Genie space:** Loan Delinquency Risk — Collections Genie (`01f1c272286c1c379ae5aa850af96c97`)
- **Deck:** `deck/collections_cockpit_deck.pdf` (+ editable Google Slides linked in `deck/README.md`)
- All data is synthetic; no real customer data is present.

---

## 1. The business problem (one line)

A consumer auto-lender loses money when loans that are current today roll into 30+ days past
due and on to charge-off. Collections has finite capacity and reacts after a loan is already
delinquent. We predict which currently-current loans will roll 30+ DPD next cycle and hand
collections a ranked daily queue so they intervene early.

---

## 2. What each service does (beginner-friendly glossary)

| Service | What it is, in plain terms | What it does in this build |
|---|---|---|
| **Lakeflow Declarative Pipelines** | A managed way to turn raw files into clean, tested tables with simple declarative SQL (bronze -> silver -> features). | Reads the raw loan + payment CSVs from a Unity Catalog Volume and builds `loans_bronze`, `loans_silver`, and the modeling table `delinquency_training`, applying data-quality expectations. |
| **Unity Catalog (UC)** | The single governance layer over all data and AI: catalogs/schemas, permissions, lineage, tags, comments. | Governs every table (comments, PK/FK, a governed tag policy forcing a `domain` tag, grants, lineage). Also registers the Lakebase tables so they are queryable from Databricks. |
| **Lakebase** | A serverless Postgres (OLTP) database built into Databricks for low-latency app serving and write-back, kept in sync with the lakehouse. | Serves the scored at-risk queue, the AI briefing, and stores operational collection cases the app writes back. |
| **MLflow + Unity Catalog Models** | Experiment tracking plus a governed model registry. | A gradient-boosting classifier that scores next-cycle 30+ DPD risk, registered in UC and used to score every current loan. |
| **GenAI (ai_query / Foundation Model APIs)** | Call a hosted LLM from SQL/Python with no infra to manage. | Writes a plain-language briefing summarizing today's at-risk queue and a recommended action. |
| **Genie** | A governed natural-language-to-SQL assistant over chosen tables. | Lets risk/collections leads ask questions in English over the loans, the scored queue, and the live collection cases. |
| **Databricks Apps** | Host a web app (here Streamlit) inside Databricks, authenticated as its own service principal. | The Collections Cockpit: KPIs, AI briefing, ranked queue, an embedded Genie assistant, and open-a-case actions. |

---

## 3. Architecture and data flow

```
raw CSVs (UC Volume)
  -> Lakeflow pipeline  : loans_bronze -> loans_silver -> delinquency_training
  -> ML (MLflow/UC)     : delinquency_risk_model scores every current loan -> loan_risk_scored (Delta)
  -> GenAI (ai_query)   : at_risk_summary briefing text
  -> Lakebase serving:
         serving.loan_risk_scored_synced   (UC SYNCED TABLE from loan_risk_scored = the queue)
         public.at_risk_summary            (briefing, seeded from UC each ML run)
         public.collection_cases           (empty; the app INSERTs here)
  -> Genie space        : loans_silver, loan_risk_scored, delinquency_training, collection_cases
  -> Databricks App (SP): reads synced queue + briefing from Lakebase, writes cases to Lakebase,
                          embeds a Genie chat, links to the full Genie space
```

### Final Lakebase architecture (3 tables)
| Table | Role | Maintained by |
|---|---|---|
| `serving.loan_risk_scored_synced` | At-risk queue (5,000 scored loans) | Native UC **synced table** (SNAPSHOT from the Delta source) |
| `public.at_risk_summary` | GenAI briefing (1 row) | `lakebase/sync_to_lakebase.py` (pulled from UC each ML run) |
| `public.collection_cases` | Operational case write-back | Created empty; the app INSERTs; 2 cases persisted so far |

The redundant direct-write `public.loan_risk_scored` and the orphaned Delta `app_collection_cases`
were dropped — the synced table is the one queue, and the app writes cases straight to Lakebase.

### The app is Lakebase-native
It authenticates as its own service principal (`a2c59ebf-343f-424b-9604-0f15a8e1ec33`), mints a
short-lived Lakebase credential at runtime (REST `POST /api/2.0/database/credentials`), connects
to Postgres with `sslmode=require`, reads the synced queue + briefing, and writes cases. The SP
has least-privilege grants: SELECT on the queue + briefing, INSERT/SELECT on `collection_cases`,
and USAGE/SELECT on its serial sequence.

### Embedded Genie assistant (no tool-switching)
The cockpit has a floating bottom-right "Ask Genie" widget. It calls the Genie Conversation API
(start-conversation -> poll the message to COMPLETED -> fetch the attachment query-result) and
renders the answer text, the SQL Genie generated, and the result table inside its own panel,
without reflowing the rest of the page. The link to the full Genie space is also kept.

### Everything is queryable in Unity Catalog
All three Lakebase tables live under UC catalog `loan_delinquency_pg`. The synced table
auto-registers; the two Postgres tables were registered once (no data copy — UC reads live
from Lakebase). Example: `SELECT * FROM loan_delinquency_pg.public.collection_cases ORDER BY created_at DESC;`

---

## 4. Live customer demo script (about 10 minutes)

1. **Frame the problem (1 min).** "Collections works loans after they are already late. We want
   to call the right borrowers before they roll. Here is a single governed lakehouse that does
   raw data to decision." Open the deck's outcome slide.
2. **Show the governed data (1 min).** In Catalog Explorer, open
   `serverless_stable_fslt65_catalog.loan_delinquency`: show `loans_silver` and
   `delinquency_training` with comments, the `domain` tag, and lineage back to the raw Volume.
   One sentence per stage: Lakeflow built these; Unity Catalog governs them.
3. **Show the model result (1 min).** Open `loan_risk_scored`: 5,000 loans scored, risk_tier
   High/Medium/Low. Mention ROC AUC 0.74 and 3.7x lift in the top 5%.
4. **Open the app (3 min).** Go to the Collections Cockpit URL. Walk the KPIs
   (5,000 loans, 153 High, ~$4.4M High exposure), read the AI briefing aloud, filter the
   at-risk queue to High and show the ranked list. Then open a case on the top loan and show
   the success message ("written to Lakebase").
5. **Ask Genie inside the app (2 min).** Click the bottom-right "Ask Genie" bubble. Ask
   "How many open collection cases are there, grouped by assigned_to?" and
   "Which FICO band has the highest delinquency rate?" Point out the generated SQL and that
   the case you just opened already shows up — the write-back loop closed with no copy.
6. **Close the loop in UC (1 min).** In a SQL editor run
   `SELECT * FROM loan_delinquency_pg.public.collection_cases ORDER BY created_at DESC;` to show
   the same operational rows are governed and queryable in Databricks.
7. **Land the value (1 min).** Return to the deck: lower net charge-offs, a more productive
   collections team, one governed platform. Hand to next steps.

Reset between demos: delete test rows with `DELETE FROM loan_delinquency_pg.public.collection_cases WHERE assigned_to = 'collections-team';` (or leave them — they are harmless synthetic cases).

---

## 5. Recreate / redeploy each stage

```bash
P=fevm-serverless-stable-fslt65

# 1. Data + pipeline
python3 data/generate_data.py                     # writes data/raw/*.csv
#   upload CSVs to the UC Volume, then run the Lakeflow pipeline:
databricks pipelines ... (pipelines/loan_delinquency_pipeline.sql)   -p $P

# 2. Governance
#   run sql/03_governance.sql via databricks api post /api/2.0/sql/statements

# 3. ML + GenAI
#   run ml/train_model.py as a serverless job (notebook must %pip install mlflow scikit-learn)

# 4. Lakebase
databricks database create-synced-database-table --json @lakebase/synced_table_spec.json -p $P
python3 lakebase/sync_to_lakebase.py              # seeds at_risk_summary + collection_cases + SP grants
#   register the Postgres tables in UC (one-time, no copy):
databricks schemas create public loan_delinquency_pg -p $P
databricks database create-database-table loan_delinquency_pg.public.collection_cases \
  --database-instance-name loan-delinquency-db --logical-database-name databricks_postgres -p $P
databricks database create-database-table loan_delinquency_pg.public.at_risk_summary \
  --database-instance-name loan-delinquency-db --logical-database-name databricks_postgres -p $P

# 5. Genie
databricks genie create-space dd8909b1ec28c7ce \
  "$(python3 -c 'import json;print(json.dumps(json.load(open("genie/space_config.json"))["serialized_space"]))')" \
  --title "Loan Delinquency Risk — Collections Genie" -p $P
#   add the 4 example questions in the Genie UI (serialized_space has no sample-questions field)

# 6. App
databricks sync app <ws_path> -p $P
databricks apps deploy loan-collections-cockpit --source-code-path <ws_path> -p $P
```

---

## 6. Gotchas (learned during the build)

- The Databricks MCP `execute_sql` has a broken certifi path on this machine — run SQL via
  `databricks api post /api/2.0/sql/statements` instead (see the helper pattern used in evidence).
- Genie `create-space` serialized_space is `{"version":2,"data_sources":{"tables":[{"identifier":...}]}}`
  and the tables **must be sorted by identifier**. There is no field for sample questions — add
  those in the UI.
- Serverless jobs need `%pip install mlflow scikit-learn pandas numpy` + `%restart_python`.
- No `CREATE CATALOG` privilege on this metastore — the Lakebase catalog `loan_delinquency_pg`
  was created manually.
- The governed tag policy only allows `domain` in [finance, sales, supply_chain, quality, hr, operations];
  this build uses `finance`.
- The app's open-case INSERT needs USAGE/SELECT on the `collection_cases` serial sequence, not just
  the table — granted in `lakebase/sync_to_lakebase.py`.
- Older `databricks-sdk` has no `w.database` attribute — mint the Lakebase credential via
  `w.api_client.do("POST", "/api/2.0/database/credentials", ...)`, which is version-independent.
- The embedded-Genie widget is pinned with CSS targeting Streamlit's popover test-ids
  (`stPopover` / `stPopoverBody`); if a future Streamlit version renames those, the selectors need
  a one-line update.
