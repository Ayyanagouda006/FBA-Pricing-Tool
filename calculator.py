import streamlit as st
from datetime import datetime
from data_fetch import fetch_quote_data
from pricing_calculation import rates
import pandas as pd
import os

LOG_FILE = r"Logs/success_rates.xlsx"

def safe_int(val, default=1):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def safe_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def remove_ids(data):
    if isinstance(data, dict):
        return {k: remove_ids(v) for k, v in data.items() if k != "id"}
    elif isinstance(data, list):
        return [remove_ids(item) for item in data]
    else:
        return data
    
def log_rate_request(quote_id, console_type, service_modes, result, errors):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "Error" if not result else "Success"
    error_messages = "; ".join(errors) if errors else ""
    service = ", ".join(service_modes) if len(service_modes) > 0 else ""
    total_destinations = len(result) if result else 0

    log_entry = {
        "Timestamp": timestamp,
        "Quote ID": quote_id,
        "OverRide ConsoleType": console_type,
        "OverRide ServiceModes": service,
        "Status": status,
        "Error Messages": error_messages,
        "Total Destinations": total_destinations
    }

    # Load or initialize log DataFrame
    if os.path.exists(LOG_FILE):
        df_logs = pd.read_excel(LOG_FILE)
    else:
        df_logs = pd.DataFrame(columns=[
            "Timestamp", "Quote ID", "Status", "OverRide ConsoleType", "OverRide ServiceModes", "Error Messages", "Total Destinations"
        ])

    # Append new log entry and save
    df_logs = pd.concat([df_logs, pd.DataFrame([log_entry])], ignore_index=True)
    df_logs.to_excel(LOG_FILE, index=False)

import os
import pandas as pd
from datetime import datetime

def quotations_backup(quote_id, result):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_path = "Logs/quotations.xlsx"
    data = []

    for destination, consoles in result.items():
        for console, details in consoles.items():
            entry = details.copy()
            entry['Agquote ID'] = quote_id
            entry['Destination'] = destination
            entry['Console Type'] = console
            entry['Quoted Date/Time'] = timestamp
            data.append(entry)

    # New data as DataFrame
    df_new = pd.DataFrame(data)

    # Check if file exists
    if os.path.exists(file_path):
        try:
            df_existing = pd.read_excel(file_path)

            # Drop existing rows with the same quote_id
            df_existing = df_existing[df_existing['Agquote ID'] != quote_id]

            # Append new rows to remaining data
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        except Exception as e:
            print("❌ Error reading existing file. Creating new one instead:", e)
            df_combined = df_new
    else:
        df_combined = df_new

    # Save back to the same file
    df_combined.to_excel(file_path, index=False)
    print("✅ Quotations updated in:", file_path)


    
