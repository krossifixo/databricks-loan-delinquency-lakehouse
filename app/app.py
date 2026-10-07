"""
Collections Cockpit — Early Delinquency Intervention
A Databricks App that surfaces the ML-scored at-risk loan queue (served via the
Lakebase UC synced table), the GenAI summary, and lets a collections manager
open cases. Reads/writes through the SQL warehouse using the app's identity.
"""
import os
import streamlit as st
import pandas as pd
from databricks.sdk import WorkspaceClient

CATALOG = "serverless_stable_fslt65_catalog"
SCHEMA = "loan_delinquency"
# serving table (Lakebase-synced UC table); falls back to the Delta scored table
SERVING = f"{CATALOG}.{SCHEMA}.loan_risk_scored"
SUMMARY = f"{CATALOG}.{SCHEMA}.at_risk_summary"
CASES = f"{CATALOG}.{SCHEMA}.app_collection_cases"
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "dd8909b1ec28c7ce")
GENIE_SPACE = "01f1c272286c1c379ae5aa850af96c97"

st.set_page_config(page_title="Collections Cockpit", layout="wide")
w = WorkspaceClient()

def sql(q: str) -> pd.DataFrame:
    r = w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=q, wait_timeout="50s")
    cols = [c.name for c in r.manifest.schema.columns] if r.manifest and r.manifest.schema else []
    rows = r.result.data_array if (r.result and r.result.data_array) else []
    return pd.DataFrame(rows, columns=cols)

def exec_sql(q: str):
    w.statement_execution.execute_statement(warehouse_id=WAREHOUSE_ID, statement=q, wait_timeout="50s")

st.title("Collections Cockpit")
st.caption("Early delinquency intervention for auto lending — rank today's current loans by their risk of rolling 30+ DPD next cycle.")

# --- KPIs ---
k = sql(f"""SELECT
  COUNT(*) AS loans,
  SUM(CASE WHEN risk_tier='High' THEN 1 ELSE 0 END) AS high,
  ROUND(SUM(CASE WHEN risk_tier='High' THEN outstanding_balance ELSE 0 END),0) AS high_exposure,
  ROUND(AVG(risk_score),4) AS avg_score
FROM {SERVING}""")
loans = int(k.loans[0]); high = int(k.high[0]); exposure = float(k.high_exposure[0])
c1, c2, c3, c4 = st.columns(4)
c1.metric("Loans scored", f"{loans:,}")
c2.metric("High-risk loans", f"{high:,}")
c3.metric("High-risk exposure", f"${exposure:,.0f}")
c4.metric("Avg risk score", k.avg_score[0])

# --- GenAI summary ---
try:
    s = sql(f"SELECT summary FROM {SUMMARY} WHERE id IS NOT NULL OR summary IS NOT NULL LIMIT 1")
    if len(s):
        st.subheader("AI briefing")
        st.info(s.iloc[0, 0])
except Exception:
    pass

st.link_button("Ask the data in natural language (Genie)",
               f"https://{os.environ.get('DATABRICKS_HOST','fevm-serverless-stable-fslt65.cloud.databricks.com')}/genie/rooms/{GENIE_SPACE}")

# --- At-risk queue ---
st.subheader("At-risk queue")
tier = st.selectbox("Risk tier", ["High", "Medium", "Low"], index=0)
n = st.slider("Show top N", 5, 100, 20)
q = sql(f"""SELECT loan_id, fico_band, state, ROUND(risk_score,4) AS risk_score, risk_tier,
       ROUND(payment_burden,3) AS payment_burden, prior_missed_3m,
       ROUND(outstanding_balance,0) AS outstanding_balance
FROM {SERVING} WHERE risk_tier='{tier}' ORDER BY risk_score DESC LIMIT {n}""")
st.dataframe(q, use_container_width=True, hide_index=True)

# --- Open a collection case (write-back) ---
st.subheader("Open a collection case")
with st.form("case"):
    loan = st.selectbox("Loan", q.loan_id.tolist() if len(q) else [])
    owner = st.text_input("Assign to (team alias)", "collections-team")
    submitted = st.form_submit_button("Open case")
    if submitted and loan:
        exec_sql(f"""CREATE TABLE IF NOT EXISTS {CASES}
          (case_id STRING, loan_id STRING, risk_tier STRING, assigned_to STRING, status STRING, created_at TIMESTAMP)""")
        exec_sql(f"""INSERT INTO {CASES} VALUES
          (uuid(), '{loan}', '{tier}', '{owner}', 'open', current_timestamp())""")
        st.success(f"Case opened for {loan}, assigned to {owner}.")

# --- Recent cases ---
try:
    cases = sql(f"SELECT loan_id, risk_tier, assigned_to, status, created_at FROM {CASES} ORDER BY created_at DESC LIMIT 10")
    if len(cases):
        st.subheader("Recent cases")
        st.dataframe(cases, use_container_width=True, hide_index=True)
except Exception:
    st.caption("No cases opened yet.")
