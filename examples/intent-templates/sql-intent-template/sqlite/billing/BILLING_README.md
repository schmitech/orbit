# Billing & Contracts SQLite Adapter

Contracts, invoices, and payments for the same synthetic customers used by
`examples/mcp-server/` (customer IDs `cus_0001`…`cus_0036`). Part of the
Customer 360 composite example — see
`examples/customer-360-composite/README.md`.

## Generate the database

```bash
cd examples/intent-templates/sql-intent-template/sqlite/billing
python3 generate_billing_data.py --force
```

This creates `billing.db` with 36 customers, 36 contracts, ~110 invoices, and
payments for the paid ones. Customer IDs/names are hardcoded in the generator
script, copied once from `examples/mcp-server/src/data.js`, so they never
drift out of sync with the MCP business server or the SLA metrics API.

## Files

- `billing_schema.sql` — table DDL (customers, contracts, invoices, payments)
- `generate_billing_data.py` — deterministic data generator (seed `4242`)
- `billing-domain.yaml` — entity/field/relationship domain definition
- `billing-templates.yaml` — 8 intent templates (contract lookups, overdue
  invoices, payment history, billing summaries, etc.)

## Registered adapter

`intent-sql-sqlite-billing` in `config/adapters/billing-sla.yaml`.

## Try it

```
"What contract does customer cus_0007 have?"
"What invoices are overdue for customer cus_0007?"
"Give me a billing summary for customer cus_0021"
```
