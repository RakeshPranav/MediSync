import os
import sys
import traceback
from datetime import date, timedelta

import database
from database import reset_db
import inventory as inv

database.DB_PATH = os.path.join("database", "test_inventory.db")   # never touches real data


# ---------- helpers ----------
def fresh():
    reset_db()


def mk(batch_id, product="Paracetamol", qty=100, expiry_months=12, storage=inv.AMBIENT,
       temps=(), approve=True, expiry=None):
    exp = expiry or inv.add_months(date.today(), expiry_months).isoformat()
    inv.add_batch(batch_id, product, "Medicine", storage, qty, exp)
    for t in temps:
        inv.record_temperature(batch_id, t)
    if approve:
        inv.review_batch(batch_id, "Approved", "QA", "Passed all checks fine")
    return batch_id


def row(batch_id):
    return next(b for b in inv.get_all_batches() if b["batch_id"] == batch_id)


def expect_error(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except inv.InventoryError as e:
        return str(e).lower()
    raise AssertionError("expected InventoryError, but none was raised")


# ---------- tests ----------
def test_add_months_calendar_math():
    assert inv.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert inv.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)     # leap year
    assert inv.add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)    # year rollover
    assert inv.add_months(date(2026, 10, 31), 6) == date(2027, 4, 30)


def test_shelf_life_boundary():
    t = date(2026, 10, 31)
    assert inv.required_expiry_cutoff(6, t) == date(2027, 4, 30)
    assert inv.is_shelf_life_valid("2027-04-30", 6, t) is True    # exactly on cutoff passes
    assert inv.is_shelf_life_valid("2027-04-29", 6, t) is False   # one day short fails


def test_new_batch_starts_pending_qc():
    fresh()
    mk("A1", approve=False)
    assert row("A1")["status"] == "Pending QC"


def test_temperature_boundaries():
    fresh()
    for i, t in enumerate((2.0, 8.0, 5.0)):
        mk(f"OK{i}", storage=inv.COLD, temps=[t], approve=False)
        assert row(f"OK{i}")["status"] == "Pending QC", f"{t} should be normal"
    for i, t in enumerate((1.9, 8.1, 1, 9)):
        mk(f"BAD{i}", storage=inv.COLD, temps=[t], approve=False)
        assert row(f"BAD{i}")["status"] == "Quarantined", f"{t} should be an excursion"


def test_ambient_batch_not_quarantined_by_warm_reading():
    fresh()
    mk("AMB", storage=inv.AMBIENT, temps=[35], approve=False)
    assert row("AMB")["status"] == "Pending QC"


def test_excursion_on_released_batch_quarantines_it():
    fresh()
    mk("R1", storage=inv.COLD, temps=[5])
    assert row("R1")["status"] == "Released"
    inv.record_temperature("R1", 9.5)
    assert row("R1")["status"] == "Quarantined"
    assert inv.get_quality_records("R1")[-1]["decision"] == "Auto-Quarantined"


def test_handoff_scenario_fefo_with_quarantine_release():
    fresh()
    hid = inv.add_hospital("Apollo Hospital", 6)
    mk("BATCH101", qty=100, expiry_months=12, storage=inv.COLD, temps=[5])
    mk("BATCH102", qty=50, expiry_months=8, storage=inv.COLD, temps=[4])
    mk("BATCH103", qty=80, expiry_months=4, storage=inv.COLD, temps=[5])
    mk("BATCH104", qty=60, expiry_months=10, storage=inv.COLD, temps=[9], approve=False)

    assert row("BATCH104")["status"] == "Quarantined"
    inv.record_temperature("BATCH104", 5)                      # back to normal...
    assert row("BATCH104")["status"] == "Quarantined"          # ...must NOT auto-release

    # Before QA: only 101 + 102 are eligible = 150 units, so 151 must fail with NOTHING deducted
    r = inv.dispatch_order(hid, "Paracetamol", 151)
    assert r["success"] is False and r["eligible_available"] == 150
    assert row("BATCH101")["quantity"] == 100 and row("BATCH102")["quantity"] == 50

    inv.review_batch("BATCH104", "Approved", "QA Lead",
                     "Reviewed full excursion history; product stability confirmed")
    r = inv.dispatch_order(hid, "Paracetamol", 120)
    assert r["success"] and r["status"] == "FULL"
    got = [(a["batch_id"], a["quantity"]) for a in r["allocations"]]
    assert got == [("BATCH102", 50), ("BATCH104", 60), ("BATCH101", 10)], got
    assert "BATCH103" in [s["batch_id"] for s in r["skipped"]]      # 4 months < 6

    assert row("BATCH102")["quantity"] == 0
    assert row("BATCH104")["quantity"] == 0
    assert row("BATCH101")["quantity"] == 90
    assert len(inv.get_dispatch_history()) == 3
    decisions = [q["decision"] for q in inv.get_quality_records("BATCH104")]
    assert decisions == ["Auto-Quarantined", "Approved"], decisions


