
import sqlite3
import calendar
from datetime import date
from database import get_connection


# -----------------------------------------
# 1. DATE AND SHELF-LIFE UTILITIES
# -----------------------------------------

def add_months(input_date, months):
    """Add calendar months while handling month-end dates."""

    month_index = input_date.month - 1 + months
    year = input_date.year + month_index // 12
    month = month_index % 12 + 1

    day = min(
        input_date.day,
        calendar.monthrange(year, month)[1]
    )

    return date(year, month, day)


def is_shelf_life_valid(expiry_date, minimum_months=6):
    """Check whether a batch meets minimum shelf life."""

    expiry = date.fromisoformat(expiry_date)
    required_date = add_months(date.today(), minimum_months)

    return expiry >= required_date


# -----------------------------------------
# 2. ADD HOSPITAL
# -----------------------------------------

def add_hospital(name, minimum_months=6):

    if minimum_months < 0:
        raise ValueError("Minimum shelf life cannot be negative")

    conn = get_connection()

    cursor = conn.execute("""
        INSERT INTO hospitals
        (hospital_name, min_shelf_life_months)
        VALUES (?, ?)
    """, (name, minimum_months))

    hospital_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return hospital_id


# -----------------------------------------
# 3. ADD MEDICAL BATCH
# -----------------------------------------

