#!/usr/bin/env python3
"""Generate billing.db — contracts, invoices, and payments for the Customer 360 example.

Customer IDs and names are hardcoded below, copied once from
examples/mcp-server/src/data.js (faker.seed(4242)), so this SQLite database
stays referentially locked to the MCP business server's customer data
without any runtime coupling between the two systems.
"""

import argparse
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

# customer_id, customer_name, segment (copied from examples/mcp-server/src/data.js)
CUSTOMERS = [
    ("cus_0001", "Cole, Aufderhar and Nienow", "SMB"),
    ("cus_0002", "Feeney - Murphy", "Mid-Market"),
    ("cus_0003", "Reilly and Sons", "SMB"),
    ("cus_0004", "Lind, Hermiston and Luettgen", "Mid-Market"),
    ("cus_0005", "Abshire, Bauch and Graham", "SMB"),
    ("cus_0006", "Deckow - Robel", "Enterprise"),
    ("cus_0007", "Mueller, Volkman and Bernier", "Enterprise"),
    ("cus_0008", "Spencer LLC", "SMB"),
    ("cus_0009", "Dare and Sons", "Mid-Market"),
    ("cus_0010", "O'Kon - Jacobi-O'Keefe", "SMB"),
    ("cus_0011", "Toy - Moen", "Enterprise"),
    ("cus_0012", "Paucek and Sons", "SMB"),
    ("cus_0013", "Herzog and Sons", "Enterprise"),
    ("cus_0014", "Spinka, Russel and Crona-Towne", "SMB"),
    ("cus_0015", "Abbott, Waelchi and Bayer", "SMB"),
    ("cus_0016", "Abernathy and Sons", "Mid-Market"),
    ("cus_0017", "Koss - Schaefer", "SMB"),
    ("cus_0018", "Deckow Group", "Enterprise"),
    ("cus_0019", "Kuhlman, Jones and Lowe", "Mid-Market"),
    ("cus_0020", "Pollich, Mitchell and Feest", "Enterprise"),
    ("cus_0021", "Ziemann - Nitzsche", "SMB"),
    ("cus_0022", "Sawayn-Wunsch Inc", "Mid-Market"),
    ("cus_0023", "Lakin, Bauch and Hills", "SMB"),
    ("cus_0024", "Moen LLC", "SMB"),
    ("cus_0025", "McLaughlin Inc", "Enterprise"),
    ("cus_0026", "Hodkiewicz Inc", "SMB"),
    ("cus_0027", "Williamson Group", "Enterprise"),
    ("cus_0028", "Thiel - Lindgren", "Enterprise"),
    ("cus_0029", "Heller Inc", "SMB"),
    ("cus_0030", "Cassin, Romaguera and Herzog", "Enterprise"),
    ("cus_0031", "Graham LLC", "Mid-Market"),
    ("cus_0032", "Adams and Sons", "SMB"),
    ("cus_0033", "Russel - Parisian", "Mid-Market"),
    ("cus_0034", "Dietrich Inc", "Enterprise"),
    ("cus_0035", "Gleichner, Morar and Bauch", "Mid-Market"),
    ("cus_0036", "Nader-Stamm Inc", "Mid-Market"),
]

PLAN_TIER_BY_SEGMENT = {"SMB": "Starter", "Mid-Market": "Growth", "Enterprise": "Enterprise"}
SEATS_BY_SEGMENT = {"SMB": (50, 200), "Mid-Market": (200, 800), "Enterprise": (800, 5000)}
CONTRACT_VALUE_BY_SEGMENT = {"SMB": (12000, 85000), "Mid-Market": (72000, 260000), "Enterprise": (240000, 1400000)}

TODAY = date(2026, 8, 1)


def daterange_str(base: date, days_offset: int) -> str:
    return (base + timedelta(days=days_offset)).isoformat()


def build_schema(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).with_name("billing_schema.sql")
    conn.executescript(schema_path.read_text())


def generate(conn: sqlite3.Connection, seed: int) -> None:
    rng = random.Random(seed)
    cur = conn.cursor()

    cur.executemany(
        "INSERT OR IGNORE INTO customers (customer_id, customer_name) VALUES (?, ?)",
        [(cid, name) for cid, name, _segment in CUSTOMERS],
    )

    contract_seq = 1
    invoice_seq = 1
    payment_seq = 1

    for customer_id, _name, segment in CUSTOMERS:
        plan_tier = PLAN_TIER_BY_SEGMENT[segment]
        seats = rng.randint(*SEATS_BY_SEGMENT[segment])
        contract_value = round(rng.uniform(*CONTRACT_VALUE_BY_SEGMENT[segment]), 2)
        billing_cycle = rng.choice(["monthly", "annual"])
        start_date = daterange_str(TODAY, -rng.randint(90, 730))
        end_date = daterange_str(TODAY, rng.randint(30, 400))
        status = rng.choices(["active", "pending_renewal", "expired"], weights=[7, 2, 1])[0]
        auto_renew = 1 if rng.random() < 0.7 else 0

        contract_id = f"con_{contract_seq:04d}"
        contract_seq += 1
        cur.execute(
            """INSERT OR IGNORE INTO contracts
               (contract_id, customer_id, plan_tier, seats, start_date, end_date,
                billing_cycle, auto_renew, contract_value, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (contract_id, customer_id, plan_tier, seats, start_date, end_date,
             billing_cycle, auto_renew, contract_value, status),
        )

        invoice_count = rng.randint(2, 4)
        for i in range(invoice_count):
            invoice_amount = round(contract_value / (12 if billing_cycle == "monthly" else 1) *
                                    (1 if billing_cycle == "annual" else rng.randint(1, 3)), 2)
            invoice_date = daterange_str(TODAY, -rng.randint(5, 300))
            due_date = daterange_str(date.fromisoformat(invoice_date), 30)
            invoice_status = rng.choices(["paid", "open", "overdue", "void"], weights=[6, 2, 2, 1])[0]

            invoice_id = f"inv_{invoice_seq:04d}"
            invoice_seq += 1
            cur.execute(
                """INSERT OR IGNORE INTO invoices
                   (invoice_id, contract_id, customer_id, invoice_date, due_date,
                    amount, currency, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (invoice_id, contract_id, customer_id, invoice_date, due_date,
                 invoice_amount, "USD", invoice_status),
            )

            if invoice_status == "paid":
                payment_date = daterange_str(date.fromisoformat(due_date), -rng.randint(0, 20))
                payment_id = f"pay_{payment_seq:04d}"
                payment_seq += 1
                cur.execute(
                    """INSERT OR IGNORE INTO payments
                       (payment_id, invoice_id, customer_id, payment_date, amount, method, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (payment_id, invoice_id, customer_id, payment_date, invoice_amount,
                     rng.choice(["credit_card", "ach", "wire"]), "succeeded"),
                )

    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(Path(__file__).with_name("billing.db")))
    parser.add_argument("--seed", type=int, default=4242)
    parser.add_argument("--force", action="store_true", help="Delete existing db file before generating")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if args.force and db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        build_schema(conn)
        generate(conn, args.seed)
    finally:
        conn.close()

    print(f"Generated {db_path}")


if __name__ == "__main__":
    main()
