# Medical Batch Inventory & Expiry Management System

A warehouse application that decides **which batches of medicines, IV fluids and test kits can be shipped to a hospital, and in what order**, while enforcing quality release, expiry, customer shelf-life and cold-chain (2-8 C) rules, and keeping an auditable record of storage conditions.

Built with **Python, SQLite and Streamlit**.

---

## 1. The problem

Finished batches wait in a warehouse for quality release. Only released batches can be sold. Orders must use the earliest-expiring stock first (FEFO), but hospitals demand a minimum remaining shelf life (for example, 6 months). Some products must be stored at 2-8 C, and a temperature excursion places the batch in quarantine until the quality team reviews it.

In simple words, the system must:

- choose which batches to ship, in the right order,
- never ship unreleased, expired, rejected or quarantined stock,
- respect each hospital's minimum remaining shelf life,
- keep proof of storage conditions.

## 2. How the system solves it

| Problem statement requirement | Solution in this project |
|---|---|
| Only released batches can be sold | New batches start as `Pending QC`. Only a quality review can move them to `Released`. Dispatch only considers `Released` stock. |
| Never ship expired / quarantined stock | Every candidate batch goes through one eligibility check that returns a plain-language skip reason. |
| FEFO | Eligible batches are sorted by `expiry_date`, then `batch_id` (deterministic tie-break), and filled greedily. |
| Hospital minimum shelf life | Each hospital stores its requirement in months. A calendar-month cutoff date is computed per order. |
| 2-8 C cold chain, excursion = quarantine | Every reading is stored. A reading outside 2.0-8.0 C on a cold-chain batch auto-quarantines it. |
| Quarantine until quality review | Only `review_batch()` can release or reject, with a mandatory reviewer name and reason. |
| Proof of storage conditions | Full temperature log per batch, plus quality decision history, shown together in the Quality Control page. |

---

## 3. Features

**Batch management**
- Add batches (product, type, storage condition, quantity, expiry). Always created as `Pending QC`.
- Search and filter by status or product; days-to-expiry shown for every batch.

**Hospital management**
- Register hospitals with their own minimum remaining shelf life (months).

**Temperature monitoring**
- Record readings per batch, view history as a chart and table, excursions flagged.
- Boundary values 2.0 C and 8.0 C are treated as normal; 1.9 C and 8.1 C are excursions.
- Ambient batches are never auto-quarantined by temperature.

**Quality control**
- Review queue of `Pending QC` and `Quarantined` batches.
- Storage proof panel: reading count, min, max, latest, excursion count, full log, past decisions.
- Approve or reject with reviewer name and reason, all recorded.

**FEFO dispatch**
- Pick hospital, product and quantity; the system shows the required expiry cutoff.
- Result shows the batches shipped in FEFO order and every batch that was **not** used, with the reason.
- All-or-nothing by default; optional "allow partial dispatch" reports the shortfall.

**Dashboard**
- Total batches, sellable units, counts by status, expired stock alert, "expiring within 90 days" alert, excursion list, stock-by-status chart.

**Dispatch history**
- Every dispatch with hospital, batch, expiry date, quantity and date.

---

## 4. Business rules

| Rule | Behaviour |
|---|---|
| Quality release | A new batch is `Pending QC`; it is sellable only after approval. |
| Status values | `Pending QC`, `Released`, `Quarantined`, `Rejected`. **Expired is calculated from the date, never stored**, so it cannot go stale. |
| Temperature range | 2.0-8.0 C inclusive, applied to `2-8C` batches only. Readings outside -50 to 60 C, non-numeric values and NaN are rejected as bad sensor data. |
| Auto-quarantine | An excursion on a `Pending QC` or `Released` cold-chain batch sets it to `Quarantined` and logs a `SYSTEM` record. |
| Normal reading after excursion | Does **not** release the batch. A person must review the history. |
| Release guards | Cannot release an expired batch; a cold-chain batch needs at least one reading and an in-range latest reading; a batch with excursion history needs a written justification of at least 15 characters. Reviewer and reason are mandatory. |
| Rejected is final | A rejected batch can never be reviewed again or shipped. |
| Shelf life | `cutoff = today + N calendar months` (month-end clamped, e.g. 31 Jan + 1 month = 28/29 Feb), never earlier than tomorrow. A batch passes if `expiry >= cutoff`; one day short fails. |
| FEFO | Earliest expiry first among **eligible** batches. The globally earliest batch may be ineligible for a particular hospital, so different hospitals get different allocations from the same stock. |
| Stock validation | Zero-quantity batches are skipped. If eligible stock is short, nothing ships and nothing is deducted (unless partial dispatch is explicitly allowed). |
| Transaction safety | A dispatch runs inside one `BEGIN IMMEDIATE` transaction. The write lock is taken before stock is read, stock is deducted with `UPDATE ... WHERE quantity >= ?`, and any failure rolls everything back. |