def add_batch(batch_id, product_name, product_type,
              quantity, expiry_date, temperature=None):

    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero")

    date.fromisoformat(expiry_date)

    status = "Released"

    if temperature is not None:
        if not 2 <= temperature <= 8:
            status = "Quarantined"

    conn = get_connection()

    try:
        conn.execute("""
            INSERT INTO batches
            (batch_id, product_name, product_type,
             quantity, expiry_date, status, current_temp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            batch_id,
            product_name,
            product_type,
            quantity,
            expiry_date,
            status,
            temperature
        ))

        # Store initial temperature if provided
        if temperature is not None:
            conn.execute("""
                INSERT INTO temperature_logs
                (batch_id, temperature)
                VALUES (?, ?)
            """, (batch_id, temperature))

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return status


# -----------------------------------------
# 4. VIEW ALL BATCHES
# -----------------------------------------

def get_all_batches():

    conn = get_connection()

    batches = conn.execute("""
        SELECT *
        FROM batches
        ORDER BY expiry_date ASC
    """).fetchall()

    conn.close()

    return [dict(batch) for batch in batches]


# -----------------------------------------
# 5. TEMPERATURE MONITORING
# -----------------------------------------

def record_temperature(batch_id, temperature):

    conn = get_connection()

    try:
        batch = conn.execute("""
            SELECT status FROM batches
            WHERE batch_id = ?
        """, (batch_id,)).fetchone()

        if batch is None:
            raise ValueError("Batch does not exist")

        conn.execute("""
            INSERT INTO temperature_logs
            (batch_id, temperature)
            VALUES (?, ?)
        """, (batch_id, temperature))

        new_status = batch["status"]

        # Temperature excursion detected
        if not 2 <= temperature <= 8:

            if new_status != "Rejected":
                new_status = "Quarantined"

        # Update latest temperature.
        # Normal temperature never automatically releases stock.
        conn.execute("""
            UPDATE batches
            SET current_temp = ?, status = ?
            WHERE batch_id = ?
        """, (temperature, new_status, batch_id))

        conn.commit()

        return new_status

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# -----------------------------------------
# 6. QUALITY TEAM REVIEW
# -----------------------------------------

def review_batch(batch_id, decision, reason):

    decision = decision.upper()

    if decision not in ("APPROVED", "REJECTED"):
        raise ValueError("Decision must be APPROVED or REJECTED")

    conn = get_connection()

    try:
        batch = conn.execute("""
            SELECT status, current_temp
            FROM batches
            WHERE batch_id = ?
        """, (batch_id,)).fetchone()

        if batch is None:
            raise ValueError("Batch does not exist")

        if batch["status"] != "Quarantined":
            raise ValueError("Batch is not quarantined")

        if decision == "APPROVED":

            if batch["current_temp"] is None:
                raise ValueError("Temperature data is missing")

            if not 2 <= batch["current_temp"] <= 8:
                raise ValueError(
                    "Cannot approve: latest temperature is outside 2-8°C"
                )

            new_status = "Released"

        else:
            new_status = "Rejected"

        conn.execute("""
            UPDATE batches
            SET status = ?
            WHERE batch_id = ?
        """, (new_status, batch_id))

        conn.execute("""
            INSERT INTO quality_records
            (batch_id, reason, decision)
            VALUES (?, ?, ?)
        """, (batch_id, reason, decision))

        conn.commit()

        return new_status

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# -----------------------------------------
# 7. FEFO DISPATCH
# -----------------------------------------

def dispatch_order(hospital_id, product_name, required_quantity):

    if required_quantity <= 0:
        raise ValueError("Required quantity must be positive")

    conn = get_connection()

    try:
        # Prevent concurrent dispatches from overselling stock
        conn.execute("BEGIN IMMEDIATE")

        hospital = conn.execute("""
            SELECT min_shelf_life_months
            FROM hospitals
            WHERE hospital_id = ?
        """, (hospital_id,)).fetchone()

        if hospital is None:
            raise ValueError("Hospital does not exist")

        minimum_months = hospital["min_shelf_life_months"]

        required_expiry = add_months(
            date.today(), minimum_months
        ).isoformat()

        # Select only eligible stock, ordered by FEFO
        batches = conn.execute("""
            SELECT batch_id, quantity, expiry_date
            FROM batches
            WHERE product_name = ?
              AND status = 'Released'
              AND quantity > 0
              AND expiry_date >= ?
            ORDER BY expiry_date ASC, batch_id ASC
        """, (product_name, required_expiry)).fetchall()

        total_available = sum(
            batch["quantity"] for batch in batches
        )

        # Do not create an incomplete dispatch
        if total_available < required_quantity:
            conn.rollback()

            return {
                "success": False,
                "message": "Insufficient eligible stock",
                "required": required_quantity,
                "available": total_available,
                "shortage": required_quantity - total_available
            }

        # Create dispatch record
        cursor = conn.execute("""
            INSERT INTO dispatches (hospital_id)
            VALUES (?)
        """, (hospital_id,))

        dispatch_id = cursor.lastrowid

        remaining = required_quantity
        allocations = []

        # Allocate earliest-expiring batches first
        for batch in batches:

            if remaining == 0:
                break

            allocated = min(batch["quantity"], remaining)

            conn.execute("""
                INSERT INTO dispatch_items
                (dispatch_id, batch_id, quantity_shipped)
                VALUES (?, ?, ?)
            """, (
                dispatch_id,
                batch["batch_id"],
                allocated
            ))

            conn.execute("""
                UPDATE batches
                SET quantity = quantity - ?
                WHERE batch_id = ?
            """, (allocated, batch["batch_id"]))

            allocations.append({
                "batch_id": batch["batch_id"],
                "expiry_date": batch["expiry_date"],
                "quantity_shipped": allocated
            })

            remaining -= allocated

        conn.commit()

        return {
            "success": True,
            "dispatch_id": dispatch_id,
            "hospital_id": hospital_id,
            "product_name": product_name,
            "total_shipped": required_quantity,
            "allocations": allocations
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# -----------------------------------------
# 8. VIEW DISPATCH HISTORY
# -----------------------------------------

def get_dispatch_history():

    conn = get_connection()

    history = conn.execute("""
        SELECT
            d.dispatch_id,
            h.hospital_name,
            b.batch_id,
            b.product_name,
            di.quantity_shipped,
            d.dispatch_date
        FROM dispatch_items di
        JOIN dispatches d
            ON di.dispatch_id = d.dispatch_id
        JOIN hospitals h
            ON d.hospital_id = h.hospital_id
        JOIN batches b
            ON di.batch_id = b.batch_id
        ORDER BY d.dispatch_date DESC
    """).fetchall()

    conn.close()

    return [dict(row) for row in history]
import calendar
import math
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from database import get_connection

# ---------- Constants ----------
COLD = "2-8C"
AMBIENT = "Ambient"
STORAGE_CONDITIONS = (AMBIENT, COLD)
PRODUCT_TYPES = ("Medicine", "IV Fluid", "Test Kit")
TEMP_MIN, TEMP_MAX = 2.0, 8.0               # inclusive safe range
SENSOR_MIN, SENSOR_MAX = -50.0, 60.0        # reject garbage sensor values


class InventoryError(Exception):
    """Raised for invalid input or a business rule violation."""


# ---------- Small helpers ----------
def _now():
    return datetime.now().isoformat(timespec="seconds")


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        raise InventoryError(f"Invalid date '{value}'. Use YYYY-MM-DD.")


def _clean(text, field):
    text = (text or "").strip() if isinstance(text, str) or text is None else str(text).strip()
    if not text:
        raise InventoryError(f"{field} is required.")
    return text


def _positive_int(value, field):
    try:
        n = int(value)
        if n != float(value):
            raise ValueError
    except (TypeError, ValueError):
        raise InventoryError(f"{field} must be a whole number.")
    if n <= 0:
        raise InventoryError(f"{field} must be greater than 0.")
    return n


@contextmanager
def transaction(conn):
    """BEGIN IMMEDIATE takes the write lock up front, so two dispatches
    can't read the same stock and oversell it."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _fetch_batch(conn, batch_id):
    row = conn.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if row is None:
        raise InventoryError(f"Batch '{batch_id}' not found.")
    return row


# ---------- Shelf-life rules ----------
def add_months(d, months):
    """Calendar-accurate: Jan 31 + 1 month = Feb 28/29 (clamped to month end)."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def required_expiry_cutoff(min_months, today=None):
    """Earliest acceptable expiry date for a hospital.
    Never earlier than tomorrow, so expired stock can't pass with a tiny requirement."""
    today = _to_date(today) if today else date.today()
    return max(add_months(today, min_months), today + timedelta(days=1))


def is_shelf_life_valid(expiry_date, min_months, today=None):
    return _to_date(expiry_date) >= required_expiry_cutoff(min_months, today)


# ---------- Hospitals ----------
def add_hospital(name, min_shelf_life_months):
    name = _clean(name, "Hospital name")
    months = _positive_int(min_shelf_life_months, "Minimum shelf life (months)")
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO hospitals(hospital_name, min_shelf_life_months) VALUES (?, ?)",
            (name, months),
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        raise InventoryError(f"Hospital '{name}' already exists.")
    finally:
        conn.close()


# ---------- Batches ----------
def add_batch(batch_id, product_name, product_type, storage_condition,
              quantity, expiry_date, initial_temp=None,
              allow_expired=False, today=None):
    """New batches ALWAYS start as 'Pending QC'. Only review_batch() can release them."""
    today = _to_date(today) if today else date.today()
    batch_id = _clean(batch_id, "Batch ID").upper()
    product_name = _clean(product_name, "Product name")
    if product_type not in PRODUCT_TYPES:
        raise InventoryError(f"Product type must be one of {PRODUCT_TYPES}.")
    if storage_condition not in STORAGE_CONDITIONS:
        raise InventoryError(f"Storage condition must be one of {STORAGE_CONDITIONS}.")
    qty = _positive_int(quantity, "Quantity")
    expiry = _to_date(expiry_date)
    if expiry <= today and not allow_expired:
        raise InventoryError("Cannot receive a batch that is already expired.")

    conn = get_connection()
    try:
        with transaction(conn):
            conn.execute(
                """INSERT INTO batches(batch_id, product_name, product_type,
                       storage_condition, quantity, expiry_date, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'Pending QC')""",
                (batch_id, product_name, product_type, storage_condition,
                 qty, expiry.isoformat()),
            )
    except sqlite3.IntegrityError:
        raise InventoryError(f"Batch ID '{batch_id}' already exists.")
    finally:
        conn.close()

    if initial_temp is not None:
        record_temperature(batch_id, initial_temp)
    return batch_id


# ---------- Temperature monitoring ----------
def record_temperature(batch_id, temperature, recorded_at=None):
    """Log a reading. A cold-chain reading outside 2-8C (inclusive) auto-quarantines
    the batch. A later normal reading NEVER auto-releases it."""
    batch_id = _clean(batch_id, "Batch ID").upper()
    try:
        temp = float(temperature)
    except (TypeError, ValueError):
        raise InventoryError("Temperature must be a number.")
    if math.isnan(temp) or not (SENSOR_MIN <= temp <= SENSOR_MAX):
        raise InventoryError(
            f"Temperature {temperature} is outside the plausible sensor range "
            f"({SENSOR_MIN:.0f} to {SENSOR_MAX:.0f} C)."
        )
    if recorded_at is None:
        ts = _now()
    else:
        try:
            ts = datetime.fromisoformat(str(recorded_at)).isoformat(timespec="seconds")
        except ValueError:
            raise InventoryError(f"Invalid timestamp '{recorded_at}'.")

    conn = get_connection()
    try:
        with transaction(conn):
            batch = _fetch_batch(conn, batch_id)
            is_cold = batch["storage_condition"] == COLD
            excursion = is_cold and not (TEMP_MIN <= temp <= TEMP_MAX)

            conn.execute(
                """INSERT INTO temperature_logs(batch_id, temperature, recorded_at, is_excursion)
                   VALUES (?, ?, ?, ?)""",
                (batch_id, temp, ts, int(excursion)),
            )
            # current_temp = most recent reading by timestamp
            conn.execute(
                """UPDATE batches SET current_temp = (
                       SELECT temperature FROM temperature_logs
                       WHERE batch_id = ? ORDER BY recorded_at DESC, log_id DESC LIMIT 1)
                   WHERE batch_id = ?""",
                (batch_id, batch_id),
            )

            status = batch["status"]
            message = "Reading recorded."
            if excursion and status in ("Pending QC", "Released"):
                status = "Quarantined"
                conn.execute("UPDATE batches SET status = 'Quarantined' WHERE batch_id = ?",
                             (batch_id,))
                conn.execute(
                    """INSERT INTO quality_records(batch_id, reason, decision, reviewer, reviewed_at)
                       VALUES (?, ?, 'Auto-Quarantined', 'SYSTEM', ?)""",
                    (batch_id,
                     f"Temperature excursion: {temp:.1f} C outside {TEMP_MIN:.0f}-{TEMP_MAX:.0f} C",
                     _now()),
                )
                message = f"EXCURSION: {temp:.1f} C. Batch auto-quarantined."
            elif excursion:
                message = f"EXCURSION: {temp:.1f} C recorded (batch already '{status}')."

        return {"batch_id": batch_id, "temperature": temp, "excursion": excursion,
                "status": status, "message": message}
    finally:
        conn.close()


def _temp_summary(conn, batch_id):
    row = conn.execute(
        """SELECT COUNT(*) AS readings, MIN(temperature) AS min_temp,
                  MAX(temperature) AS max_temp,
                  COALESCE(SUM(is_excursion), 0) AS excursions
           FROM temperature_logs WHERE batch_id = ?""",
        (batch_id,),
    ).fetchone()
    latest = conn.execute(
        """SELECT temperature, is_excursion FROM temperature_logs
           WHERE batch_id = ? ORDER BY recorded_at DESC, log_id DESC LIMIT 1""",
        (batch_id,),
    ).fetchone()
    return {
        "readings": row["readings"],
        "min_temp": row["min_temp"],
        "max_temp": row["max_temp"],
        "excursions": row["excursions"],
        "latest_temp": latest["temperature"] if latest else None,
        "latest_in_range": (not latest["is_excursion"]) if latest else None,
    }


# ---------- Quality review ----------
def review_batch(batch_id, decision, reviewer, reason, today=None):
    """Quality team decision: 'Approved' (-> Released) or 'Rejected' (final)."""
    today = _to_date(today) if today else date.today()
    batch_id = _clean(batch_id, "Batch ID").upper()
    if decision not in ("Approved", "Rejected"):
        raise InventoryError("Decision must be 'Approved' or 'Rejected'.")
    reviewer = _clean(reviewer, "Reviewer name")
    reason = _clean(reason, "Reason")
    if len(reason) < 5:
        raise InventoryError("Reason is too short. Describe what was reviewed.")

    conn = get_connection()
    try:
        with transaction(conn):
            batch = _fetch_batch(conn, batch_id)
            if batch["status"] not in ("Pending QC", "Quarantined"):
                raise InventoryError(
                    f"Batch {batch_id} is '{batch['status']}' and cannot be reviewed. "
                    f"Only Pending QC or Quarantined batches can be reviewed."
                )
            summary = _temp_summary(conn, batch_id)   # FULL history, not just the last reading

            if decision == "Approved":
                if _to_date(batch["expiry_date"]) <= today:
                    raise InventoryError(
                        f"Cannot release batch {batch_id}: it is expired "
                        f"(expiry {batch['expiry_date']})."
                    )
                if batch["storage_condition"] == COLD:
                    if summary["readings"] == 0:
                        raise InventoryError(
                            f"Cannot release cold-chain batch {batch_id}: no temperature "
                            f"readings on file (storage proof missing)."
                        )
                    if not summary["latest_in_range"]:
                        raise InventoryError(
                            f"Cannot release batch {batch_id}: latest temperature reading "
                            f"({summary['latest_temp']:.1f} C) is outside the "
                            f"{TEMP_MIN:.0f}-{TEMP_MAX:.0f} C range."
                        )
                    if summary["excursions"] > 0 and len(reason) < 15:
                        raise InventoryError(
                            f"Batch {batch_id} has excursion history "
                            f"({summary['excursions']} reading(s)). Provide a written "
                            f"justification of at least 15 characters."
                        )

            new_status = "Released" if decision == "Approved" else "Rejected"
            conn.execute("UPDATE batches SET status = ? WHERE batch_id = ?",
                         (new_status, batch_id))
            conn.execute(
                """INSERT INTO quality_records(batch_id, reason, decision, reviewer, reviewed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (batch_id, reason, decision, reviewer, _now()),
            )
        return {"batch_id": batch_id, "status": new_status, "temperature_summary": summary}
    finally:
        conn.close()


# ---------- Dispatch (FEFO) ----------
def _ineligible_reason(b, cutoff, today):
    """Return why a batch can't ship, or None if it can. Order matters."""
    exp = date.fromisoformat(b["expiry_date"])
    if b["status"] == "Rejected":
        return "Rejected by quality team"
    if b["status"] == "Quarantined":
        return "Quarantined (awaiting quality review)"
    if b["status"] == "Pending QC":
        return "Not released (pending quality release)"
    if exp <= today:
        return f"Expired (expiry {exp})"
    if b["quantity"] <= 0:
        return "No stock left"
    if exp < cutoff:
        return (f"Short shelf life: expires {exp}, hospital needs {cutoff} or later "
                f"(short by {(cutoff - exp).days} days)")
    return None


def dispatch_order(hospital_id, product_name, quantity, today=None, allow_partial=False):
    """FEFO allocation. All-or-nothing by default."""
    today = _to_date(today) if today else date.today()
    qty = _positive_int(quantity, "Quantity")
    product_name = _clean(product_name, "Product name")

    conn = get_connection()
    try:
        with transaction(conn):   # lock first, THEN read stock
            hospital = conn.execute("SELECT * FROM hospitals WHERE hospital_id = ?",
                                    (hospital_id,)).fetchone()
            if hospital is None:
                raise InventoryError("Hospital not found.")
            cutoff = required_expiry_cutoff(hospital["min_shelf_life_months"], today)

            rows = conn.execute(
                """SELECT batch_id, quantity, expiry_date, status
                   FROM batches WHERE product_name = ?
                   ORDER BY expiry_date ASC, batch_id ASC""",
                (product_name,),
            ).fetchall()
            if not rows:
                raise InventoryError(f"No batches found for product '{product_name}'.")

            eligible, skipped = [], []
            for b in rows:
                reason = _ineligible_reason(b, cutoff, today)
                if reason:
                    skipped.append({"batch_id": b["batch_id"], "reason": reason})
                else:
                    eligible.append(b)

            allocations, remaining = [], qty
            for b in eligible:
                if remaining == 0:
                    break
                take = min(b["quantity"], remaining)
                allocations.append({
                    "batch_id": b["batch_id"],
                    "expiry_date": b["expiry_date"],
                    "days_left": (date.fromisoformat(b["expiry_date"]) - today).days,
                    "quantity": take,
                })
                remaining -= take

            available = sum(b["quantity"] for b in eligible)
            fulfilled = remaining == 0

            if not fulfilled and not (allow_partial and allocations):
                return {
                    "success": False, "dispatch_id": None, "requested": qty,
                    "eligible_available": available, "allocations": [],
                    "skipped": skipped, "shelf_life_cutoff": cutoff.isoformat(),
                    "message": (f"Insufficient eligible stock: requested {qty}, "
                                f"only {available} eligible for this hospital."),
                }

            cur = conn.execute(
                "INSERT INTO dispatches(hospital_id, dispatch_date) VALUES (?, ?)",
                (hospital_id, _now()),
            )
            dispatch_id = cur.lastrowid
            for a in allocations:
                conn.execute(
                    """INSERT INTO dispatch_items(dispatch_id, batch_id, quantity_shipped)
                       VALUES (?, ?, ?)""",
                    (dispatch_id, a["batch_id"], a["quantity"]),
                )
                updated = conn.execute(
                    """UPDATE batches SET quantity = quantity - ?
                       WHERE batch_id = ? AND quantity >= ?""",
                    (a["quantity"], a["batch_id"], a["quantity"]),
                )
                if updated.rowcount != 1:      # safety net, rolls everything back
                    raise InventoryError("Stock changed during dispatch. Please retry.")

        shipped = qty - remaining
        return {
            "success": True, "dispatch_id": dispatch_id, "requested": qty,
            "shipped": shipped, "shortfall": remaining,
            "status": "FULL" if fulfilled else "PARTIAL",
            "allocations": allocations, "skipped": skipped,
            "shelf_life_cutoff": cutoff.isoformat(),
            "message": f"Dispatched {shipped} units across {len(allocations)} batch(es).",
        }
    finally:
        conn.close()


# ---------- Read helpers (used by the UI) ----------
def _query(sql, params=()):
    conn = get_connection()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def get_all_batches():
    return _query("SELECT * FROM batches ORDER BY expiry_date, batch_id")


def get_hospitals():
    return _query("SELECT * FROM hospitals ORDER BY hospital_name")


def get_product_names():
    return [r["product_name"] for r in
            _query("SELECT DISTINCT product_name FROM batches ORDER BY product_name")]


def get_temperature_logs(batch_id=None):
    if batch_id:
        return _query("SELECT * FROM temperature_logs WHERE batch_id = ? "
                      "ORDER BY recorded_at, log_id", (batch_id.upper(),))
    return _query("SELECT * FROM temperature_logs ORDER BY recorded_at, log_id")


def get_quality_records(batch_id=None):
    if batch_id:
        return _query("SELECT * FROM quality_records WHERE batch_id = ? ORDER BY record_id",
                      (batch_id.upper(),))
    return _query("SELECT * FROM quality_records ORDER BY record_id")


def get_dispatch_history():
    return _query(
        """SELECT d.dispatch_id, d.dispatch_date, h.hospital_name, b.product_name,
                  i.batch_id, b.expiry_date, i.quantity_shipped
           FROM dispatches d
           JOIN hospitals h ON h.hospital_id = d.hospital_id
           JOIN dispatch_items i ON i.dispatch_id = d.dispatch_id
           JOIN batches b ON b.batch_id = i.batch_id
           ORDER BY d.dispatch_id DESC, b.expiry_date"""
    )


def get_batch_proof(batch_id):
    """Storage proof for one batch: details, temp summary, full log, QA decisions."""
    batch_id = _clean(batch_id, "Batch ID").upper()
    conn = get_connection()
    try:
        batch = dict(_fetch_batch(conn, batch_id))
        return {
            "batch": batch,
            "temperature_summary": _temp_summary(conn, batch_id),
            "temperature_logs": [dict(r) for r in conn.execute(
                "SELECT * FROM temperature_logs WHERE batch_id = ? ORDER BY recorded_at, log_id",
                (batch_id,))],
            "quality_records": [dict(r) for r in conn.execute(
                "SELECT * FROM quality_records WHERE batch_id = ? ORDER BY record_id",
                (batch_id,))],
        }
    finally:
        conn.close()