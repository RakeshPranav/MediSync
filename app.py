from datetime import date, timedelta

import pandas as pd
import streamlit as st

import inventory as inv
from database import create_tables

create_tables(verbose=False)
st.set_page_config(page_title="Medical Batch Inventory", layout="wide")


# ---------- helpers ----------
def run(fn, *args, **kwargs):
    """Call a backend function; show business-rule errors nicely, return None on error."""
    try:
        return fn(*args, **kwargs)
    except inv.InventoryError as e:
        st.error(str(e))
        return None


def flash(kind, msg):
    """Message that survives st.rerun() (kind: success / error / warning / info)."""
    st.session_state["flash"] = (kind, msg)


def table(rows, empty="No records."):
    if not rows:
        st.info(empty)
    else:
        st.dataframe(pd.DataFrame(rows), hide_index=True)


def fmt_temp(x):
    return "-" if x is None else f"{x:.1f} C"


def batches_df():
    rows = inv.get_all_batches()
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    today = date.today()
    d["days_left"] = d["expiry_date"].apply(lambda s: (date.fromisoformat(s) - today).days)
    return d


# ---------- pages ----------
def page_dashboard():
    st.header("Dashboard")
    d = batches_df()
    if d.empty:
        st.info("No batches yet. Run `python seed_data.py` or add batches.")
        return

    sellable = d[(d.status == "Released") & (d.days_left > 0)]
    cols = st.columns(6)
    cols[0].metric("Total batches", len(d))
    cols[1].metric("Sellable units", int(sellable.quantity.sum()))
    cols[2].metric("Released", int((d.status == "Released").sum()))
    cols[3].metric("Pending QC", int((d.status == "Pending QC").sum()))
    cols[4].metric("Quarantined", int((d.status == "Quarantined").sum()))
    cols[5].metric("Rejected", int((d.status == "Rejected").sum()))

    left, right = st.columns(2)
    with left:
        st.subheader("Expiry alerts")
        expired = d[(d.days_left <= 0) & (d.quantity > 0)]
        soon = d[(d.days_left > 0) & (d.days_left <= 90) & (d.quantity > 0)]
        cols_show = ["batch_id", "product_name", "quantity", "expiry_date", "days_left", "status"]
        if not expired.empty:
            st.error(f"{len(expired)} expired batch(es) still holding stock")
            st.dataframe(expired[cols_show], hide_index=True)
        if not soon.empty:
            st.warning(f"{len(soon)} batch(es) expiring within 90 days")
            st.dataframe(soon[cols_show], hide_index=True)
        if expired.empty and soon.empty:
            st.success("No expiry alerts.")
    with right:
        st.subheader("Temperature excursions")
        logs = [l for l in inv.get_temperature_logs() if l["is_excursion"]]
        if logs:
            st.error(f"{len(logs)} excursion reading(s) on record")
            table([{"batch_id": l["batch_id"], "temperature": l["temperature"],
                    "recorded_at": l["recorded_at"]} for l in logs])
        else:
            st.success("No excursions recorded.")

    st.subheader("Units in stock by status")
    st.bar_chart(d.groupby("status")["quantity"].sum())


def page_batches():
    st.header("Batch Management")
    tab_view, tab_add = st.tabs(["View batches", "Add batch"])

    with tab_view:
        d = batches_df()
        if d.empty:
            st.info("No batches yet.")
        else:
            c1, c2 = st.columns(2)
            statuses = c1.multiselect("Status", sorted(d.status.unique()), default=sorted(d.status.unique()))
            search = c2.text_input("Search batch ID or product")
            view = d[d.status.isin(statuses)]
            if search:
                s = search.lower()
                view = view[view.batch_id.str.lower().str.contains(s) | view.product_name.str.lower().str.contains(s)]
            st.dataframe(view.drop(columns=["created_at"]), hide_index=True)

    with tab_add:
        st.caption("New batches always start as 'Pending QC'. The quality team must release them.")
        with st.form("add_batch"):
            c1, c2 = st.columns(2)
            batch_id = c1.text_input("Batch ID")
            product = c2.text_input("Product name")
            product_type = c1.selectbox("Product type", inv.PRODUCT_TYPES)
            storage = c2.selectbox("Storage condition", inv.STORAGE_CONDITIONS)
            qty = c1.number_input("Quantity", min_value=1, value=100, step=1)
            expiry = c2.date_input("Expiry date", value=date.today() + timedelta(days=365))
            temp_txt = st.text_input("Initial temperature in C (optional)")
            if st.form_submit_button("Add batch"):
                try:
                    temp = float(temp_txt) if temp_txt.strip() else None
                except ValueError:
                    st.error("Temperature must be a number.")
                else:
                    if run(inv.add_batch, batch_id, product, product_type, storage, int(qty), expiry, temp):
                        flash("success", f"Batch {batch_id.strip().upper()} added as Pending QC.")
                        st.rerun()


def page_hospitals():
    st.header("Hospital Management")
    with st.form("add_hospital"):
        name = st.text_input("Hospital name")
        months = st.number_input("Minimum remaining shelf life (months)", min_value=1, value=6, step=1)
        if st.form_submit_button("Register hospital"):
            if run(inv.add_hospital, name, int(months)):
                flash("success", f"Hospital '{name.strip()}' registered.")
                st.rerun()
    table(inv.get_hospitals(), "No hospitals registered.")