### Shelf-life example

Today is 31 October 2026 and the hospital requires 6 months. The cutoff is 30 April 2027. A released batch expiring on 29 April 2027 is excluded even though it is approved and in stock; a batch expiring on 30 April 2027 is accepted.

---

## 5. Architecture

```text
              USER (browser)
                    |
                    v
        +-----------------------+
        |   Streamlit UI        |   app.py
        |   7 pages             |
        +-----------------------+
                    |   calls functions, catches InventoryError
                    v
        +-----------------------+
        |   Business logic      |   inventory.py
        |   rules, FEFO,        |
        |   transactions        |
        +-----------------------+
                    |   get_connection()
                    v
        +-----------------------+
        |   Database layer      |   database.py
        |   schema, connection  |
        +-----------------------+
                    |
                    v
        +-----------------------+
        |   SQLite              |   database/inventory.db
        +-----------------------+
```

The UI contains no business rules. Every rule lives in `inventory.py`, so it can be tested without the interface.

---

## 6. Database design

Six tables, foreign keys enforced (`PRAGMA foreign_keys = ON`).

**batches**

| Column | Notes |
|---|---|
| `batch_id` | Primary key, stored uppercase |
| `product_name` | Case-insensitive |
| `product_type` | `Medicine`, `IV Fluid`, `Test Kit` |
| `storage_condition` | `Ambient` or `2-8C` |
| `quantity` | Integer, never negative |
| `expiry_date` | ISO date `YYYY-MM-DD` |
| `status` | `Pending QC` (default), `Released`, `Quarantined`, `Rejected` |
| `current_temp` | Latest reading by timestamp |
| `created_at` | Timestamp |

**hospitals**: `hospital_id`, `hospital_name` (unique), `min_shelf_life_months` (at least 1)

**temperature_logs**: `log_id`, `batch_id` (FK), `temperature`, `recorded_at`, `is_excursion`

**dispatches**: `dispatch_id`, `hospital_id` (FK), `dispatch_date`

**dispatch_items**: `item_id`, `dispatch_id` (FK), `batch_id` (FK), `quantity_shipped` (greater than 0)

**quality_records**: `record_id`, `batch_id` (FK), `reason`, `decision` (`Auto-Quarantined`, `Approved`, `Rejected`), `reviewer` (`SYSTEM` for automatic), `reviewed_at`

Relationships: one batch has many temperature readings and many quality records; one hospital has many dispatches; one dispatch has many dispatch items, each pointing to the batch that supplied the stock.

---

## 7. Project structure

```text
medical_inventory/
├── app.py              Streamlit user interface (7 pages)
├── inventory.py        Business logic: rules, FEFO, temperature, QA, dispatch
├── database.py         Connection, schema creation, reset helper
├── seed_data.py        Loads demo data (wipes and rebuilds the database)
├── test_backend.py     17 backend tests (uses its own test database)
├── requirements.txt    Python dependencies
├── README.md           This file
├── DEMO_AND_VIVA.md    Demo script, break-test checklist and viva Q&A
├── .gitignore          Keeps venv, caches and database files out of Git
└── database/
    ├── inventory.db        Application database
    └── test_inventory.db   Created by the tests only
```

`test_sqlite.py` and `check_db.py` from early setup are optional leftovers and are not used by the application.

### Main functions in `inventory.py`

