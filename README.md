# Early Delinquency Intervention for Auto Lending — End-to-End Lakehouse

**Industry:** Consumer / auto lending.
**Customer problem (specific):** A consumer auto-lender loses money when loans that are *current today* roll into **30+ days past due** and then on to charge-off. Collections has limited capacity and today reacts *after* a loan is already delinquent. They need to know **which currently-current loans are most likely to roll into 30+ DPD next cycle**, so collections can intervene early (proactive outreach, hardship programs) and reduce roll-to-charge-off losses.

**Outcome targeted:** lower early-stage delinquency roll rate and net charge-offs by prioritizing collections on the highest-risk current loans.

## The integrated data journey (six stages)

| Stage | Databricks capability | What it does here |
|---|---|---|
| 1. Ingest | **Lakeflow** | Load raw synthetic loan + payment CSVs from a UC Volume into bronze, then clean to silver with expectations. |
| 2. Govern | **Unity Catalog** | Catalog/schema, table + column comments, PK/FK constraints, tags, grants, lineage. |
| 3. Serve | **Lakebase** | Serve the scored at-risk queue (UC synced table), the GenAI briefing, and the operational collection_cases write-back from serverless Postgres; all three tables are also registered in Unity Catalog so they are queryable from Databricks. |
| 4. Intelligence | **ML + GenAI** | Train an MLflow delinquency-risk model; a GenAI summary explains the daily at-risk queue in plain language. |
| 5. Natural language | **Genie** | A governed Genie space (loans, scored queue, and the operational collection_cases table) so risk/collections leads can ask questions in English. |
| 6. Business surface | **Databricks App** | A Lakebase-native collections cockpit: ranked at-risk loans, AI briefing, an embedded Genie assistant, and case actions written back to Lakebase. |

## Repository layout

```
data/        synthetic data generator + raw landing files + data dictionary
pipelines/   Lakeflow ingestion (bronze -> silver -> features)
sql/         Unity Catalog DDL, governance, Genie-ready views
ml/          feature engineering + model training (MLflow) + batch scoring
lakebase/    sync of scored output to Lakebase for serving
genie/       Genie space definition + example question/SQL/result transcripts
app/         Databricks App (collections cockpit)
evidence/    READABLE-AS-TEXT execution evidence (run logs, query results, metrics)
deck/        business presentation (outcome-led, KPI-quantified)
```

## Execution evidence
Per the submission rules, this repo commits **text** evidence that the build ran: data-generation run logs, Lakeflow pipeline run output, Unity Catalog query results, model metrics and sample scored output, Lakebase verification queries, and Genie question→SQL→result transcripts. See `evidence/`.

## Environment
Built on Databricks (serverless), Unity Catalog catalog `serverless_stable_fslt65_catalog`, schema `loan_delinquency`. All data is synthetic; no real customer data is present.

## Submission summary (all six stages run end-to-end)

| Stage | Artifact | Evidence (text) |
|---|---|---|
| Lakeflow ingest | `pipelines/loan_delinquency_pipeline.sql` | `evidence/02_lakeflow_pipeline_run.txt` |
| Unity Catalog govern | `sql/03_governance.sql` | `evidence/03_unity_catalog_governance.txt` |
| ML + GenAI | `ml/train_model.py` | `evidence/04_ml_genai.txt` (AUC 0.74, lift 3.7x, UC-registered model) |
| Lakebase serving | `lakebase/sync_to_lakebase.py`, `lakebase/synced_table_spec.json` | `evidence/05_lakebase_serving.txt`, `evidence/05b_lakebase_synced_table.txt` |
| Genie NL querying | `genie/space_config.json` | `evidence/06_genie_transcripts.txt` |
| Databricks App | `app/app.py` | `evidence/07_databricks_app.txt` |

- **App:** https://loan-collections-cockpit-7474658995900491.aws.databricksapps.com
- **Genie space:** Loan Delinquency Risk — Collections Genie (`01f1c272286c1c379ae5aa850af96c97`)
- **Deck:** `deck/collections_cockpit_deck.pdf`
- All data synthetic; no real customer data.
