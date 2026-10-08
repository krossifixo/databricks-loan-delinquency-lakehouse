# Catch Delinquency Before It Costs You
### Early intervention for auto lending, on one governed lakehouse
Audience: Chief Risk Officer (sponsor) and Collections & Risk Ops lead (owner)

*(Plain-language business deck. Built on the Databricks Executive template.)*

---

## 1. The business outcome
- We flag the current borrowers most likely to miss a payment next month, and hand collections a ranked call list so they reach out before the account goes late.
- What you feel: fewer accounts charged off as losses, and a collections team spending its time where it pays off.
- Nothing changes in how you approve or book loans.

---

## 2. The problem, in your terms
- Collections only works an account after it is already late, when it is harder and more expensive to bring the borrower current.
- The team can only make so many calls a month, and today that effort is spread evenly instead of aimed at the riskiest accounts.
- The damage shows up as more accounts slipping from on-time to late, more of those going all the way to write-off, and higher loss totals, the numbers your risk leaders report every quarter.
- On this sample book of 5,000 loans (about $134.6M owed), roughly 3 in every 100 on-time borrowers fall a month behind each cycle. That is the leak we close.

---

## 3. One connected system, not six tools
- Raw loan and payment files are automatically cleaned and quality-checked (Lakeflow).
- Every table is governed in one place, with clear ownership, access control, and a full audit trail (Unity Catalog).
- A model scores each current borrower's risk, and plain-language notes explain the day's list (machine learning and generative AI).
- The scored call list and case notes live in a fast operational database the app reads and writes instantly (Lakebase).
- Anyone can ask questions in plain English, with no spreadsheets or code (Genie).
- It all comes together in one collections web app: the ranked list, the daily briefing, a built-in question assistant, and one-click case creation.

---

## 4. Does it actually work? Yes
- The model reliably separates borrowers who will fall behind from those who will not, ranking the right one as higher risk about 3 times out of 4.
- Risk lines up with credit scores exactly as you would expect: the weakest-credit borrowers are more than 20 times likelier to fall behind than the strongest (about 11% versus 0.5%).
- Focus on the riskiest 5% the model flags and you reach borrowers about 3.7 times likelier to actually fall behind than a typical borrower, so each call does far more work.
- Today's list: 153 high-risk loans worth $4.4M, each with a plain-language briefing and a recommended next step.

---

## 5. What it is worth, in your numbers
- Your call list hits the mark about 11.8% of the time, versus 3.2% working accounts at random, roughly 3.7 times more productive outreach.
- Each cycle the team works the 153 highest-risk loans first, instead of waiting for them to go late.
- An illustration to validate with your own data: if early outreach saves just a quarter of the $4.4M at-risk balance, and you would otherwise recover a little under half of a written-off loan, that is roughly $0.6M in losses avoided every cycle, growing with the size of your book.
- No added cost to approve or book loans. This runs on data you already have.

---

## 6. Why it matters to the Chief Risk Officer
- Fewer losses and lower reserves by moving collections from reacting to predicting.
- One governed system from raw data to finished app, with the audit trail, access controls, and ownership your risk and audit teams require.
- The same approach extends to pricing, credit-line decisions, and recovery, on tools you already run.

---

## 7. Why it matters to the collections lead
- A ranked daily call list instead of a flat spreadsheet, so the team works the riskiest dollars first.
- A plain-language briefing that explains the day's list and suggests the next action.
- A built-in assistant that answers questions in plain English, right inside the app, with no switching tools and no code.
- Case handling built in: open and assign a case in one click, saved instantly and available to everyone who needs it.

---

## 8. Why Databricks
- The hand-offs between data prep, governance, modeling, serving, and the app are where most projects break. Here they are one connected system.
- One platform, one set of security rules, one trusted copy of the data.
- From a raw file to a business decision with no copying data between bolt-on tools, faster to launch and cheaper to run.

---

## 9. Next steps
- Run the model against your own anonymized history and confirm the results on your real write-offs.
- Agree who gets contacted, and with what offer, for the highest-risk tier.
- Pilot with the collections team for one cycle, and measure the drop in accounts going late and the gain in successful outreach.
- Extend the same approach to the next risk problem.

*All figures here come from a synthetic sample built for this prototype; the dollar impact is illustrative and should be validated against your actuals.*