def fba_quote_app():
    # ----------------- Session State Init -----------------
    if "form_data_loaded" not in st.session_state:
        st.session_state.form_data_loaded = False
    if "last_quote_input" not in st.session_state:
        st.session_state.last_quote_input = ""
    if "multidest" not in st.session_state:
        st.session_state.multidest = []

    # ----------------- Layout -----------------
    left_col, right_col = st.columns(2)

    # ----------------- Left Column -----------------
    with left_col:
        quote_id = st.text_input("Enter Ag Quote No.", key="quote_input")

        if quote_id != st.session_state.last_quote_input:
            st.session_state.form_data_loaded = False
            st.session_state.last_quote_input = quote_id
            st.rerun()

        if quote_id and not st.session_state.form_data_loaded:
            try:
                quote_data, entityname = fetch_quote_data(quote_id)

                if not quote_data:
                    st.error("❌ Quote not found or invalid ID.")
                else:
                    quote_info = quote_data.get("quoteData", {})
                    quotesum_info = quote_data.get("quoteSummary", {})

                    is_fba = quote_info.get("fba", "").strip().lower() == "yes"
                    shipment_scope = quotesum_info.get("shipmentScope", "")

                    if not is_fba:
                        st.error("🚫 The entered quotation is not marked as an FBA shipment.")
                    elif shipment_scope not in ['Port-to-Door' , 'Door-to-Door']:
                        st.error("🚫 Shipment Scope must be either 'Port to Door' or 'Door to Door'.")
                    else:
                        st.session_state.scope = quotesum_info.get("shipmentScope", "")
                        st.session_state.entityName = entityname
                        st.session_state.origin = quote_info.get("origin", "")
                        st.session_state.cargo_date = datetime.strptime(
                            quote_info.get("cargoReadinessDate", "2025-01-01"), "%Y-%m-%d"
                        )
                        st.session_state.multidest = quote_info.get("multidest", [])
                        st.session_state.fbaOCC = quote_info.get("fbaOCC", "")
                        st.session_state.fbaDCC = quote_info.get("fbaDCC", "")
                        st.session_state.fba = quote_info.get("fba", "")
                        st.session_state.form_data_loaded = True

            except Exception as e:
                st.error(f"❌ Unexpected error while loading quote: {str(e)}")


        # ----------- Booking Form ------------
        with st.form("shipment_form"):
            r1c1, r1c2, r1c3 = st.columns([1.5, 1, 1.5])
            with r1c1:
                st.text_input("Customer Name", value=st.session_state.get("entityName", ""), disabled=True)
                st.toggle("isFBA", value=True if st.session_state.get("fba", "").lower() == "yes" else False, disabled=True)
            with r1c2:
                st.date_input("Cargo Readiness Date", value=st.session_state.get("cargo_date", datetime.today()), disabled=True)
                st.toggle("OCC", value=True if st.session_state.get("fbaOCC", "").lower() == "yes" else False, disabled=True)
            with r1c3:
                st.text_input("Scope", value=st.session_state.get("scope", ""), disabled=True)
                st.toggle("DCC", value=True if st.session_state.get("fbaDCC", "").lower() == "yes" else False, disabled=True)

            orc1, desc2 = st.columns(2)
            with orc1:
                st.text_input("Origin", st.session_state.get("origin", ""), disabled=True)
            with desc2:
                dests = st.session_state.get("multidest", [])
                if len(dests) > 1:
                    destination_value = "Multiple"
                    des_val = "Multiple"
                elif len(dests) == 1:
                    des_val = "Single"
                    destination_value = dests[0].get("destination", "")
                else:
                    destination_value = ""
                st.text_input("Destination(s)", value=destination_value, disabled=True)

            for idx, dest_entry in enumerate(dests):
                dest = dest_entry.get("destination", "Unknown Destination")
                cargo_list = dest_entry.get("cargoDetails", [])

                st.markdown(f"#### 📍 Destination {idx + 1}: `{dest}`")

                total_weight_all = 0.0
                total_volume_all = 0.0

                for row_idx, cargo in enumerate(cargo_list):
                    weight_val = safe_float(cargo.get("wtPerPackage", 0.0))
                    length_val = safe_float(cargo.get("length", 0.0))
                    width_val = safe_float(cargo.get("width", 0.0))
                    height_val = safe_float(cargo.get("height", 0.0))
                    quantity_val = safe_int(cargo.get("numPackages", 0))
                    pkg_type = cargo.get("packageType", "")

                    total_weight = safe_float(cargo.get("totalWeight", 0.0))
                    total_volume = safe_float(cargo.get("totalVolume", 0.0))

                    total_weight_all += total_weight
                    total_volume_all += total_volume

                    col1, col2, col3, col4, col5, col6 = st.columns([1.5, 1, 1.5, 1, 1, 1])
                    with col1:
                        st.text_input("Package Type*", pkg_type, key=f"pkg_{idx}_{row_idx}", disabled=True)
                    with col2:
                        st.number_input("Quantity*", min_value=1, value=quantity_val, key=f"qty_{idx}_{row_idx}", disabled=True)
                    with col3:
                        st.number_input(f"Weight*", min_value=0.0, value=weight_val, key=f"wt_{idx}_{row_idx}", disabled=True)
                    with col4:
                        st.number_input(f"L", min_value=0.0, value=length_val, key=f"l_{idx}_{row_idx}", disabled=True)
                    with col5:
                        st.number_input(f"W", min_value=0.0, value=width_val, key=f"w_{idx}_{row_idx}", disabled=True)
                    with col6:
                        st.number_input(f"H", min_value=0.0, value=height_val, key=f"h_{idx}_{row_idx}", disabled=True)

                    st.markdown(
                        f"**Total Weight:** `{total_weight}` &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; "
                        f"**Total Volume:** `{total_volume}`",
                        unsafe_allow_html=True
                    )

                st.markdown(
                    f"✅ **Grand Total Weight:** `{total_weight_all}` "
                    f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; "
                    f"**Grand Total Volume:** `{total_volume_all}`",
                    unsafe_allow_html=True
                )

            col_oc, col_cl = st.columns(2)
            with col_oc:
                is_own_console = st.checkbox("Own Console", key="own_console")
            with col_cl:
                is_co_load = st.checkbox("Co Load", key="co_load")

            col_ltl, col_ftl, col_ftl53, col_dry = st.columns(4)
            with col_ltl:
                is_ltl = st.checkbox("LTL", key="ltl")
            with col_ftl:
                is_ftl = st.checkbox("FTL", key="ftl")
            with col_ftl53:
                is_ftl53 = st.checkbox("FTL53", key="ftl53")
            with col_dry:
                is_dry = st.checkbox("Drayage", key="drayage")
            
            pickup_charges = 0.0  # Default
            shipment_scope = st.session_state.get("scope", "")
            if shipment_scope == 'Door-to-Door':
                pickup_charges = st.number_input("Enter Pickup Charges (USD)", min_value=0.0, step=10.0)

            submit = st.form_submit_button("🔎 Get Rates")

    with right_col:
        if submit:
            if not quote_id:
                st.warning("⚠️ Please enter a valid Ag Quote No. before requesting rates.")
            elif not st.session_state.form_data_loaded:
                st.warning("⚠️ Please load the quote details first by entering a valid quote ID.")
            else:
                if is_own_console and not is_co_load:
                    console_type = "Own Console"
                elif is_co_load and not is_own_console:
                    console_type = "Coload"
                elif is_own_console and is_co_load:
                    console_type = "both selected"
                else:
                    console_type = "not selected"

                service_modes = []
                if is_ltl:
                    service_modes.append("LTL")
                if is_ftl:
                    service_modes.append("FTL")
                if is_ftl53:
                    service_modes.append("FTL53")
                if is_dry:
                    service_modes.append("Drayage")

                is_occ = st.session_state.get("fbaOCC", "").lower() == "yes"
                is_dcc = st.session_state.get("fbaDCC", "").lower() == "yes"
                origin = st.session_state.get("origin", "")

                st.success("✅ Getting rates based on provided inputs...")
                cleaned_data = remove_ids(st.session_state.multidest)

                # ✅ Updated call with error handling
                result, errors = rates(
                    origin,
                    cleaned_data,
                    console_type,
                    is_occ,
                    is_dcc,
                    des_val,
                    service_modes,
                    shipment_scope,
                    pickup_charges
                )

                # st.json(result)

                # ✅ Show errors if any
                if errors:
                    st.warning("⚠️ Some issues occurred during rate calculation:")
                    for msg in errors:
                        st.markdown(f"- {msg}")

                log_rate_request(quote_id, console_type, service_modes, result, errors)

                if result and not errors:
                    # Show success message again if you like
                    st.success("✅ Rate calculation successful. Showing breakdown:")

                    quotations_backup(quote_id,result)  # 💾 Save backup

                    # ✅ Show rate breakdowns if available
                    for idx, destination in enumerate(result):
                        dest_info = result[destination]
                        st.markdown(f"📍 Destination {idx + 1}: `{destination}`")

                        with st.container(border=True):
                            route_count = 1

                            for console_key in ["Own Console", "Coload"]:
                                if console_key in dest_info:
                                    data = dest_info[console_key]

                                    origin = data.get("Origin", "")
                                    pol = data.get("POL", "")
                                    pod = data.get("POD", "")
                                    fba = data.get("FBA Code", "")
                                    shipmentscope = data.get("Shipment Scope","")
                                    cbm_cost = data.get("Total per cbm", "N/A")
                                    if shipmentscope == "Port-to-Door":
                                        route_parts = [p for p in [origin, pod, fba] if p]
                                    else:
                                        route_parts = [p for p in [origin, pol, pod, fba] if p]
                                    route_str = " → ".join(route_parts)

                                    with st.expander(f'Route {route_count}', expanded=True):
                                        st.markdown(f"**🚚 Console Type:** {console_key}")
                                        st.markdown(f"**📍 Route:** {route_str}")
                                        st.markdown(f"**💰 Total Cost / CBM:** ${cbm_cost}")

                                        col1, col2 = st.columns([1, 1])
                                        with col1:
                                            st.button("💾 Save Quote", key=f"save_{idx}_{console_key}")
                                        with col2:
                                            st.button("🔍 Review Quote", key=f"review_{idx}_{console_key}")

                                        # Totals
                                        total_keys = ["Total Weight", "Total CBM", "Total Pallets", "category"]
                                        total_rows = [(key, data[key]) for key in total_keys if key in data]
                                        if total_rows:
                                            st.dataframe(pd.DataFrame(total_rows, columns=["Feild", "Value"]), use_container_width=True, hide_index=True)
                                        else:
                                            st.info("ℹ️ No total breakdown available.")

                                        # Rate breakdown
                                        rate_keys = [
                                            "Pick-Up Charges", "P2P Charge", "Selected lm",
                                            "OCC", "DCC", "Documentation", "Palletization Cost", "Total Cost", "Total per cbm"
                                        ]
                                        rate_rows = []
                                        for key in rate_keys:
                                            if key in data:
                                                value = data[key]
                                                if key == "Selected lm" and isinstance(value, dict):
                                                    rate_rows.append(("Last mile Rate", value.get("Rate", "N/A")))
                                                    rate_rows.append(("Last mile Rate Type", value.get("Rate Type", "N/A")))
                                                    rate_rows.append(("Last mile Service Provider", value.get("Service Provider", "N/A")))
                                                else:
                                                    rate_rows.append((key, value))
                                        if rate_rows:
                                            st.dataframe(pd.DataFrame(rate_rows, columns=["Charge Head", "Value"]), use_container_width=True, hide_index=True)
                                        else:
                                            st.info("ℹ️ No pricing breakdown available.")

                                    route_count += 1







