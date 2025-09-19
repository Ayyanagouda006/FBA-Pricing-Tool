import streamlit as st
import requests
import pandas as pd
from streamlit_searchbox import st_searchbox  # pip install streamlit-searchbox
import time
from math import ceil
from datetime import datetime
from pricing_calculation import rates_comparison
import os

def get_address(zip_code: str):
    if not zip_code:
        return []

    url = f"https://office-dev.agraga.com/api/api/v1/location/fetchfulladdress2/{zip_code},"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list) and len(data) > 0:
            results, new_rows = [], []
            for entry in data:
                city = entry.get('city', '')
                state = entry.get('state', '')
                state_code = entry.get('stateCode', '')
                country = entry.get('country', '')
                zip_val = entry.get('pin', zip_code)

                results.append(f"{zip_val}, {city}, {state}, {state_code}, {country}")

            return results
        return []
    except requests.exceptions.RequestException:
        return []
    

LOG_FILE = r"Logs/transport_rates_log.xlsx"

def trans_rates(data):
    errors = []
    log_row = {
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Origin": data.get("Origin", ""),
        "Destination": data.get("Destination", ""),
        "Success Rate": "No",
        "LTL": "",
        "FTL": "",
        "FTL53": "",
        "Drayage": "",
        "Quoted Result": "",
        "Error": ""
    }

    try:
        origin_address = data.get("Origin", "")
        destination_address = data.get("Destination", "")
        cargo_details = data.get("CargoDetails", [])

        # ✅ Split safely into 5 parts
        try:
            origin_zip, origin_city, origin_state, origin_stcode, origin_country = [
                part.strip() for part in origin_address.split(",")
            ]
        except Exception:
            errors.append(f"❌ Invalid Origin format: {origin_address}")
            origin_zip = origin_city = origin_state = origin_stcode = origin_country = ""

        try:
            destination_zip, destination_city, destination_state, destination_stcode, destination_country = [
                part.strip() for part in destination_address.split(",")
            ]
        except Exception:
            errors.append(f"❌ Invalid Destination format: {destination_address}")
            destination_zip = destination_city = destination_state = destination_stcode = destination_country = ""

        qty = 0
        weight = 0.0
        pallets = 0
        loose_cbm = 0.0
        total_cbm = 0.0

        for item in cargo_details:
            try:
                package = str(item.get("package_type", "")).strip()
                item_qty = int(item.get("qty", 0))
                item_wtppack = float(item.get("weight", 0.0))
                item_weight = item_qty * item_wtppack

                length = float(item.get("L", 0.0))
                width = float(item.get("W", 0.0))
                height = float(item.get("H", 0.0))
                vol = (length * width * height) / 1000000
                item_cbm = item_qty * vol

                qty += item_qty
                weight += item_weight
                total_cbm += item_cbm

                if package.lower() == "pallets":
                    pallets += item_qty
                else:
                    loose_cbm += item_cbm

            except Exception as e:
                errors.append(f"❌ Error parsing cargo row {item}: {e}")
                continue

        loose_as_pallets = ceil(loose_cbm / 1.8) if loose_cbm > 0 else 0
        total_pallet_count = pallets + loose_as_pallets

        if total_cbm >= 50:
            category = "HOT"
            services = ["Drayage"]
        else:
            category = "NON HOT"
            services = ["FTL", "FTL53", "LTL"]

        dt_str = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_id = f"TRANSPORT_RATES_{dt_str}"

        try:
            ltl, ftl, ftl53, drayage, lowest, selected_lowest = rates_comparison(
                origin_city, origin_stcode, origin_zip, "-",
                destination_city, destination_stcode, destination_zip,
                total_pallet_count, weight, category, services, "-", unique_id
            )
            log_row.update({
                "Success Rate": "Yes",
                "LTL": ltl,
                "FTL": ftl,
                "FTL53": ftl53,
                "Drayage": drayage,
                "Quoted Result": selected_lowest
            })
        except Exception as e:
            errors.append(f"❌ Error fetching rates: {e}")
            selected_lowest = {}

    except Exception as e:
        errors.append(f"❌ Unexpected error in trans_rates: {e}")
        selected_lowest = {}

    # Log errors if any
    if errors:
        log_row["Error"] = "; ".join(errors)

    # ✅ Append to Excel log
    df_new = pd.DataFrame([log_row])
    if os.path.exists(LOG_FILE):
        df_existing = pd.read_excel(LOG_FILE)
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
    else:
        df_combined = df_new
    df_combined.to_excel(LOG_FILE, index=False)

    return {"result": selected_lowest, "errors": errors}



