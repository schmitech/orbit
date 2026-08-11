-- Billing & Contracts Database Schema
-- Customer IDs are shared with examples/mcp-server/src/data.js (cus_0001..cus_0036)
-- so this database can be composed with the SLA metrics HTTP API on the same
-- customer domain via ORBIT's composite intent retriever.

PRAGMA foreign_keys = ON;

-- ============================================================================
-- CUSTOMERS TABLE (reference only — full CRM record lives in the MCP server)
-- ============================================================================
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL
);

-- ============================================================================
-- CONTRACTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS contracts (
    contract_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    plan_tier TEXT NOT NULL,          -- Starter, Growth, Enterprise
    seats INTEGER,
    start_date DATE NOT NULL,
    end_date DATE,
    billing_cycle TEXT NOT NULL,      -- monthly, annual
    auto_renew BOOLEAN DEFAULT 1,
    contract_value DECIMAL(12, 2),
    status TEXT DEFAULT 'active',     -- active, expired, pending_renewal
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- ============================================================================
-- INVOICES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS invoices (
    invoice_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    currency TEXT DEFAULT 'USD',
    status TEXT DEFAULT 'open',        -- paid, open, overdue, void
    FOREIGN KEY (contract_id) REFERENCES contracts(contract_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- ============================================================================
-- PAYMENTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    payment_date DATE NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    method TEXT,                       -- credit_card, ach, wire
    status TEXT DEFAULT 'succeeded',   -- succeeded, failed, refunded
    FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- ============================================================================
-- INDEXES
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_contracts_customer ON contracts(customer_id);
CREATE INDEX IF NOT EXISTS idx_contracts_status ON contracts(status);
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_invoices_contract ON invoices(contract_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_payments_customer ON payments(customer_id);
CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments(invoice_id);
