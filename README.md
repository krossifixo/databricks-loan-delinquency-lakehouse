# Early Delinquency Intervention for Auto Lending — End-to-End Lakehouse

**Industry:** Consumer / auto lending.
**Customer problem (specific):** A consumer auto-lender loses money when loans that are *current today* roll into **30+ days past due** and then on to charge-off. Collections has limited capacity and today reacts *after* a loan is already delinquent. They need to know **which currently-current loans are most likely to roll into 30+ DPD next cycle**, so collections can intervene early (proactive outreach, hardship programs) and reduce roll-to-charge-off losses.

**Outcome targeted:** lower early-stage delinquency roll rate and net charge-offs by prioritizing collections on the highest-risk current loans.

## The integrated data journey (six stages)

| Stage | Databricks capability | What it does here |
|---|---|---|
| 1. Ingest | **Lakeflow** | Load raw synthetic loan + payment CSVs from a UC Volume into bronze, then clean to silver with expectations. |
| 2. Govern | **Unity Catalog** | Catalog/schema, table + column comments, PK/FK constraints, tags, grants, lineage. |
| 3. Serve | **Lakebase** | Sync scored at-risk loans / collection cases to Postgres for low-latency operational serving to the app. |
| 4. Intelligence | **ML + GenAI** | Train an MLflow delinquency-risk model; a GenAI summary explains the daily at-risk queue in plain language. |
| 5. Natural language | **Genie** | A governed Genie space so risk/collections leads can ask questions in English. |
| 6. Business surface | **Databricks App** | A collections cockpit: ranked at-risk loans, risk drivers, Genie Q&A, and case actions. |

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
