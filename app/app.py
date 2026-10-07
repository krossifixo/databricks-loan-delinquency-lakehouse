"""
Collections Cockpit — Early Delinquency Intervention
A Databricks App that reads the ML-scored at-risk queue and GenAI briefing from, and
writes collection cases to, the Lakebase operational database. The app authenticates as
its own service principal and mints a short-lived Lakebase credential at runtime.
"""
import os, uuid, time
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
    # version-independent: call the Lakebase credential REST endpoint directly
    resp = w.api_client.do("POST", "/api/2.0/database/credentials",
                           body={"request_id": str(uuid.uuid4()), "instance_names": [INSTANCE]})
    token = resp["token"]
    return psycopg2.connect(host=PGHOST, port=5432, dbname=PGDB, user=PGUSER,
                            password=token, sslmode="require")

def q(sql, params=None):
    with connect() as c, c.cursor() as cur:
        cur.execute(sql, params or ())
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)

def write(sql, params):
    with connect() as c, c.cursor() as cur:
        cur.execute(sql, params); c.commit()

def genie_ask(question):
    """Ask the Genie space (Conversation API) and return (text, sql, dataframe)."""
    sid = GENIE_SPACE
    conv = st.session_state.get("genie_conv")
    if conv:
        r = w.api_client.do("POST", f"/api/2.0/genie/spaces/{sid}/conversations/{conv}/messages",
                            body={"content": question})
        msg = r.get("message_id") or r.get("id")
    else:
        r = w.api_client.do("POST", f"/api/2.0/genie/spaces/{sid}/start-conversation",
                            body={"content": question})
        conv = r.get("conversation_id"); msg = r.get("message_id")
        st.session_state["genie_conv"] = conv
    status = None
    for _ in range(45):
        m = w.api_client.do("GET", f"/api/2.0/genie/spaces/{sid}/conversations/{conv}/messages/{msg}")
        status = m.get("status")
        if status in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)
    text, sql, df = None, None, None
    for a in (m.get("attachments") or []):
        if a.get("text", {}).get("content"):
            text = a["text"]["content"]
        if "query" in a:
            sql = a["query"].get("query") or a["query"].get("description")
            aid = a.get("attachment_id")
            try:
                qr = w.api_client.do("GET", f"/api/2.0/genie/spaces/{sid}/conversations/{conv}/messages/{msg}/attachments/{aid}/query-result")
                sr = qr["statement_response"]; res = sr.get("result", {})
                cols = [c["name"] for c in sr["manifest"]["schema"]["columns"]]
                df = pd.DataFrame(res.get("data_array", []), columns=cols)
            except Exception:
                pass
    if status == "FAILED" and not text:
        text = "Genie could not answer that one. Try rephrasing."
    return text or "(no answer returned)", sql, df

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

st.link_button("Open the full Genie space", f"https://{HOST}/genie/rooms/{GENIE_SPACE}")

# --- Floating in-app Genie chatbot (pinned bottom-right, does not reflow the page) ---
st.markdown("""
<style>
/* pin the Genie popover trigger to the bottom-right corner */
div[data-testid="stPopover"] { position: fixed; bottom: 24px; right: 24px; z-index: 1000; }
/* size + scroll the popover panel so chat stays in its own box */
div[data-testid="stPopoverBody"] { width: 430px; max-width: 92vw; max-height: 72vh; overflow-y: auto; }
</style>
""", unsafe_allow_html=True)

if "genie_hist" not in st.session_state:
    st.session_state.genie_hist = []
SAMPLES = [
    "How many loans are in each risk tier?",
    "Which FICO band has the highest delinquency rate?",
    "How many open collection cases are there, grouped by assigned_to?",
    "List the top 5 loans by risk score.",
]

with st.popover("💬 Ask Genie", use_container_width=False):
    st.caption("Ask about loans, delinquency drivers, or open cases — powered by the Genie space.")
    bcols = st.columns(2)
    pending = None
    for i, s in enumerate(SAMPLES):
        if bcols[i % 2].button(s, key=f"gq{i}"):
            pending = s
    with st.form("genie_form", clear_on_submit=True):
        typed = st.text_input("Ask Genie", label_visibility="collapsed",
                              placeholder="Ask a question about the portfolio...")
        if st.form_submit_button("Send") and typed:
            pending = typed
    if st.button("Clear chat", key="genie_clear"):
        st.session_state.genie_hist = []
        st.session_state.pop("genie_conv", None)
    # process synchronously (no st.rerun) so the panel stays open and shows the answer
    if pending:
        st.session_state.genie_hist.append(("user", pending, None, None))
        with st.spinner("Genie is thinking..."):
            text, sql, df = genie_ask(pending)
        st.session_state.genie_hist.append(("assistant", text, sql, df))
    # render the conversation inside the popover
    for role, content, sql, df in st.session_state.genie_hist:
        with st.chat_message(role):
            st.markdown(content)
            if sql:
                with st.expander("SQL Genie ran"):
                    st.code(sql, language="sql")
            if df is not None and len(df):
                st.dataframe(df, use_container_width=True, hide_index=True)

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
