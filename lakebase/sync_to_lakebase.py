"""Serve scored loans to Lakebase (Postgres) for low-latency operational access by the app.
Pulls loan_risk_scored + at_risk_summary from Unity Catalog and loads them into the
Lakebase instance 'loan-delinquency-db'. Credential is a short-lived Databricks OAuth token."""
import subprocess, json, time, psycopg2, os
from psycopg2.extras import execute_values

PROFILE="fevm-serverless-stable-fslt65"; WH="dd8909b1ec28c7ce"
CAT="serverless_stable_fslt65_catalog"; SCH="loan_delinquency"
PGHOST="ep-rapid-hill-d2oltmgm.database.us-east-1.cloud.databricks.com"
PGUSER="mark.ativie@databricks.com"; PGDB="databricks_postgres"

def uc_query(sql):
    body={"warehouse_id":WH,"statement":sql,"wait_timeout":"50s","format":"JSON_ARRAY","disposition":"INLINE"}
    d=json.loads(subprocess.run(["databricks","api","post","/api/2.0/sql/statements","-p",PROFILE,
        "--json",json.dumps(body)],capture_output=True,text=True).stdout)
    sid=d["statement_id"]
    while d.get("status",{}).get("state") in ("PENDING","RUNNING"):
        time.sleep(3)
        d=json.loads(subprocess.run(["databricks","api","get",f"/api/2.0/sql/statements/{sid}","-p",PROFILE],
            capture_output=True,text=True).stdout)
    cols=[c["name"] for c in d["manifest"]["schema"]["columns"]]
    return cols, d.get("result",{}).get("data_array",[]) or []

tok=open("/tmp/pgtok.txt").read().strip()
conn=psycopg2.connect(host=PGHOST,port=5432,dbname=PGDB,user=PGUSER,password=tok,sslmode="require")
conn.autocommit=False; cur=conn.cursor()

# 1) scored loans
cols,rows=uc_query(f"SELECT loan_id,CAST(as_of_month AS STRING),product_type,fico_band,state,apr,monthly_payment,dti_ratio,ltv_ratio,payment_burden,prior_missed_3m,outstanding_balance,risk_score,risk_tier FROM {CAT}.{SCH}.loan_risk_scored")
cur.execute("""DROP TABLE IF EXISTS loan_risk_scored;
CREATE TABLE loan_risk_scored(
  loan_id text PRIMARY KEY, as_of_month date, product_type text, fico_band text, state text,
  apr double precision, monthly_payment double precision, dti_ratio double precision,
  ltv_ratio double precision, payment_burden double precision, prior_missed_3m int,
  outstanding_balance double precision, risk_score double precision, risk_tier text);""")
execute_values(cur, "INSERT INTO loan_risk_scored VALUES %s", rows, page_size=1000)
cur.execute("CREATE INDEX idx_risk ON loan_risk_scored(risk_score DESC);")
cur.execute("CREATE INDEX idx_tier ON loan_risk_scored(risk_tier);")

# 2) GenAI summary
_,srows=uc_query(f"SELECT summary FROM {CAT}.{SCH}.at_risk_summary")
cur.execute("DROP TABLE IF EXISTS at_risk_summary; CREATE TABLE at_risk_summary(id int PRIMARY KEY, summary text);")
cur.execute("INSERT INTO at_risk_summary VALUES (1,%s)", (srows[0][0],))
conn.commit()

# 3) a simple collections case table the app writes to (operational state)
cur.execute("""DROP TABLE IF EXISTS collection_cases;
CREATE TABLE collection_cases(
  case_id serial PRIMARY KEY, loan_id text, risk_tier text, status text DEFAULT 'open',
  assigned_to text, created_at timestamptz DEFAULT now());""")

conn.commit()
print(f"loaded loan_risk_scored rows: {len(rows)}")
cur.close(); conn.close()