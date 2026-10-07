"""
Collections Cockpit — Early Delinquency Intervention
A Databricks App that reads the ML-scored at-risk queue and GenAI briefing from, and
writes collection cases to, the Lakebase operational database. The app authenticates as
its own service principal and mints a short-lived Lakebase credential at runtime.
"""
import os, uuid
import streamlit as st
import pandas as pd
import psycopg2
from databricks.sdk import WorkspaceClient

INSTANCE = os.environ.get("LAKEBASE_INSTANCE", "loan-delinquency-db")
PGHOST = os.environ.get("PGHOST", "ep-rapid-hill-d2oltmgm.database.us-east-1.cloud.databricks.com")
PGUSER = os.environ.get("PGUSER", "a2c59ebf-343f-424b-9604-0f15a8e1ec33")  # app service principal
PGDB = os.environ.get("PGDATABASE", "databricks_postgres")
GENIE_SPACE = "01f1c272286c1c379ae5aa850af96c97"
HOST = os.environ.get("DATABRICKS_HOST", "fevm-serverless-stable-fslt65.cloud.databricks.com")

SCORED = "serving.loan_risk_scored_synced"   # Lakebase UC synced table (queue)
SUMMARY = "public.at_risk_summary"           # GenAI briefing
CASES = "public.collection_cases"            # operational write-back

st.set_page_config(page_title="Collections Cockpit", layout="wide")
w = WorkspaceClient()

def connect():
    cred = w.database.generate_database_credential(request_id=str(uuid.uuid4()), instance_names=[INSTANCE])
    return psycopg2.connect(host=PGHOST, port=5432, dbname=PGDB, user=PGUSER,
                            password=cred.token, sslmode="require")

def q(sql, params=None):
    with connect() as c, c.cursor() as cur:
        cur.execute(sql, params or ())
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)

def write(sql, params):
    with connect() as c, c.cursor() as cur:
        cur.execute(sql, params); c.commit()

st.title("Collections Cockpit")
st.caption("Early delinquency intervention for auto lending — rank today's current loans by their risk of rolling 30+ DPD next cycle. Served from Lakebase.")

# --- KPIs ---
k = q(f"""SELECT COUNT(*) loans,
       SUM(CASE WHEN risk_tier='High' THEN 1 ELSE 0 END) high,
       ROUND(SUM(CASE WHEN risk_tier='High' THEN outstanding_balance ELSE 0 END)::numeric,0) high_exposure,
       ROUND(AVG(risk_score)::numeric,4) avg_score
       FROM {SCORED}""")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Loans scored", f"{int(k.loans[0]):,}")
c2.metric("High-risk loans", f"{int(k.high[0]):,}")
c3.metric("High-risk exposure", f"${float(k.high_exposure[0]):,.0f}")
c4.metric("Avg risk score", f"{float(k.avg_score[0]):.4f}")

# --- GenAI briefing ---
try:
    s = q(f"SELECT summary FROM {SUMMARY} LIMIT 1")
    if len(s):
        st.subheader("AI briefing")
        st.info(s.iloc[0, 0])
except Exception as e:
    st.caption(f"(briefing unavailable: {e})")

st.link_button("Ask the data in natural language (Genie)", f"https://{HOST}/genie/rooms/{GENIE_SPACE}")

# --- At-risk queue ---
st.subheader("At-risk queue")
tier = st.selectbox("Risk tier", ["High", "Medium", "Low"], index=0)
n = st.slider("Show top N", 5, 100, 20)
queue = q(f"""SELECT loan_id, fico_band, state, ROUND(risk_score::numeric,4) risk_score, risk_tier,
       ROUND(payment_burden::numeric,3) payment_burden, prior_missed_3m,
       ROUND(outstanding_balance::numeric,0) outstanding_balance
       FROM {SCORED} WHERE risk_tier=%s ORDER BY risk_score DESC LIMIT %s""", (tier, n))
st.dataframe(queue, use_container_width=True, hide_index=True)

# --- Open a collection case (writes to Lakebase) ---
st.subheader("Open a collection case")
with st.form("case"):
    loan = st.selectbox("Loan", queue.loan_id.tolist() if len(queue) else [])
    owner = st.text_input("Assign to (team alias)", "collections-team")
    submitted = st.form_submit_button("Open case")
    if submitted and loan:
        write(f"INSERT INTO {CASES} (loan_id, risk_tier, assigned_to) VALUES (%s,%s,%s)", (loan, tier, owner))
        st.success(f"Case opened for {loan}, assigned to {owner}. (written to Lakebase)")

# --- Recent cases (from Lakebase) ---
try:
    cases = q(f"SELECT loan_id, risk_tier, assigned_to, status, created_at FROM {CASES} ORDER BY created_at DESC LIMIT 10")
    if len(cases):
        st.subheader("Recent cases")
        st.dataframe(cases, use_container_width=True, hide_index=True)
    else:
        st.caption("No cases opened yet.")
except Exception as e:
    st.caption(f"(cases unavailable: {e})")
