# Genie — Collections NL querying

Genie space **Loan Delinquency Risk — Collections Genie** (`01f1c272286c1c379ae5aa850af96c97`) lets risk/collections leads ask questions in plain English over the governed tables (delinquency_training, loan_risk_scored, loans_silver). Recreate with:

```
databricks genie create-space dd8909b1ec28c7ce "$(python3 -c 'import json;print(json.dumps(json.load(open("space_config.json"))["serialized_space"]))')" --title "Loan Delinquency Risk — Collections Genie" -p fevm-serverless-stable-fslt65
```

See `../evidence/06_genie_transcripts.txt` for real question -> generated SQL -> result transcripts.
