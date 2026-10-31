from datetime import date, datetime, timedelta

import inventory as inv
from database import reset_db, get_connection

TODAY = date.today()


def months(n, plus_days=0):
    return (inv.add_months(TODAY, n) + timedelta(days=plus_days)).isoformat()


def days(n):
    return (TODAY + timedelta(days=n)).isoformat()


def hrs_ago(h):
    return (datetime.now() - timedelta(hours=h)).isoformat(timespec="seconds")


NORMAL = [(72, 4.6), (48, 5.1), (24, 4.8)]

# City General needs 6 months, so this expires 5 days short of its cutoff
SHORT_FOR_CITY_GENERAL = (inv.add_months(TODAY, 6) - timedelta(days=5)).isoformat()

# (id, product, type, storage, qty, expiry, temps[(hours_ago, temp)], final_action)
BATCHES = [
    ("PCM-2601", "Paracetamol 500mg Tablets", "Medicine", inv.AMBIENT, 500, months(14), [], "release"),
    ("PCM-2602", "Paracetamol 500mg Tablets", "Medicine", inv.AMBIENT, 300, months(7), [], "release"),
    ("PCM-2603", "Paracetamol 500mg Tablets", "Medicine", inv.AMBIENT, 400, months(18), [], "pending"),  # unreleased

    ("RL-2601", "Ringer Lactate IV 500ml", "IV Fluid", inv.AMBIENT, 200, months(10), [], "release"),
    ("RL-2602", "Ringer Lactate IV 500ml", "IV Fluid", inv.AMBIENT, 150, days(-10), [], "released_then_expired"),
    ("RL-2603", "Ringer Lactate IV 500ml", "IV Fluid", inv.AMBIENT, 250, SHORT_FOR_CITY_GENERAL, [], "release"),

    ("INS-2601", "Insulin Glargine 100IU/ml", "Medicine", inv.COLD, 100, months(9), NORMAL, "release"),
    # excursion at 9.6C, then back to normal. Must STAY quarantined.
    ("INS-2602", "Insulin Glargine 100IU/ml", "Medicine", inv.COLD, 80, months(12),
     [(72, 4.8), (48, 9.6), (24, 5.0)], "none"),
    ("INS-2603", "Insulin Glargine 100IU/ml", "Medicine", inv.COLD, 120, months(15), NORMAL, "release"),

    # readings exactly on 2.0 and 8.0 are still IN range
    ("NS1-2601", "Dengue NS1 Test Kit", "Test Kit", inv.COLD, 200, months(5),
     [(72, 2.0), (48, 8.0), (24, 6.5)], "release"),
    ("NS1-2602", "Dengue NS1 Test Kit", "Test Kit", inv.COLD, 200, months(9), NORMAL, "release"),

    ("CTX-2601", "Ceftriaxone 1g Injection", "Medicine", inv.AMBIENT, 300, months(16), [], "release"),
    ("CTX-2602", "Ceftriaxone 1g Injection", "Medicine", inv.AMBIENT, 100, days(100), [], "release"),
    ("CTX-2603", "Ceftriaxone 1g Injection", "Medicine", inv.AMBIENT, 60, months(12), [], "reject"),
]

HOSPITALS = [
    ("City General Hospital", 6),
    ("Sunrise Children's Hospital", 8),
    ("Rural District Hospital", 3),
    ("Metro Super Specialty Hospital", 12),
]


def seed():
    reset_db()

    for name, m in HOSPITALS:
        inv.add_hospital(name, m)

    for bid, product, ptype, storage, qty, expiry, temps, action in BATCHES:
        inv.add_batch(bid, product, ptype, storage, qty, expiry, allow_expired=True)
        for h, t in temps:
            inv.record_temperature(bid, t, hrs_ago(h))

        if action == "release":
            inv.review_batch(bid, "Approved", "QA Team", "Passed QC inspection; storage log reviewed")
        elif action == "reject":
            inv.review_batch(bid, "Rejected", "QA Team", "Failed visual inspection: particulate in vials")
        elif action == "released_then_expired":
            # Simulates a batch released months ago that has since passed expiry.
            # (review_batch correctly refuses to release an expired batch.)
            conn = get_connection()
            conn.execute("UPDATE batches SET status = 'Released' WHERE batch_id = ?", (bid,))
            conn.close()

    print("Seeded OK\n")
    print(f"{'BATCH':10} {'PRODUCT':28} {'QTY':>4}  {'EXPIRY':10}  {'STORAGE':8} STATUS")
    for b in inv.get_all_batches():
        print(f"{b['batch_id']:10} {b['product_name'][:28]:28} {b['quantity']:>4}  "
              f"{b['expiry_date']:10}  {b['storage_condition']:8} {b['status']}")


if __name__ == "__main__":
    seed()