def test_unsafe_stock_is_never_shipped():
    fresh()
    hid = inv.add_hospital("H", 3)
    mk("GOOD", "P", qty=10)
    mk("PEND", "P", qty=10, approve=False)
    mk("QUAR", "P", qty=10, storage=inv.COLD, temps=[12], approve=False)
    mk("REJ", "P", qty=10, approve=False)
    inv.review_batch("REJ", "Rejected", "QA", "Failed inspection badly")
    inv.add_batch("OLD", "P", "Medicine", inv.AMBIENT, 10,
                  (date.today() - timedelta(days=3)).isoformat(), allow_expired=True)
    r = inv.dispatch_order(hid, "P", 10)
    assert [a["batch_id"] for a in r["allocations"]] == ["GOOD"]
    reasons = {s["batch_id"]: s["reason"].lower() for s in r["skipped"]}
    assert "pending" in reasons["PEND"]
    assert "quarantined" in reasons["QUAR"]
    assert "rejected" in reasons["REJ"]


def test_insufficient_stock_all_or_nothing():
    fresh()
    hid = inv.add_hospital("H", 3)
    mk("S1", "P", qty=100)
    r = inv.dispatch_order(hid, "P", 101)
    assert r["success"] is False and r["eligible_available"] == 100
    assert row("S1")["quantity"] == 100
    assert inv.get_dispatch_history() == []


def test_partial_only_when_allowed():
    fresh()
    hid = inv.add_hospital("H", 3)
    mk("S1", "P", qty=100)
    r = inv.dispatch_order(hid, "P", 130, allow_partial=True)
    assert r["success"] and r["status"] == "PARTIAL" and r["shortfall"] == 30
    assert row("S1")["quantity"] == 0


def test_shelf_life_differs_per_hospital():
    fresh()
    a = inv.add_hospital("Needs6", 6)
    b = inv.add_hospital("Needs8", 8)
    mk("D1", "Diff", qty=100, expiry_months=7)
    assert inv.dispatch_order(a, "Diff", 10)["success"] is True
    r = inv.dispatch_order(b, "Diff", 10)
    assert r["success"] is False
    assert "short shelf life" in r["skipped"][0]["reason"].lower()


def test_batch_one_day_short_of_cutoff_is_skipped():
    fresh()
    hid = inv.add_hospital("H6", 6)
    cutoff = inv.required_expiry_cutoff(6)
    mk("BND-OK", "Boundary", qty=10, expiry=cutoff.isoformat())
    mk("BND-SHORT", "Boundary", qty=10, expiry=(cutoff - timedelta(days=1)).isoformat())
    r = inv.dispatch_order(hid, "Boundary", 10)
    assert [a["batch_id"] for a in r["allocations"]] == ["BND-OK"]
    assert "short by 1" in r["skipped"][0]["reason"].lower()


def test_fefo_tie_break_by_batch_id():
    fresh()
    hid = inv.add_hospital("H", 3)
    same = inv.add_months(date.today(), 10).isoformat()
    mk("TB-B", "Tie", qty=10, expiry=same)
    mk("TB-A", "Tie", qty=10, expiry=same)
    r = inv.dispatch_order(hid, "Tie", 15)
    assert [(a["batch_id"], a["quantity"]) for a in r["allocations"]] == [("TB-A", 10), ("TB-B", 5)]


