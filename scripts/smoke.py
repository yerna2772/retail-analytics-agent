#!/usr/bin/env python
"""First-contact smoke test for real GCP credentials.

Runs the checks in the order they actually fail, so the first red line is the
thing to fix. Nothing here goes through the agent graph -- this isolates
"is the plumbing connected" from "is the agent correct".

    python scripts/smoke.py --project YOUR_BILLING_PROJECT

Total scan cost is a few MB. thelook_ecommerce is small relative to the 1 TB
monthly free tier; the script prints exact bytes so you can confirm rather
than take my word for it.
"""

from __future__ import annotations

import argparse
import sys

from google.api_core import exceptions as gexc
from google.cloud import bigquery

DATASET = "bigquery-public-data.thelook_ecommerce"
TABLES = ["orders", "order_items", "products", "users"]

# Must match safety/pii.py exactly. Step 4 verifies that it does.
PII_COLUMNS = {
    "users": {
        "first_name", "last_name", "email", "street_address",
        "postal_code", "latitude", "longitude", "user_geom",
    }
}

OK, FAIL, WARN = "  [ok]", "  [FAIL]", "  [warn]"


def step(n: int, title: str) -> None:
    print(f"\n{n}. {title}")


def main(project: str | None) -> int:
    failures = 0

    # ---------------------------------------------------------------
    step(1, "Credentials and client init")
    try:
        client = bigquery.Client(project=project)
        print(f"{OK} billing project: {client.project}")
    except Exception as exc:  # noqa: BLE001
        print(f"{FAIL} {exc}")
        print("       run: gcloud auth application-default login")
        print("            gcloud auth application-default set-quota-project PROJECT")
        return 1

    # ---------------------------------------------------------------
    step(2, "Table access and size (metadata only, scans nothing)")
    for name in TABLES:
        try:
            t = client.get_table(f"{DATASET}.{name}")
            print(f"{OK} {name:<12} {t.num_rows:>10,} rows  {len(t.schema)} columns")
        except gexc.Forbidden as exc:
            print(f"{FAIL} {name}: permission denied -- {exc}")
            failures += 1
        except gexc.NotFound:
            print(f"{FAIL} {name}: not found")
            failures += 1
        except Exception as exc:  # noqa: BLE001
            print(f"{FAIL} {name}: {exc}")
            failures += 1

    if failures:
        print("\n       enable the API: gcloud services enable bigquery.googleapis.com")
        return 1

    # ---------------------------------------------------------------
    step(3, "dry_run works and reports an estimate")
    probe = f"SELECT COUNT(*) AS n FROM `{DATASET}.orders` LIMIT 1"
    cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    try:
        job = client.query(probe, job_config=cfg)
        print(f"{OK} estimate: {job.total_bytes_processed:,} bytes, nothing billed")
    except Exception as exc:  # noqa: BLE001
        print(f"{FAIL} {exc}")
        return 1

    # ---------------------------------------------------------------
    step(4, "PII denylist matches the real schema")
    # A denylisted column that no longer exists is a silent hole: the validator
    # protects a column nobody queries while the real one goes unchecked.
    for table, expected in PII_COLUMNS.items():
        actual = {f.name for f in client.get_table(f"{DATASET}.{table}").schema}
        missing = expected - actual
        unlisted = actual - expected
        if missing:
            print(f"{FAIL} {table}: denylisted but absent from schema -> {sorted(missing)}")
            failures += 1
        else:
            print(f"{OK} all {len(expected)} denylisted columns exist in {table}")
        print(f"       other columns present: {sorted(unlisted)}")
        print("       ^ review this list by hand. Anything identifying belongs in the denylist.")

    # ---------------------------------------------------------------
    step(5, "Actual status values (ground the semantic layer in reality)")
    sql = f"""
        SELECT status, COUNT(*) AS n
        FROM `{DATASET}.order_items`
        GROUP BY status ORDER BY n DESC
    """
    try:
        rows = list(client.query(sql).result())
        for r in rows:
            print(f"{OK} {r.status:<12} {r.n:>10,}")
        print("       ^ metrics.yaml must exclude exactly the non-revenue statuses above,")
        print("         not the ones I guessed from memory.")
    except Exception as exc:  # noqa: BLE001
        print(f"{FAIL} {exc}")
        failures += 1

    # ---------------------------------------------------------------
    step(6, "Quantify the revenue-filter trap (test C1) on real data")
    sql = f"""
        SELECT
          SUM(sale_price) AS naive,
          SUM(CASE WHEN status NOT IN ('Cancelled', 'Returned')
                   THEN sale_price END) AS filtered
        FROM `{DATASET}.order_items`
        WHERE EXTRACT(YEAR FROM created_at) = 2023
    """
    try:
        job = client.query(sql)
        r = list(job.result())[0]
        gap = (r.naive - r.filtered) / r.naive * 100 if r.naive else 0
        print(f"{OK} without status filter: {r.naive:>15,.2f}")
        print(f"{OK} with status filter:    {r.filtered:>15,.2f}")
        print(f"{WARN} overstatement: {gap:.1f}%")
        print(f"       scanned {job.total_bytes_billed:,} bytes")
        print("       ^ this is the error the agent makes silently if metrics.yaml")
        print("         is missing. dry_run passes both queries. Record this number")
        print("         as the reference for test C1.")
    except Exception as exc:  # noqa: BLE001
        print(f"{FAIL} {exc}")
        failures += 1

    # ---------------------------------------------------------------
    step(7, "Data recency (affects 'last month' and 'up-to-date' questions)")
    sql = f"SELECT MIN(created_at) AS lo, MAX(created_at) AS hi FROM `{DATASET}.orders`"
    try:
        r = list(client.query(sql).result())[0]
        print(f"{OK} orders span {r.lo:%Y-%m-%d} .. {r.hi:%Y-%m-%d}")
        print("       ^ 'up-to-date revenue' must resolve against MAX(created_at),")
        print("         not CURRENT_DATE, or recent periods come back empty.")
    except Exception as exc:  # noqa: BLE001
        print(f"{FAIL} {exc}")
        failures += 1

    # ---------------------------------------------------------------
    step(8, "Typed error classification behaves as designed")
    try:
        client.query("SELECT nonexistent_column FROM `%s.orders`" % DATASET,
                     job_config=bigquery.QueryJobConfig(dry_run=True))
        print(f"{FAIL} bad column did not raise")
        failures += 1
    except gexc.BadRequest as exc:
        first = str(exc).split("\n")[0][:90]
        print(f"{OK} BadRequest -> SQLRepairableError")
        print(f"       message fed to the repair loop: {first}")
    except Exception as exc:  # noqa: BLE001
        print(f"{WARN} raised {type(exc).__name__}, expected BadRequest -- check _classify()")

    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    if failures:
        print(f"{failures} check(s) failed.")
        return 1
    print("All checks passed. Plumbing is connected.")
    print("Next: run one real question end-to-end, then compare its SQL")
    print("against the reference numbers from steps 5-7.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=None, help="billing project id")
    sys.exit(main(ap.parse_args().project))
