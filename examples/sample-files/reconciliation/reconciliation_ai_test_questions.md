
# AI Financial Reconciliation Test Questions

This list includes basic, intermediate, and advanced questions you can use to evaluate reasoning and retrieval in RAG-based financial reconciliation demos using the credit card dataset.

---

## 🧾 Core Reconciliation & Matching

1. Match the February 2025 statement lines for CH-002 (USD card) to Transactions using a $1 CAD tolerance after converting at the mid-month FX rate. Which lines don’t match?
2. List Transactions in January where TxnDate and PostedDate differ by more than 2 days. Do they still match a Statement line using the fallback rule?
3. Find potential duplicates: same CardholderID, Vendor (fuzzy), Amount_CAD within $0.50, within 1 day. Show TxnIDs and your confidence.
4. Identify missing statement lines by comparing Statements and Transactions across all cardholders. List by CardholderID and Month.

---

## 💱 Currency & FX Reasoning

5. Reconcile CH-004 (EUR) for January using the mid-month rate from FX_Rates. Which Transactions fail to match due to FX rounding?
6. For multi-currency cardholders, compute the total CAD spend by category for Jan–Apr 2025 and rank the top 5 vendors.
7. Identify Transactions where the FX_to_CAD rate differs from the expected mid-month FX rate by more than 0.02.

---

## 📋 Policy & Compliance

8. Which Transactions require receipts but have ‘Receipt missing’ in Notes? Summarize by Cardholder with total CAD and count.
9. Identify Transactions over their Category policy limit. Provide recommended actions from Reconciliation_Rules (e.g., escalate or split).
10. Flag Meals over $150 and show any corresponding refunds or chargebacks that offset them.
11. Find all OverPolicyLimit transactions by GL_CostCenter and summarize total CAD and number of occurrences.

---

## 🔁 Refunds, Chargebacks & Exceptions

12. Find all negative Amount_CAD lines (Refund/Chargeback) and match them to their original vendor Transactions (same Cardholder, ±14 days). Which remain unmatched?
13. Populate the Exceptions sheet with unmatched items including Reason and ProposedAction, then summarize by Cardholder.
14. Detect vendors with recurring refunds or chargebacks, list how often and average refund percentage relative to total spend.

---

## 📄 Statement vs Ledger Gaps

15. Which Statement lines for CH-003 in February have no corresponding Transaction? Suggest whether to wait (Pending) vs. book an accrual.
16. Identify vendor name variants likely to be the same merchant (e.g., ‘UBER’, ‘UBR’, ‘UBER *TRIP’) and show how that affects reconciliation counts.
17. Highlight Statement lines that correspond to Pending Transactions and predict which are likely to post next month.

---

## 🧮 GL & Reporting

18. Produce a GL posting extract: Category → GL_Account totals in CAD for each month. Include Tax_CAD and net of refunds.
19. By Department (GL_CostCenter), what’s the CAD spend in Travel-Air vs Travel-Hotel, and how many required receipts are missing?
20. Summarize total Tax_CAD collected by category and identify any inconsistencies between tax estimates and policy applicability.

---

## 🧠 Advanced Analytical & Predictive Reasoning

21. Find Transactions tagged ‘Installment plan month 1 of 3’. Estimate the full contract cost and create a schedule across months.
22. Detect grouped statement items (e.g., rides + Stripe fees same day/vendor). Merge and re-run match — what’s the delta in unmatched count?
23. Which Pending Transactions later posted at a different amount? Show variance and whether they still matched.
24. Estimate the FX impact per department by comparing base-currency vs. converted CAD values across months.
25. Predict which Cardholders are most likely to trigger Exceptions next month based on their past reconciliation patterns and policy breaches.
26. Rank vendors by total CAD exposure, number of refunds, and policy limit breaches.
27. Detect seasonality or recurring transaction patterns per Cardholder (e.g., monthly subscriptions or travel spikes).
28. Generate a compliance risk score for each Cardholder based on count of missing receipts, over-limit expenses, and refunds.

---

## 🧪 Cross-Sheet Reasoning

29. Use Reconciliation_Rules and Vendor_Rules to auto-categorize new Transactions with unknown vendors and propose a likely match.
30. Combine GL_Map and Category data to produce a fully balanced journal entry summary, ensuring total debits = credits in CAD.
31. Rebuild a reconciliation matrix by Cardholder showing: total Transactions, matched, unmatched, pending, refunds, duplicates.

---

**Tip:** For demo scenarios, use progressively harder questions — start from matching and FX reasoning, then move into exception handling and predictive pattern discovery.

---

**Dataset:** credit_card_reconciliation_complex_large.xlsx  
**Date Range:** Jan–Apr 2025  
**Base Currency:** CAD  
**Cardholders:** 10  
**Transactions:** ~450  
**Statements:** ~290  

