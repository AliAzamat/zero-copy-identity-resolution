"""The three source systems, loaded in place.

These are read-only views over the raw tables. Nothing here copies data into a
new store: DuckDB reads the parquet files where they sit, which is the whole
architectural claim being demonstrated. If a later stage needs a materialized
table, it must be DERIVED and reproducible, never a duplicate of a source.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

DATA = Path(__file__).parent.parent / "data"


def connect() -> duckdb.DuckDBPyConnection:
    """Open a connection with the three sources registered as views."""
    con = duckdb.connect(database=":memory:")

    # Views, not tables. `CREATE VIEW ... SELECT * FROM read_parquet(...)`
    # leaves the bytes on disk and reads them per query. A CREATE TABLE here
    # would copy the source into the engine, which is exactly the pattern this
    # project exists to avoid.
    con.execute(f"""
        CREATE VIEW crm AS SELECT * FROM read_parquet('{DATA}/crm.parquet');
        CREATE VIEW web AS SELECT * FROM read_parquet('{DATA}/web.parquet');
        CREATE VIEW support AS SELECT * FROM read_parquet('{DATA}/support.parquet');
    """)
    return con


SOURCE_SCHEMAS = {
    "crm": ["account_id", "full_name", "email", "phone", "company", "updated_at"],
    "web": ["cookie_id", "signup_email", "display_name", "last_seen_at"],
    "support": ["ticket_id", "requester_email", "requester_name", "created_at"],
}


def sample_rows() -> dict[str, list[dict]]:
    """Illustrative rows showing the disagreements this project must resolve."""
    return {
        "crm": [
            {"account_id": "A-1001", "full_name": "Robert Chen",
             "email": "robert.chen@northwind.example", "phone": "+1-415-555-0142",
             "company": "Northwind", "updated_at": "2026-08-02"},
        ],
        "web": [
            # Same human. Nickname, plus-addressed email, different system.
            {"cookie_id": "ck_9f2a", "signup_email": "bob.chen+news@northwind.example",
             "display_name": "Bob Chen", "last_seen_at": "2026-09-14"},
        ],
        "support": [
            # Same human again. Name typed by the person, email casing differs.
            {"ticket_id": "T-5521", "requester_email": "Robert.Chen@Northwind.Example",
             "requester_name": "rob chen", "created_at": "2026-09-01"},
        ],
    }