def trans_cal():
    with st.container():
        # ---- Two main columns: Left (origin/dest) | Right (cargo details) ---- #
        left, right = st.columns([1, 2])

        # ================= LEFT SIDE ================= #
        with left:
            origin_selection = st_searchbox(
                label="Select Origin *",
                search_function=get_address,
                placeholder="Choose Origin",
                key="origin_key"
            )

            dest_selection = st_searchbox(
                label="Select Destination *",
                search_function=get_address,
                placeholder="Choose Destination",
                key="dest_key"
            )

        # ================= RIGHT SIDE ================= #
        with right:
            st.subheader("📦 Cargo Details")
            # Cargo rows in session state
            if "cargo_rows" not in st.session_state:
                st.session_state.cargo_rows = [
                    {"package_type": "Loose Cartons", "qty": 0, "weight": 0, "L": 0, "W": 0, "H": 0}
                ]

            rows = st.session_state.cargo_rows
            new_rows = []

            for i, row in enumerate(rows):
                col1, col2, col3, col4, col5, col6, col7 = st.columns([2,1,2,1,1,1,1])

                with col1:
                    package_type = st.selectbox(
                        "Package Type*",
                        ["Loose Cartons", "Pallets"],
                        key=f"pkg_{i}",
                        index=["Loose Cartons", "Pallets"].index(row["package_type"])
                    )
                with col2:
                    qty = st.number_input("Quantity *", min_value=0, step=1,
                                        key=f"qty_{i}", value=int(row["qty"]))
                with col3:
                    weight = st.number_input("Weight per package * (Kgs)", min_value=0.0, step=1.0,
                                            key=f"wt_{i}", value=float(row["weight"]))
                with col4:
                    L = st.number_input("L (in)", min_value=0.0, step=1.0,
                                        key=f"L_{i}", value=float(row["L"]))
                with col5:
                    W = st.number_input("W (in)", min_value=0.0, step=1.0,
                                        key=f"W_{i}", value=float(row["W"]))
                with col6:
                    H = st.number_input("H (in)", min_value=0.0, step=1.0,
                                        key=f"H_{i}", value=float(row["H"]))
                with col7:
                    if st.button("🗑️", key=f"del_{i}"):
                        st.session_state.cargo_rows.pop(i)
                        st.rerun()   # 👈 force refresh immediately

                new_rows.append({
                    "package_type": package_type, "qty": qty, "weight": weight,
                    "L": L, "W": W, "H": H
                })

            st.session_state.cargo_rows = new_rows

            if st.button("➕ Add Row"):
                st.session_state.cargo_rows.append(
                    {"package_type": "Loose Cartons", "qty": 0, "weight": 0, "L": 0, "W": 0, "H": 0}
                )
                st.rerun()  # 👈 force refresh immediately

            # Totals
            total_weight = sum(r["qty"] * r["weight"] for r in st.session_state.cargo_rows)
            total_volume_cbm = sum(
                r["qty"] * ((r["L"] * r["W"] * r["H"]) / 1000000)
                for r in st.session_state.cargo_rows
            )

            st.markdown(f"""
            <div style="font-size:16px; margin-top:10px;">
            <b style="color:orange;">Grand Total Weight:</b> {total_weight} Kgs &nbsp;&nbsp;&nbsp;&nbsp;
            <b style="color:orange;">Grand Total Volume:</b> {total_volume_cbm:.2f} CBM
            </div>
            """, unsafe_allow_html=True)

            # Action buttons
            col1, col2 = st.columns([1,1])
            with col1:
                # st.button("Clear")
                pass
            with col2:
                submit = st.button("Get Rates", type="primary")

    if submit:
        start_time = time.time()
        payload = {
            "Origin": origin_selection,
            "Destination": dest_selection,
            "CargoDetails": st.session_state.cargo_rows,
            "Totals": {
                "Weight": total_weight,
                "VolumeCBM": round(total_volume_cbm, 2)
            }
        }

        st.markdown("---")
        with st.spinner("🔎 Getting rates based on provided inputs..."):
            response = trans_rates(payload)
            result = response["result"]
            errors = response["errors"]

        elapsed_time = round(time.time() - start_time, 2)
        st.success(f"✅ Done in {elapsed_time} seconds")

        # ⚠️ Show warnings if any
        if errors:
            st.warning("⚠️ Some issues were detected while processing:")
            for err in errors:
                st.text(err)

        # 📊 Show results only if available
        if result:
            st.markdown("### 📊 Best Available Rate")

            # Big rate highlight
            st.markdown(
                f"""
                <div style="
                    text-align:center;
                    padding:20px;
                    border-radius:12px;
                    background:linear-gradient(135deg, #f6d365 0%, #fda085 100%);
                    color:white;
                    font-size:24px;
                    font-weight:bold;">
                    💰 ${result.get("Rate","-"):,.2f}
                </div>
                """,
                unsafe_allow_html=True
            )

            # Details in two columns
            left, right = st.columns(2)
            with left:
                st.metric("Rate Type", result.get("Rate Type", "-"))
                st.metric("Carrier", result.get("Carrier Name", "-"))
                st.metric("Service Provider", result.get("Service Provider", "-"))
            with right:
                st.metric("Source", result.get("Source", "-"))
                st.metric("Date", result.get("Date", "-"))
        else:
            st.error("❌ No valid rates found. Please check inputs.")