def test_product_name_is_case_insensitive():
    fresh()
    hid = inv.add_hospital("H", 3)
    mk("C1", "Paracetamol", qty=10)
    assert inv.dispatch_order(hid, "paracetamol", 5)["success"] is True


def test_release_guards():
    fresh()
    # expired batch can't be released
    inv.add_batch("EXP", "P", "Medicine", inv.AMBIENT, 5,
                  (date.today() - timedelta(days=1)).isoformat(), allow_expired=True)
    assert "expired" in expect_error(inv.review_batch, "EXP", "Approved", "QA", "Looks fine to me")

    # cold batch with no readings = no storage proof
    mk("NOLOG", storage=inv.COLD, approve=False)
    assert "temperature" in expect_error(inv.review_batch, "NOLOG", "Approved", "QA", "Looks fine to me")

    # latest reading still out of range
    mk("HOT", storage=inv.COLD, temps=[9], approve=False)
    assert "outside" in expect_error(inv.review_batch, "HOT", "Approved", "QA", "Looks fine to me")

    # excursion history needs a real justification
    inv.record_temperature("HOT", 5)
    assert "excursion" in expect_error(inv.review_batch, "HOT", "Approved", "QA", "ok fine now")
    inv.review_batch("HOT", "Approved", "QA", "Excursion reviewed; stability data supports release")
    assert row("HOT")["status"] == "Released"

    # rejected is final, released can't be re-reviewed
    mk("REJ2", approve=False)
    inv.review_batch("REJ2", "Rejected", "QA", "Contamination found")
    assert "cannot be reviewed" in expect_error(inv.review_batch, "REJ2", "Approved", "QA", "Changed my mind")
    assert "cannot be reviewed" in expect_error(inv.review_batch, "HOT", "Approved", "QA", "Second review pass")

    # reviewer and reason are mandatory
    mk("NEEDQA", approve=False)
    assert "reviewer" in expect_error(inv.review_batch, "NEEDQA", "Approved", "  ", "Looks fine to me")
    assert "reason" in expect_error(inv.review_batch, "NEEDQA", "Approved", "QA", "")


def test_input_validation():
    fresh()
    mk("V1", approve=False)
    for bad in ("abc", 500, float("nan"), None):
        expect_error(inv.record_temperature, "V1", bad)
    assert "not found" in expect_error(inv.record_temperature, "NOPE", 5)
    assert "already exists" in expect_error(
        inv.add_batch, "V1", "P", "Medicine", inv.AMBIENT, 10,
        inv.add_months(date.today(), 5).isoformat())
    expect_error(inv.add_batch, "V2", "P", "Medicine", inv.AMBIENT, -5, "2030-01-01")
    expect_error(inv.add_batch, "V3", "P", "Medicine", inv.AMBIENT, 5, "not-a-date")
    expect_error(inv.add_batch, "V4", "P", "Vaccine", inv.AMBIENT, 5, "2030-01-01")
    expect_error(inv.add_hospital, "Bad", 0)
    hid = inv.add_hospital("Dup", 6)
    assert "already exists" in expect_error(inv.add_hospital, "Dup", 6)
    expect_error(inv.dispatch_order, 9999, "P", 5)
    expect_error(inv.dispatch_order, hid, "P", 0)
    expect_error(inv.dispatch_order, hid, "UnknownProduct", 5)


def test_batch_proof_contains_full_history():
    fresh()
    mk("PR1", storage=inv.COLD, temps=[5, 9], approve=False)
    inv.record_temperature("PR1", 5)
    proof = inv.get_batch_proof("PR1")
    assert proof["temperature_summary"]["readings"] == 3
    assert proof["temperature_summary"]["excursions"] == 1
    assert proof["temperature_summary"]["latest_in_range"] is True
    assert len(proof["quality_records"]) == 1


# ---------- runner ----------
if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)