def page_temperature():
    st.header("Temperature Monitoring")
    batches = inv.get_all_batches()
    if not batches:
        st.info("No batches yet.")
        return
    labels = {b["batch_id"]: f'{b["batch_id"]} | {b["product_name"]} | {b["storage_condition"]} | {b["status"]}'
              for b in batches}
    bid = st.selectbox("Batch", list(labels), format_func=labels.get)

    with st.form("add_temp"):
        temp = st.number_input("Temperature (C)", value=5.0, step=0.1, format="%.1f")
        if st.form_submit_button("Record reading"):
            res = run(inv.record_temperature, bid, temp)
            if res:
                flash("error" if res["excursion"] else "success", res["message"])
                st.rerun()

    logs = inv.get_temperature_logs(bid)
    if not logs:
        st.info("No readings for this batch.")
        return
    df = pd.DataFrame(logs)
    df["result"] = df["is_excursion"].map({1: "EXCURSION", 0: "OK"})
    st.line_chart(df.set_index("recorded_at")["temperature"])
    st.dataframe(df[["recorded_at", "temperature", "result"]], hide_index=True)


def page_quality():
    st.header("Quality Control")
    waiting = [b for b in inv.get_all_batches() if b["status"] in ("Pending QC", "Quarantined")]
    if not waiting:
        st.success("Nothing waiting for review.")
        return
    labels = {b["batch_id"]: f'{b["batch_id"]} | {b["product_name"]} | {b["status"]}' for b in waiting}
    bid = st.selectbox("Batch to review", list(labels), format_func=labels.get)

    proof = inv.get_batch_proof(bid)
    s = proof["temperature_summary"]
    st.subheader("Storage proof")
    c = st.columns(5)
    c[0].metric("Readings", s["readings"])
    c[1].metric("Min", fmt_temp(s["min_temp"]))
    c[2].metric("Max", fmt_temp(s["max_temp"]))
    c[3].metric("Excursions", s["excursions"])
    c[4].metric("Latest", fmt_temp(s["latest_temp"]))
    if proof["batch"]["storage_condition"] == inv.COLD and s["readings"] == 0:
        st.warning("Cold-chain batch with no temperature readings. It cannot be released.")
    if proof["temperature_logs"]:
        logs = pd.DataFrame(proof["temperature_logs"])
        logs["result"] = logs["is_excursion"].map({1: "EXCURSION", 0: "OK"})
        st.dataframe(logs[["recorded_at", "temperature", "result"]], hide_index=True)
    st.subheader("Quality history")
    table(proof["quality_records"], "No quality decisions yet.")

    st.subheader("Decision")
    with st.form("review"):
        reviewer = st.text_input("Reviewer name")
        reason = st.text_area("Reason / justification")
        decision = st.radio("Decision", ["Approved", "Rejected"], horizontal=True)
        if st.form_submit_button("Submit decision"):
            res = run(inv.review_batch, bid, decision, reviewer, reason)
            if res:
                flash("success", f"{bid}: {decision}. New status: {res['status']}.")
                st.rerun()


def page_dispatch():
    st.header("Dispatch (FEFO)")
    hospitals = inv.get_hospitals()
    products = inv.get_product_names()
    if not hospitals or not products:
        st.info("Register at least one hospital and one batch first.")
        return
    names = {h["hospital_id"]: h for h in hospitals}
    c1, c2, c3 = st.columns(3)
    hid = c1.selectbox("Hospital", list(names), format_func=lambda i: names[i]["hospital_name"])
    product = c2.selectbox("Product", products)
    qty = c3.number_input("Quantity", min_value=1, value=100, step=1)
    allow_partial = st.checkbox("Allow partial dispatch if stock is short")

    months = names[hid]["min_shelf_life_months"]
    st.caption(f"Requirement: {months} month(s) remaining shelf life, so batches must expire on or after "
               f"{inv.required_expiry_cutoff(months)}.")

    if st.button("Allocate and dispatch", type="primary"):
        res = run(inv.dispatch_order, hid, product, int(qty), allow_partial=allow_partial)
        if res is None:
            return
        if res["success"]:
            (st.success if res["status"] == "FULL" else st.warning)(
                f"Dispatch #{res['dispatch_id']} ({res['status']}): {res['message']}"
                + (f" Shortfall: {res['shortfall']}." if res["shortfall"] else ""))
            st.subheader("Batches shipped (FEFO order)")
            table(res["allocations"])
        else:
            st.error(res["message"])
        if res["skipped"]:
            st.subheader("Batches NOT used, and why")
            table(res["skipped"])


def page_history():
    st.header("Dispatch History")
    rows = inv.get_dispatch_history()
    if not rows:
        st.info("No dispatches yet.")
        return
    df = pd.DataFrame(rows)
    pick = st.multiselect("Hospital", sorted(df.hospital_name.unique()), default=sorted(df.hospital_name.unique()))
    st.dataframe(df[df.hospital_name.isin(pick)], hide_index=True)


# ---------- main ----------
PAGES = {
    "Dashboard": page_dashboard,
    "Dispatch": page_dispatch,
    "Quality Control": page_quality,
    "Temperature Monitoring": page_temperature,
    "Batch Management": page_batches,
    "Hospital Management": page_hospitals,
    "Dispatch History": page_history,
}


def main():
    st.sidebar.title("Medical Batch Inventory")
    choice = st.sidebar.radio("Go to", list(PAGES))

    with st.sidebar.expander("Demo data"):
        sure = st.checkbox("Wipe DB and reload demo data")
        if st.button("Reload demo data", disabled=not sure):
            import seed_data
            seed_data.seed()
            flash("success", "Demo data reloaded.")
            st.rerun()

    if "flash" in st.session_state:
        kind, msg = st.session_state.pop("flash")
        getattr(st, kind)(msg)

    PAGES[choice]()


main()