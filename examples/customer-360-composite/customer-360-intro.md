👋 **Hi! I'm your Customer 360 Assistant.** I combine billing, contract, and support SLA data for our customers — pulled live from a SQLite billing database and a support SLA metrics API — into one place. 📄📊

**💡 Try asking things like:**
- 📄 "What contract does customer `cus_0007` have?"
- 💵 "What invoices are overdue for customer `cus_0021`?"
- 🧾 "Give me a billing summary for customer `cus_0012`."
- ⏱️ "What's the SLA compliance rate for `cus_0012`?"
- 🚨 "Which customers have SLA breaches?"

**🔀 Combine both — billing and support in one answer:**
- 🧭 "Show me billing and support SLA status for customer `cus_0021`."
- ⚠️ "Which customers have both overdue invoices and SLA breaches?"

These last two pull from both the billing database and the SLA metrics API at
once and merge the results — ask a "full picture" style question and you'll
see both sources show up side by side.

**🧠 I can also reach into live CRM data** (customer health, opportunities,
support tickets, churn modeling) via a connected MCP tool. Try combining all
three:
- 📊 "Give me a full risk profile for `cus_0021`: contract status, SLA compliance, and current churn probability."
- 🚩 "Which Enterprise customers have overdue invoices *and* SLA breaches — and how healthy are they in the CRM?"
- 🔗 "Find the customer with the most SLA breaches, then check their health score and simulate their churn risk if we lose them."
- 🧑‍💼 "Which sales rep is managing the most at-risk accounts — overdue invoices, SLA breaches, and low seat utilization?"
- 📋 "Build a renewal-save account plan for `cus_0034` using their contract terms, SLA history, and open support tickets."

These pull billing, SLA, and live CRM data together into one answer — the
kind of question no single source could fully answer on its own.
