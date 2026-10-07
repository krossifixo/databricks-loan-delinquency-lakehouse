"""
Serve to Lakebase (final architecture).
The at-risk QUEUE is served by the native UC synced table
`loan_delinquency_pg.serving.loan_risk_scored_synced` (see synced_table_spec.json) —
no custom loader needed. This script only maintains the two tables that are not synced:
  - public.at_risk_summary  : the GenAI briefing (one row) pulled from UC
  - public.collection_cases : operational write-back table the app INSERTs into
"""
import subprocess, json, time, psycopg2
PROFILE="fevm-serverless-stable-fslt65"; WH="dd8909b1ec28c7ce"
CAT="serverless_stable_fslt65_catalog"; SCH="loan_delinquency"
PGHOST="ep-rapid-hill-d2oltmgm.database.us-east-1.cloud.databricks.com"
PGUSER="mark.ativie@databricks.com"; PGDB="databricks_postgres"

def uc_query(sql):
    body={"warehouse_id":WH,"statement":sql,"wait_timeout":"50s","format":"JSON_ARRAY","disposition":"INLINE"}
    d=json.loads(subprocess.run(["databricks","api","post","/api/2.0/sql/statements","-p",PROFILE,"--json",json.dumps(body)],capture_output=True,text=True).stdout)
    sid=d["statement_id"]
    while d.get("status",{}).get("state") in ("PENDING","RUNNING"):
        time.sleep(3)
        d=json.loads(subprocess.run(["databricks","api","get",f"/api/2.0/sql/statements/{sid}","-p",PROFILE],capture_output=True,text=True).stdout)
    return d.get("result",{}).get("data_array",[]) or []

tok=subprocess.run(["databricks","database","generate-database-credential","--json",
    json.dumps({"instance_names":["loan-delinquency-db"]}),"-p",PROFILE],capture_output=True,text=True).stdout
tok=json.loads(tok)["token"]
conn=psycopg2.connect(host=PGHOST,port=5432,dbname=PGDB,user=PGUSER,password=tok,sslmode="require")
conn.autocommit=True; cur=conn.cursor()

# GenAI briefing (refreshed each ML run)
summary=uc_query(f"SELECT summary FROM {CAT}.{SCH}.at_risk_summary")[0][0]
cur.execute("DROP TABLE IF EXISTS public.at_risk_summary; CREATE TABLE public.at_risk_summary(id int PRIMARY KEY, summary text);")
cur.execute("INSERT INTO public.at_risk_summary VALUES (1,%s)", (summary,))

# operational write-back table (app INSERTs cases here)
cur.execute("""CREATE TABLE IF NOT EXISTS public.collection_cases(
  case_id serial PRIMARY KEY, loan_id text, risk_tier text, status text DEFAULT 'open',
  assigned_to text, created_at timestamptz DEFAULT now());""")

# App service-principal least-privilege grants (reproducible); serial PK needs sequence USAGE
SP="a2c59ebf-343f-424b-9604-0f15a8e1ec33"
cur.execute(f'GRANT SELECT ON public.at_risk_summary TO "{SP}"')
cur.execute(f'GRANT SELECT, INSERT ON public.collection_cases TO "{SP}"')
cur.execute(f'GRANT USAGE, SELECT ON SEQUENCE public.collection_cases_case_id_seq TO "{SP}"')
print("Lakebase ready: public.at_risk_summary (briefing), public.collection_cases (write-back); queue served by serving.loan_risk_scored_synced")
cur.close(); conn.close()
