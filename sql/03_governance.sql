-- Unity Catalog governance for the loan_delinquency domain.
-- NOTE: this metastore enforces GOVERNED TAG POLICIES (allowed values are
-- centrally controlled). 'domain' must be one of [finance, sales, supply_chain,
-- quality, hr, operations]; 'data_classification' one of [u-nnpi, cui, pii]
-- (left unset here because the data is synthetic, not PII/CUI). This is itself
-- a governance control the platform enforces.

COMMENT ON SCHEMA serverless_stable_fslt65_catalog.loan_delinquency
  IS 'Early delinquency intervention for auto lending. Synthetic data only. Lakeflow bronze/silver + ML training set.';

-- Governed classification tag (policy-compliant value)
ALTER SCHEMA serverless_stable_fslt65_catalog.loan_delinquency SET TAGS ('domain' = 'finance');

-- Access governance: grant the governed domain to account users (read-only)
GRANT USE SCHEMA, SELECT ON SCHEMA serverless_stable_fslt65_catalog.loan_delinquency TO `account users`;

-- Discoverability tags on the ML gold table
ALTER TABLE serverless_stable_fslt65_catalog.loan_delinquency.delinquency_training
  SET TAGS ('layer' = 'gold', 'contains_label' = 'true');
