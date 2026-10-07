-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Lakeflow Declarative Pipeline — Loan Delinquency
-- MAGIC Ingests raw loan + payment CSVs from the Unity Catalog Volume landing zone,
-- MAGIC cleans/types them to silver with data-quality expectations, and builds the
-- MAGIC ML-ready training/scoring table with the next-month 30+ DPD label.
-- MAGIC Target: serverless_stable_fslt65_catalog.loan_delinquency

-- COMMAND ----------

-- BRONZE: raw loan origination master, ingested from the Volume landing zone
CREATE OR REFRESH STREAMING TABLE loans_bronze
COMMENT "Raw loan origination master, auto-ingested from the UC Volume landing zone"
AS SELECT *, _metadata.file_name AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/serverless_stable_fslt65_catalog/loan_delinquency/raw_landing/loans',
  format => 'csv', header => true, inferColumnTypes => true);

-- COMMAND ----------

-- BRONZE: raw monthly payment-history snapshots
CREATE OR REFRESH STREAMING TABLE payments_bronze
COMMENT "Raw monthly payment-history snapshots, auto-ingested from the landing zone"
AS SELECT *, _metadata.file_name AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/Volumes/serverless_stable_fslt65_catalog/loan_delinquency/raw_landing/payments',
  format => 'csv', header => true, inferColumnTypes => true);

-- COMMAND ----------

-- SILVER: typed, validated loans (expectations drop bad rows)
CREATE OR REFRESH MATERIALIZED VIEW loans_silver (
  CONSTRAINT valid_loan_id   EXPECT (loan_id IS NOT NULL)      ON VIOLATION DROP ROW,
  CONSTRAINT valid_principal EXPECT (principal_amount > 0)     ON VIOLATION DROP ROW,
  CONSTRAINT valid_dti       EXPECT (dti_ratio BETWEEN 0 AND 1)
)
COMMENT "Cleaned, typed loan master"
AS SELECT
  loan_id,
  CAST(origination_date AS DATE)        AS origination_date,
  product_type,
  CAST(principal_amount AS DOUBLE)      AS principal_amount,
  CAST(apr AS DOUBLE)                   AS apr,
  CAST(term_months AS INT)              AS term_months,
  CAST(monthly_payment AS DOUBLE)       AS monthly_payment,
  fico_band,
  CAST(borrower_monthly_income AS DOUBLE) AS borrower_monthly_income,
  CAST(dti_ratio AS DOUBLE)             AS dti_ratio,
  CAST(ltv_ratio AS DOUBLE)             AS ltv_ratio,
  state
FROM loans_bronze;

-- COMMAND ----------

-- SILVER: typed, validated payment snapshots
CREATE OR REFRESH MATERIALIZED VIEW payments_silver (
  CONSTRAINT valid_dpd   EXPECT (days_past_due >= 0) ON VIOLATION DROP ROW,
  CONSTRAINT valid_month EXPECT (as_of_month IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT "Cleaned, typed monthly payment snapshots"
AS SELECT
  loan_id,
  CAST(as_of_month AS DATE)          AS as_of_month,
  CAST(scheduled_payment AS DOUBLE)  AS scheduled_payment,
  CAST(actual_payment AS DOUBLE)     AS actual_payment,
  CAST(outstanding_balance AS DOUBLE) AS outstanding_balance,
  CAST(days_past_due AS INT)         AS days_past_due,
  delinquency_bucket
FROM payments_bronze;

-- COMMAND ----------

-- GOLD / FEATURES: one row per (loan, month) that is CURRENT this month,
-- labeled with whether it rolls to 30+ DPD NEXT month. This is the ML target.
CREATE OR REFRESH MATERIALIZED VIEW delinquency_training (
  CONSTRAINT has_label EXPECT (target_delinquent_next IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT "ML training/scoring set: current loans + next-month 30+DPD label and risk features"
AS
WITH p AS (
  SELECT
    loan_id, as_of_month, days_past_due, actual_payment, scheduled_payment, outstanding_balance,
    LEAD(days_past_due) OVER (PARTITION BY loan_id ORDER BY as_of_month) AS next_dpd,
    SUM(CASE WHEN days_past_due > 0 THEN 1 ELSE 0 END)
      OVER (PARTITION BY loan_id ORDER BY as_of_month ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS prior_missed_3m
  FROM payments_silver
)
SELECT
  p.loan_id,
  p.as_of_month,
  l.product_type,
  l.fico_band,
  l.apr,
  l.term_months,
  l.dti_ratio,
  l.ltv_ratio,
  l.monthly_payment,
  l.borrower_monthly_income,
  l.state,
  (l.monthly_payment / NULLIF(l.borrower_monthly_income, 0)) AS payment_burden,
  p.outstanding_balance,
  COALESCE(p.prior_missed_3m, 0) AS prior_missed_3m,
  CASE WHEN p.next_dpd >= 30 THEN 1 ELSE 0 END AS target_delinquent_next
FROM p
JOIN loans_silver l USING (loan_id)
WHERE p.days_past_due = 0        -- only loans that are CURRENT this month
  AND p.next_dpd IS NOT NULL;    -- need a next month to label against