| Function | Purpose |
|---|---|
| `add_batch`, `add_hospital` | Validated record creation |
| `record_temperature` | Store a reading, detect excursion, auto-quarantine |
| `review_batch` | Quality approve/reject with release guards |
| `dispatch_order` | FEFO allocation with shelf-life checks, transactional |
| `required_expiry_cutoff`, `add_months`, `is_shelf_life_valid` | Calendar-month shelf-life maths |
| `get_batch_proof` | Batch details, temperature summary, full log and quality history |
| `get_all_batches`, `get_hospitals`, `get_temperature_logs`, `get_quality_records`, `get_dispatch_history` | Read helpers for the UI |

All business-rule violations raise `InventoryError`, which the UI shows as a clear message.

---

## 8. Installation and setup

**Prerequisites:** Python 3.10 or later. VS Code is recommended. DB Browser for SQLite is optional for inspecting the database.

```bash
# 1. Get the code and enter the project folder
git clone <your-repository-url>
cd <repository-folder-name>

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate            # Windows (Command Prompt)
# source venv/bin/activate       # macOS / Linux (use python3 if python is not found)

# 3. Install dependencies
pip install -r requirements.txt

# 4. Build the schema
python database.py

# 5. Load the demo data
python seed_data.py

# 6. Start the application
streamlit run app.py
```

If the `streamlit` command is not recognised, run `python -m streamlit run app.py` instead. On the very first launch Streamlit may ask for an email in the terminal; press Enter to skip it.

The app opens at `http://localhost:8501`.

Always run these commands from the project root, because the database path is relative (`database/inventory.db`). The database file is created locally by steps 4 and 5; it is not stored in Git.

---

## 9. Demo data

`seed_data.py` creates 14 batches, 4 hospitals and temperature logs. Dates are relative to the day you run it, so the demo scenarios never go stale.

**Hospitals**

| Hospital | Minimum shelf life |
|---|---:|
| City General Hospital | 6 months |
| Sunrise Children's Hospital | 8 months |
| Rural District Hospital | 3 months |
| Metro Super Specialty Hospital | 12 months |

**Batches and the case each one demonstrates**

| Batch | Product | Storage | Final status | Demonstrates |
|---|---|---|---|---|
| PCM-2601 / 2602 | Paracetamol 500mg | Ambient | Released | Normal FEFO ordering |
| PCM-2603 | Paracetamol 500mg | Ambient | Pending QC | Unreleased stock is never shipped |
| RL-2601 | Ringer Lactate IV | Ambient | Released | Normal stock |
| RL-2602 | Ringer Lactate IV | Ambient | Released, expired | Expired stock is never shipped |
| RL-2603 | Ringer Lactate IV | Ambient | Released | Expires 5 days short of City General's 6-month cutoff |
| INS-2601 / 2603 | Insulin Glargine | 2-8C | Released | Normal cold-chain stock |
| INS-2602 | Insulin Glargine | 2-8C | **Quarantined** | 9.6 C excursion; stays quarantined even after a normal 5.0 C reading |
| NS1-2601 | Dengue NS1 Test Kit | 2-8C | Released | Readings of exactly 2.0 and 8.0 C are accepted |
| NS1-2602 | Dengue NS1 Test Kit | 2-8C | Released | Normal stock |
| CTX-2601 / 2602 | Ceftriaxone 1g | Ambient | Released | Normal and short-dated stock |
| CTX-2603 | Ceftriaxone 1g | Ambient | Rejected | Rejected stock is never shipped |

---

## 10. Testing

### Automated backend tests

```bash
python test_backend.py
```

Runs 17 tests against a separate test database (`database/test_inventory.db`), so real data is never touched. Each test prints `PASS` or `FAIL`, ending with `17/17 passed`.

Coverage:

- calendar-month maths (month-end clamping, leap year, year rollover) and the exact shelf-life boundary,
- new batches start `Pending QC`,
- temperature boundaries (2.0, 8.0 normal; 1.9, 8.1 excursion), ambient batches unaffected,
- excursion on a released batch quarantines it; normal readings never release it,
- FEFO order, tie-break by batch ID, case-insensitive product names,
- pending, quarantined, rejected and expired stock never shipped,
- all-or-nothing dispatch with no stock deducted on failure; partial dispatch only when allowed,
- per-hospital shelf-life differences,
- every release guard (expired, no readings, out-of-range latest reading, weak justification, final rejection, mandatory reviewer and reason),
- input validation (bad numbers, dates, duplicates, unknown batch/product/hospital),
- batch storage proof contains the complete history.

