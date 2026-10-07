#!/usr/bin/env python3
"""
Synthetic raw data generator for the Loan Delinquency Lakehouse journey.

Industry / problem: a consumer auto-lender wants to predict which ACTIVE loans
will roll into early-stage delinquency (30+ days past due) next cycle, so the
collections team can intervene early and reduce roll-to-charge-off losses.

This produces RAW landing files (no labels precomputed) that Lakeflow ingests:
  data/raw/loans.csv       - one row per loan (origination master)
  data/raw/payments.csv    - monthly payment-history snapshots per loan

The data carries real signal (delinquency correlates with low FICO, high DTI,
high LTV, prior missed payments, and higher payment burden) so the downstream
ML model has something to learn. No real customer data is used.
"""
import csv, os, random, datetime, math

SEED = 42
random.seed(SEED)
N_LOANS = 5000
MONTHS = 12                      # months of payment history per loan
OUT = os.path.join(os.path.dirname(__file__), "raw")
os.makedirs(OUT, exist_ok=True)

STATES = ["TX","CA","FL","NY","OH","MI","GA","NC","PA","IL","AZ","WA"]
PRODUCTS = ["new_auto","used_auto","refi_auto"]
FICO_BANDS = ["<580","580-619","620-659","660-699","700-739","740-779","780+"]
# base monthly 30+DPD hazard by band (used_auto / subprime skew higher)
BAND_HAZARD = {"<580":0.085,"580-619":0.055,"620-659":0.035,"660-699":0.022,
               "700-739":0.013,"740-779":0.007,"780+":0.004}

def pick_band():
    # realistic auto-lending FICO distribution, slightly subprime-weighted
    r = random.random()
    cuts = [(0.10,"<580"),(0.18,"580-619"),(0.33,"620-659"),(0.52,"660-699"),
            (0.70,"700-739"),(0.87,"740-779"),(1.01,"780+")]
    for c,b in cuts:
        if r < c: return b
    return "780+"

def origination_date():
    start = datetime.date(2023,1,1)
    return start + datetime.timedelta(days=random.randint(0, 900))

loans = []
for i in range(1, N_LOANS+1):
    band = pick_band()
    product = random.choices(PRODUCTS, weights=[0.35,0.5,0.15])[0]
    principal = round(random.uniform(8000, 55000), 2)
    apr = round({"<580":0.19,"580-619":0.16,"620-659":0.13,"660-699":0.10,
                 "700-739":0.075,"740-779":0.06,"780+":0.049}[band]
                + random.uniform(-0.01,0.02), 4)
    term = random.choice([48,60,72,84])
    income = round(random.uniform(2800, 11000), 2)       # monthly gross
    # monthly payment (amortized)
    r = apr/12
    pmt = round(principal * r / (1 - (1+r)**(-term)), 2)
    dti = round(min(0.75, (pmt + random.uniform(400,2600)) / income), 4)
    ltv = round(random.uniform(0.80, 1.25), 4)           # auto often >100%
    loans.append({
        "loan_id": f"LN{i:06d}",
        "origination_date": origination_date().isoformat(),
        "product_type": product,
        "principal_amount": principal,
        "apr": apr,
        "term_months": term,
        "monthly_payment": pmt,
        "fico_band": band,
        "borrower_monthly_income": income,
        "dti_ratio": dti,
        "ltv_ratio": ltv,
        "state": random.choice(STATES),
    })

# payment history: evolve days_past_due with a hazard driven by borrower risk
payments = []
for ln in loans:
    base = BAND_HAZARD[ln["fico_band"]]
    # risk multipliers from DTI, LTV, payment burden
    burden = ln["monthly_payment"] / ln["borrower_monthly_income"]
    mult = (1.0
            + 2.2*max(0, ln["dti_ratio"]-0.35)
            + 1.4*max(0, ln["ltv_ratio"]-1.0)
            + 3.0*max(0, burden-0.18))
    hazard = min(0.9, base*mult)
    dpd = 0
    for m in range(MONTHS):
        as_of = datetime.date(2025,1,1) + datetime.timedelta(days=30*m)
        # if already delinquent, chance to cure or worsen; else chance to miss
        if dpd == 0:
            missed = random.random() < hazard
            dpd = 30 if missed else 0
        else:
            r = random.random()
            if r < 0.45: dpd = 0                 # cured
            elif r < 0.80: dpd = min(120, dpd+30) # roll forward
            # else: stays same
        bal = round(ln["principal_amount"] * max(0.05, 1 - m/ (ln["term_months"])), 2)
        scheduled = ln["monthly_payment"]
        actual = 0.0 if dpd>0 and random.random()<0.7 else scheduled
        payments.append({
            "loan_id": ln["loan_id"],
            "as_of_month": as_of.isoformat(),
            "scheduled_payment": scheduled,
            "actual_payment": round(actual,2),
            "outstanding_balance": bal,
            "days_past_due": dpd,
            "delinquency_bucket": ("current" if dpd==0 else f"{dpd}dpd"),
        })

with open(os.path.join(OUT,"loans.csv"),"w",newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(loans[0].keys())); w.writeheader(); w.writerows(loans)
with open(os.path.join(OUT,"payments.csv"),"w",newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(payments[0].keys())); w.writeheader(); w.writerows(payments)

# quick stats for the generator's own log
any_delinq = {}
for p in payments:
    any_delinq[p["loan_id"]] = any_delinq.get(p["loan_id"], False) or (p["days_past_due"]>=30)
rate = sum(1 for v in any_delinq.values() if v)/len(any_delinq)
print(f"loans={len(loans)} payments={len(payments)}")
print(f"loans that hit 30+DPD at any point: {rate:.1%}")
print(f"wrote {OUT}/loans.csv and {OUT}/payments.csv")
