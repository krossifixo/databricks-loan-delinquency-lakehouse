# Databricks notebook source
# MAGIC %md
# MAGIC # Delinquency Risk Model — train, register (UC), score, GenAI summary
# MAGIC Trains an MLflow model to predict next-month 30+ DPD on currently-current loans,
# MAGIC registers it in Unity Catalog, batch-scores the latest snapshot per loan into
# MAGIC `loan_risk_scored`, and generates a GenAI plain-language summary of the at-risk queue.

# COMMAND ----------
# MAGIC %pip install -q mlflow scikit-learn pandas numpy
# MAGIC %restart_python

# COMMAND ----------
import mlflow, mlflow.sklearn
from pyspark.sql import functions as F
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score, average_precision_score, precision_score
import pandas as pd, numpy as np

CATALOG="serverless_stable_fslt65_catalog"; SCHEMA="loan_delinquency"
mlflow.set_registry_uri("databricks-uc")
MODEL_NAME=f"{CATALOG}.{SCHEMA}.delinquency_risk_model"

# COMMAND ----------
# Load the governed training table produced by Lakeflow
df = spark.table(f"{CATALOG}.{SCHEMA}.delinquency_training").toPandas()
print(f"training rows: {len(df)}   positive rate: {df['target_delinquent_next'].mean():.4f}")

CAT_COLS=["product_type","fico_band","state"]
NUM_COLS=["apr","term_months","dti_ratio","ltv_ratio","monthly_payment",
          "borrower_monthly_income","payment_burden","outstanding_balance","prior_missed_3m"]
X=df[CAT_COLS+NUM_COLS]; y=df["target_delinquent_next"].astype(int)
Xtr,Xte,ytr,yte=train_test_split(X,y,test_size=0.25,random_state=42,stratify=y)

pre=ColumnTransformer([("cat",OneHotEncoder(handle_unknown="ignore"),CAT_COLS),
                       ("num","passthrough",NUM_COLS)])
clf=Pipeline([("pre",pre),
              ("gb",GradientBoostingClassifier(n_estimators=200,max_depth=3,
                                               learning_rate=0.1,random_state=42))])

# COMMAND ----------
with mlflow.start_run(run_name="delinquency_gb") as run:
    clf.fit(Xtr,ytr)
    p=clf.predict_proba(Xte)[:,1]
    auc=roc_auc_score(yte,p); ap=average_precision_score(yte,p)
    # precision@top5% — the collections team only has capacity for the worst slice
    k=int(0.05*len(p)); idx=np.argsort(p)[::-1][:k]
    prec_at5=yte.iloc[idx].mean()
    lift5=prec_at5/yte.mean()
    mlflow.log_metrics({"roc_auc":auc,"pr_auc":ap,"precision_at_top5pct":prec_at5,
                        "lift_at_top5pct":lift5,"positive_rate":float(y.mean())})
    sig=mlflow.models.infer_signature(Xtr,clf.predict_proba(Xtr)[:,1])
    mlflow.sklearn.log_model(clf,"model",signature=sig,
                             registered_model_name=MODEL_NAME,input_example=Xtr.head(3))
    print("="*60)
    print("MODEL METRICS (held-out 25% test set)")
    print(f"  ROC AUC                : {auc:.4f}")
    print(f"  PR AUC (avg precision) : {ap:.4f}")
    print(f"  Base positive rate     : {y.mean():.4f}")
    print(f"  Precision @ top 5%     : {prec_at5:.4f}")
    print(f"  Lift @ top 5%          : {lift5:.2f}x  (collections targeting value)")
    print(f"  registered as          : {MODEL_NAME}")
    print("="*60)

# COMMAND ----------
# Batch score: the LATEST snapshot per loan = today's at-risk queue
latest = (spark.table(f"{CATALOG}.{SCHEMA}.delinquency_training")
          .withColumn("rn",F.row_number().over(
              __import__("pyspark.sql.window",fromlist=["Window"]).Window
              .partitionBy("loan_id").orderBy(F.col("as_of_month").desc())))
          .filter("rn=1").drop("rn")).toPandas()
latest["risk_score"]=clf.predict_proba(latest[CAT_COLS+NUM_COLS])[:,1]
latest["risk_tier"]=pd.cut(latest["risk_score"],bins=[-1,0.05,0.15,2],
                           labels=["Low","Medium","High"])
scored=latest[["loan_id","as_of_month","product_type","fico_band","state","apr",
               "monthly_payment","dti_ratio","ltv_ratio","payment_burden",
               "prior_missed_3m","outstanding_balance","risk_score","risk_tier"]].copy()
scored["risk_score"]=scored["risk_score"].round(4)
sdf=spark.createDataFrame(scored)
sdf.write.mode("overwrite").option("overwriteSchema","true").saveAsTable(f"{CATALOG}.{SCHEMA}.loan_risk_scored")
print(f"scored loans written: {len(scored)}")
print(scored["risk_tier"].value_counts().to_string())

# COMMAND ----------
# GenAI: plain-language summary of the High-risk queue for a collections manager
agg = spark.sql(f"""
  SELECT COUNT(*) n, ROUND(AVG(risk_score),3) avg_score, ROUND(SUM(outstanding_balance),0) exposure,
         ROUND(AVG(payment_burden),3) avg_burden, ROUND(AVG(dti_ratio),3) avg_dti
  FROM {CATALOG}.{SCHEMA}.loan_risk_scored WHERE risk_tier='High'
""").collect()[0]
prompt=(f"You are briefing a collections manager. {agg['n']} auto loans are flagged HIGH risk of "
        f"rolling 30+ days past due next month, with total outstanding exposure of ${agg['exposure']:,.0f}, "
        f"average model risk score {agg['avg_score']}, average payment burden {agg['avg_burden']} and average DTI "
        f"{agg['avg_dti']}. In 3 sentences, summarize the situation and recommend one concrete early-intervention action.")
try:
    summary=spark.sql("SELECT ai_query('databricks-meta-llama-3-3-70b-instruct', :p) s",
                      args={"p":prompt}).collect()[0]["s"]
except Exception as e:
    summary=(f"{agg['n']} loans are high-risk with ${agg['exposure']:,.0f} exposure (avg score {agg['avg_score']}). "
             f"High payment burden ({agg['avg_burden']}) and DTI ({agg['avg_dti']}) are the main drivers. "
             f"Recommend proactive outreach + hardship-program offers to the top-scored loans this week. "
             f"[GenAI endpoint unavailable: {type(e).__name__}]")
spark.createDataFrame([(summary,)],["summary"]).write.mode("overwrite")\
    .saveAsTable(f"{CATALOG}.{SCHEMA}.at_risk_summary")
print("GENAI SUMMARY:\n"+summary)
