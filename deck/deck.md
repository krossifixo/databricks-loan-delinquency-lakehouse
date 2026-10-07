# Catch Delinquency Before It Costs You
### Early intervention for auto lending, on one governed lakehouse
Presenter: Solutions Architect · Audience: Chief Risk/Lending Officer (sponsor) + Collections & Risk Ops lead (owner)

---

## 1. The business outcome (lead with this)
**Stop losing money to loans that roll from current to charge-off while collections is still reacting after the fact.**

We predict which currently-current loans will roll 30+ days past due **next cycle**, and hand collections a ranked daily queue so they intervene *before* the roll. The result the business feels: **lower net charge-offs and a more efficient collections team**, with no change to how loans are booked.

---

## 2. The problem, in the buyer's terms
- Collections today is **reactive**: a loan is worked only after it is already delinquent, when cure is harder and costlier.
- Capacity is **finite**: the team can only call so many borrowers a month, and today that effort is spread without prioritization.
- The cost shows up as **early-stage roll rate → roll-to-charge-off → net charge-offs ($)** — the KPIs the CRO reports and the Collections lead owns.

On this synthetic 5,000-loan book (~$134.6M outstanding), **3.2% of current loans roll to 30+ DPD each cycle** — the leak we are closing.

---

## 3. What we built — one integrated journey, not six silos
Raw data → decision, on a single platform:
1. **Lakeflow** ingests raw loan + payment data (bronze → silver with data-quality rules).
2. **Unity Catalog** governs it (comments, governed tag policy, grants, lineage).
3. **ML + GenAI** scores every current loan and writes a plain-language briefing.
4. **Lakebase** serves the scored queue, the briefing, and the operational cases from serverless Postgres (all three also queryable in Unity Catalog).
5. **Genie** lets risk/collections ask questions in plain English, including over the live collection cases.
6. **A Lakebase-native Databricks App** puts the ranked queue, the AI briefing, an embedded Genie assistant, and case actions in front of the business, writing cases straight back to Lakebase.

---

## 4. Proof it works (from the actual build)
- Model: next-month 30+ DPD classifier, registered in Unity Catalog.
- **ROC AUC 0.74**; risk ranks monotonically with FICO (0.5% → 11.2%).
- **3.7× lift in the top 5%**: the model's highest-risk slice is **~3.7× more likely** to actually roll than the average loan — so the same collections hour catches far more future delinquencies.
- Today's queue: **153 High-risk loans, $4.4M exposure**, surfaced automatically with an AI briefing and recommended action.

---

## 5. Quantified impact (the KPIs the buyer tracks)
Focus the fixed collections capacity on the model's top slice instead of spreading it:
- **Collections hit rate (precision of the worked queue): 11.8% vs 3.2% baseline** — ~3.7× more productive contacts.
- **Early-stage roll rate**: intervene on the 153 High-risk loans each cycle rather than waiting.
- **Illustrative loss avoided** (assumptions the customer validates): if early outreach cures just **25%** of the $4.4M High-risk exposure that would otherwise roll, at a **~55% loss-given-default** on charge-off, that is **~$0.6M in net charge-offs avoided per cycle** on this book — scaling with portfolio size.
- **No new cost to book loans**: this runs on the data you already have.

---

## 6. Value for the executive sponsor (CRO / Chief Lending Officer)
- **Lower net charge-offs and provisioning** by shifting collections from reactive to predictive.
- **One governed platform** from raw data to app: auditable lineage, governed tag policies, and access control satisfy risk and audit.
- **Scales and compounds**: the same pattern extends to pricing, line management, and recovery, on infrastructure you already run.

---

## 7. Value for the domain owner (Collections & Risk Ops lead)
- **A ranked daily queue** instead of a flat list — work the riskiest dollars first.
- **An AI briefing** that explains the queue and recommends an action in plain language.
- **Self-serve answers** via an embedded Genie assistant ("which FICO band is rolling fastest?", "how many open cases per team?") with no SQL and without leaving the cockpit.
- **Case workflow built in**: open and assign a case from the same screen; it is written back operationally to Lakebase and is immediately queryable in Genie and Unity Catalog.

---

## 8. Why Databricks (why integrated matters)
- The hand-offs between ingest, governance, ML, serving, NL, and the app are **the usual failure points**. Here they are one platform, one security model, one copy of governed data.
- From a **raw file to a business decision** with no data movement to bolt-on tools — faster to value and cheaper to run.

---

## 9. Next steps
1. Point this at a **real (scrubbed) book** and validate the lift on your charge-off history.
2. Agree the **intervention playbook** (who gets called, what offer) for the High tier.
3. Pilot with the collections team for one cycle; measure roll-rate and hit-rate deltas.
4. Expand the governed lakehouse pattern to the next risk use case.

*All figures above are from a synthetic dataset built for this prototype; dollar impact is illustrative and to be validated against the customer's actuals.*
