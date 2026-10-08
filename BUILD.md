# How I built this (build and AI mindset)

This is my own account of how the solution was actually built: the workflow, where the
AI assistant was the force multiplier, where I had to step in and redirect it, and the
reasoning behind the specific data, model, threshold, and prompt choices. The code tells
you *what* exists; this explains *why* it looks the way it does and *how* it got there.

## Approach

I started from a blueprint I had built before (a loan risk assistant) but rebuilt everything
from scratch for this problem, because the old app was gone and I wanted the data model and
serving layer to genuinely fit *early delinquency intervention*, not just reuse a shell. The
goal I set up front: a current borrower rolls 30+ days past due next cycle, and collections
has finite capacity, so the whole build has to end in a *ranked* queue a collections manager
can act on, with the governance an audited lending use case needs.

## Tooling and workflow

I built this with Claude Code driving the **Databricks AI Dev Kit** (its skills plus the
Databricks MCP tools), executing against the `fevm-serverless-stable-fslt65` workspace through
the Databricks CLI. The workflow was stage-by-stage: I described each stage and the design
constraint, the assistant generated the artifact, I ran it, read the real output, and then
either accepted it or redirected. Every stage's text evidence in `evidence/` is the actual run
output from that loop, not a mock-up.

**Where the AI was the force multiplier.** It wrote the first drafts of all the artifacts fast
enough that I could spend my time on judgment instead of boilerplate: the synthetic data
generator, the Lakeflow bronze/silver/features SQL with expectations, the MLflow training
notebook, the Genie space configuration, the Streamlit app, and the deck. It also handled the
mechanical Databricks plumbing I would otherwise have hand-cranked, the pipeline submit, the
Lakebase synced-table spec, the service-principal Postgres role and grants, and the Genie
Conversation API wiring. That compression is the point: raw idea to a running, evidenced stage
in minutes.

**Where I had to intervene or redirect it.** The AI was not left to run unsupervised; several
of the real decisions were mine, and several of its first attempts were wrong until I steered
them:

- **It assumed too much Databricks access.** It tried to `CREATE CATALOG` on the metastore; I
  don't have that privilege here, so I created the Lakebase catalog `loan_delinquency_pg`
  myself and pointed it at that. Same story with the governed tag policy: it tried
  `domain=lending`, which the policy rejected, and I had it fall back to the allowed value
  `finance`.
- **A tool was broken in my environment.** The MCP `execute_sql` had a broken certificate path
  on my machine, so I redirected it to run all SQL through
  `databricks api post /api/2.0/sql/statements` instead. That is why the SQL evidence looks the
  way it does.
- **It had to discover an undocumented schema by trial.** The Genie `create-space`
  `serialized_space` format was not obvious; it iterated through "unknown field" errors until we
  landed on `{"version":2,"data_sources":{"tables":[...]}}` with the tables sorted by identifier.
  I made the call that the sample questions, which that schema has no field for, would be added
  in the UI rather than faked in config.
- **I made it rework the serving architecture.** Its first pass had the app writing directly to
  a plain table and kept a redundant scored copy plus an orphaned Delta table. I decided the
  queue should be a *native Unity Catalog synced table* and that the app should be
  *Lakebase-native* (authenticate as its own service principal, mint a credential at runtime,
  read the synced queue and briefing, and write cases straight back to Lakebase), and had it
  drop the redundant tables. I also had it register the Postgres tables back in Unity Catalog so
  the operational cases are queryable from Databricks, which closes the governance loop.
- **A smoke test caught a real bug.** The app's first case-insert used `uuid()` inside a SQL
  `VALUES` clause, which fails; I caught it in a smoke test and had it switch to a parameterized
  insert. A later run surfaced an `InsufficientPrivilege` on the case-id sequence, so I added the
  `USAGE, SELECT` grant on the sequence and made that reproducible in the sync script. An older
  SDK had no `.database` attribute, so I had it mint the Lakebase credential via the versionless
  REST call instead.
- **Product decisions were mine.** Embedding Genie as a floating in-app assistant (so collections
  never leaves the cockpit), keeping the full-Genie link alongside it, and the plain-language
  rewrite of the deck were all choices I directed.

## Why the specific choices

**The data and its hazard model (`data/generate_data.py`).** I wanted the model to have real,
defensible signal rather than noise, so delinquency is not random: each loan gets a base monthly
30+ DPD hazard by FICO band (from ~0.4% at 780+ up to ~8.5% below 580), then multiplied by the
drivers a credit risk person would expect, DTI above 0.35, LTV above 1.0 (auto loans are often
underwater), and payment burden above 0.18 of income. I weighted **payment burden highest (3.0x),
then DTI (2.2x), then LTV (1.4x)**, because affordability is the dominant early-delinquency driver
in practice. Payment history is a month-by-month state machine with realistic cure/roll-forward
odds (about 45% cure, 35% roll worse). The result is the clean monotonic roll rate by FICO band
the pipeline evidence shows, which is deliberate: it is the sanity check a risk officer looks for.

**The classifier (`ml/train_model.py`).** I used a `GradientBoostingClassifier`
(200 trees, depth 3, learning rate 0.1) rather than logistic regression or a random forest because
the signal is driven by *interactions and thresholds* among FICO, DTI, LTV, burden and prior
missed payments (the hazard model itself is non-linear with kinks), and shallow boosted trees fit
exactly that shape while staying well-calibrated enough to use the predicted probability as a
ranking score. Depth 3 keeps each tree a weak learner and guards against overfitting the 5,000-row
book; 200 estimators at a 0.1 learning rate is the standard, stable pairing. Categorical fields are
one-hot encoded, numerics pass through. I score the *latest snapshot per loan* so the output is
"today's queue," not history.

**The metric I optimized for.** I report ROC AUC (0.74) for discrimination, but the metric I
actually care about is **precision in the top 5% and the lift it implies (3.7x)**, and that choice
is in the code on purpose: collections can only call so many borrowers, so the honest question is
"of the slice you have capacity to work, how many actually roll?" Lift answers that in the
language of the buyer, and it is what the deck's business case is built on.

**The risk-tier cutoffs.** I bucket the predicted probability into Low (< 0.05), Medium (0.05 to
0.15), and High (> 0.15). I set the High cut at 0.15 against a base roll rate of ~3.2% so the High
tier is roughly a 5x+ concentration of risk and lands near the collections team's realistic daily
capacity (it produces ~153 loans here), not an unworkable list. Low at 0.05 is close to the base
rate, i.e. "no worse than average," so the three tiers map to a real triage decision rather than
arbitrary thirds.

**The GenAI briefing prompt.** Rather than ask a model to free-associate, I ground the prompt in
real aggregates computed from the High-risk queue (count, exposure, average score, average payment
burden, average DTI) and constrain the output: "brief a collections manager, in 3 sentences,
summarize and recommend one concrete early-intervention action." The constraint keeps it short,
decision-oriented, and tied to the actual numbers. I used `databricks-meta-llama-3-3-70b-instruct`
through `ai_query` so it is one governed SQL call with no extra infrastructure, and I added a
deterministic fallback paragraph so the pipeline still produces a sensible briefing if the endpoint
is unavailable. That fallback was a deliberate robustness choice, not an afterthought.