### Manual UI check (with the demo data)

| Page | Action | Expected result |
|---|---|---|
| Dashboard | Open | 14 batches; 1 quarantined, 1 rejected, 1 pending QC; expired-stock alert for RL-2602 |
| Dispatch | City General orders 150 Ringer Lactate | Ships from RL-2601. RL-2603 skipped: short by 5 days. RL-2602 skipped: expired |
| Dispatch | Rural District orders 300 Ringer Lactate | RL-2603 (250) then RL-2601 (50): same stock, different result |
| Dispatch | Sunrise orders 150 Insulin | INS-2601 (100) then INS-2603 (50). INS-2602 skipped: quarantined |
| Dispatch | Metro orders 150 Insulin | Fails: only 120 eligible; nothing deducted |
| Temperature | Record 9.1 C on NS1-2602 | Excursion message; batch becomes Quarantined |
| Quality Control | Review it, approve with a short reason | Rejected by the guards; approve after a normal reading with a proper justification and it is Released |
| Dispatch History | Open | The dispatches you made, by batch |

---

## 11. Suggested demonstration flow

1. **Dashboard:** show status counts and the expiry and excursion alerts.
2. **Dispatch:** City General orders Ringer Lactate; point out the batch skipped for being 5 days short.
3. **Dispatch:** Rural District orders the same product to show a different FEFO result from the same stock.
4. **Dispatch:** Metro orders Insulin and fails; point out the quarantined batch is excluded.
5. **Temperature Monitoring:** record an out-of-range reading and show the auto-quarantine.
6. **Quality Control:** show the storage proof, then release with a justification.
7. **Dispatch History:** show the recorded transactions.

---

## 12. Troubleshooting

| Problem | Cause and fix |
|---|---|
| `ModuleNotFoundError: No module named 'inventory'` | Run commands from the project root; `app.py` must sit next to `inventory.py`. |
| App shows no data | You probably ran from another folder and created a second empty database. Run from the project root, then `python seed_data.py`. |
| `PermissionError` when running `seed_data.py` on Windows | The database file is open. Stop Streamlit and any DB viewer, then retry. |
| Schema looks outdated after pulling changes | Delete `database/inventory.db`, run `python database.py`, then `python seed_data.py`. |
| PowerShell says running scripts is disabled when activating the venv | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again, or use Command Prompt. |
| `streamlit` is not recognised | The venv is not active. Activate it, or use `python -m streamlit run app.py`. |
| `python` not found on macOS / Linux | Use `python3` and `pip3`. |

---

## 13. Known limitations

- Product names are free text (case-insensitive) rather than a separate products table.
- No login or roles; the quality team is represented by the reviewer name entered.
- An excursion is a single out-of-range reading. Duration of excursion and mean kinetic temperature are not modelled.
- Temperature logs are per batch, not per storage location or sensor.
- Dispatch commits immediately; there is no preview step and no dispatch cancellation or returns.
- Records cannot be edited or deleted from the UI, by design: pharmaceutical records are corrected by adding new records (for example rejecting a batch with a reason), which keeps the audit trail intact.
- Single-user SQLite database, suited to a demo or small site rather than concurrent multi-site use.

## 14. Future enhancements

- Dispatch preview ("plan, then confirm") and downloadable storage-proof report per dispatch.
- Role-based access for warehouse operators and the quality team, with authentication.
- Excursion duration and mean kinetic temperature assessment.
- Separate products table with per-product storage rules.
- Barcode or QR scanning and real-time IoT sensor ingestion.
- Email or chat notifications for excursions and near-expiry stock.
- Report export to Excel or PDF.
- Move to PostgreSQL or Supabase for multi-user, multi-site deployment.

---

## 15. Technology stack

| Technology | Purpose |
|---|---|
| Python | Business logic and validation |
| SQLite (`sqlite3`) | Relational storage with constraints and transactions; no server needed |
| Streamlit | Web interface written in Python |
| Pandas | Tables and dashboard data handling |

---

**Developed as a final-year engineering placement project.**
