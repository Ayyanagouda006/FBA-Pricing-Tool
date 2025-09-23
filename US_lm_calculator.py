import streamlit as st
import requests
import pandas as pd
from streamlit_searchbox import st_searchbox  # pip install streamlit-searchbox
import time
from math import ceil
from datetime import datetime
from heyprimo import heyprimo_api
from exfreight import exfreight_api
from jbhunt import jbhunt_api
import os

LOG_FILE = r"Logs/transport_rates_log.xlsx"

def log_trans_rates(data, results):
    """
    Append input/output data of trans_rates into an Excel log file.
    """
    try:
        # Flatten main fields for readability
        log_entry = {
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Origin": data.get("Origin", ""),
            "Destination": data.get("Destination", ""),
            "DataType": data.get("DataType", ""),
            "Totals_Weight": data.get("Totals", {}).get("Weight", ""),
            "Totals_VolumeCBM": data.get("Totals", {}).get("VolumeCBM", ""),
            "CargoDetails": str(data.get("CargoDetails", "")),   # save as string
            "Toggles": str(data.get("Toggles", "")),             # save as string
            "LTL": str(results.get("LTL", {})),
            "FTL": str(results.get("FTL", {})),
            "FTL53": str(results.get("FTL53", {})),
            "Drayage": str(results.get("Drayage", {})),
            "Errors": "; ".join(results.get("errors", []))
        }

        df_new = pd.DataFrame([log_entry])

        if os.path.exists(LOG_FILE):
            # Append to existing log
            with pd.ExcelWriter(LOG_FILE, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
                # Find existing rows to append correctly
                existing = pd.read_excel(LOG_FILE)
                startrow = len(existing) + 1
                df_new.to_excel(writer, index=False, header=False, startrow=startrow, sheet_name="Logs")
        else:
            # Create new file with headers
            df_new.to_excel(LOG_FILE, index=False, sheet_name="Logs")

    except Exception as e:
        print(f"❌ Failed to log data: {e}")


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
    
# --- Check if origin/destination is in the US ---
def is_us_location(location: str) -> bool:
    parts = [p.strip().lower() for p in location.split(",")]
    return any(p in ["united states", "us", "usa"] for p in parts)



def ltl_rate(fpod_city, fpod_st_code, fpod_zip, fba_code, fba_city, fba_st_code, fba_zip, qty, weight,quote_id,unique_id,toggels):
    # Read offline last mile rates
    lm = pd.read_excel(r"Data/Last Mile Rates (no api).xlsx", "Last Mile Rates (no api)")
    lm = lm[lm['Delivery Type'] == "LTL"]

    fba = toggels.get("FBA",False)
    LiftgateRequired = toggels.get('LiftgateRequired',False)
    ResidentialDelivery = toggels.get('ResidentialDelivery',False)
    if not fba or fba == 'false':
        if LiftgateRequired and ResidentialDelivery:
            eaccessorialslist=[{"category": "lift_gate", "scope": "at_delivery"}, {"category": "residential", "scope": "at_delivery"}]
            accessorials = ["LFO", "RSD"]
        elif ResidentialDelivery:
            eaccessorialslist=[{"category": "residential", "scope": "at_delivery"}]
            accessorials = ["RSD"]
    else:
        eaccessorialslist=[{"category": "amazon_fba_delivery", "scope": "at_delivery"}, {"category": "ocean_cfs_pickup", "scope": "at_pickup"}]
        haccessorials = ["APD", "CTO"]

    # Step 1: Get API results
    hp_result = heyprimo_api({
        "Origin City": fpod_city,
        "Origin State Code": fpod_st_code,
        "Origin ZIP": fpod_zip,
        "Destn City": fba_city,
        "Destn State Code": fba_st_code,
        "FBA Code": fba_code,
        "FBA or Destination ZIP": fba_zip,
        "Num Of Pallet": qty,
        "quote_id":quote_id,
        'unique id':unique_id
    })


    
    ef_result = exfreight_api(fpod_zip, fba_code, fba_zip, weight, qty, quote_id, unique_id, eaccessorialslist)

    # Step 2: Parse rates from API safely
    candidates = []

    if isinstance(hp_result, dict) and "Lowest Rate" in hp_result:
        candidates.append({
            "Rate Type": "LTL",
            "Rate": round(float(hp_result["Lowest Rate"]), 2),
            "Carrier Name": hp_result.get("Carrier Name", ""),
            "Service Provider": "HeyPrimo",
            "Source": hp_result.get("Source", ""),   # safe default
            "Date": hp_result.get("Date", "")
        })


    if isinstance(ef_result, dict) and "Lowest Rate" in ef_result:
        candidates.append({
            "Rate Type": "LTL",
            "Rate": round(float(ef_result["Lowest Rate"]), 2),
            "Carrier Name": ef_result.get("Carrier Name", ""),
            "Service Provider": "Ex-Freight",
            "Source": ef_result.get("Source", ""),   # ✅ use ef_result not hp_result
            "Date": ef_result.get("Date", "")
        })


    # Step 3: Find offline Excel rates (exact match by zip + pallet count)
    try:
        today = pd.to_datetime(datetime.today().strftime("%d-%m-%Y"), format="%d-%m-%Y")
        lm["Valid From"] = pd.to_datetime(lm["Valid From"], format="%d-%m-%Y", errors="coerce")
        lm["Valid To"] = pd.to_datetime(lm["Valid To"], format="%d-%m-%Y", errors="coerce")
        offline_match = lm[
            (lm['FPOD ZIP'].astype(str).str.zfill(5) == str(fpod_zip).zfill(5)) &
            (lm['FBA ZIP'].astype(str).str.zfill(5) == str(fba_zip).zfill(5)) &
            (lm['No. of pallets'] == qty) &
            (lm['Valid From'] <= today) & (lm['Valid To'] >= today)
        ]

        for _, row in offline_match.iterrows():
            candidates.append({
                "Rate Type": "LTL",
                "Rate": round(float(row['Rate']), 2),
                "Carrier Name": row['Carrier Name'] if not pd.isna(row['Carrier Name']) else "",
                "Service Provider": row["Broker"] if not pd.isna(row['Broker']) else "",
                "Source":"No API STATIC DATA",
                "Date": row['Date Modified'].strftime("%d-%m-%Y") if not pd.isna(row['Date Modified']) else ""
            })
    except Exception as e:
        print("Error matching offline Excel rate:", e)

    # Step 4: Pick the lowest rate
    if candidates:
        return candidates
    else:
        return None
    
def ftl_rate(fpod_zip, fba_code, fba_zip, qty, quote_id,unique_id):
    lm = pd.read_excel(r"Data/Last Mile Rates (no api).xlsx", "Last Mile Rates (no api)")
    today = pd.to_datetime(datetime.today().strftime("%d-%m-%Y"), format="%d-%m-%Y")
    lm["Valid From"] = pd.to_datetime(lm["Valid From"], format="%d-%m-%Y", errors="coerce")
    lm["Valid To"] = pd.to_datetime(lm["Valid To"], format="%d-%m-%Y", errors="coerce")

    # Separate FTL and FTL53 sheets
    lm_ftl = lm[lm['Delivery Type'] == "FTL"]
    lm_ftl53 = lm[lm['Delivery Type'] == "FTL53"]

    ftl_cand = []
    ftl_match = lm_ftl[
        (lm_ftl['FPOD ZIP'].astype(str).str.zfill(5) == str(fpod_zip).zfill(5)) &
        (lm_ftl['FBA ZIP'].astype(str).str.zfill(5) == str(fba_zip).zfill(5)) &
        (lm_ftl['Valid From'] <= today) & (lm_ftl['Valid To'] >= today)
    ]

    for _, row in ftl_match.iterrows():
        ftl_cand.append({
            "Rate Type": "FTL",
            "Rate": round(float(row['Rate']), 2),
            "Carrier Name": row['Carrier Name'] if not pd.isna(row['Carrier Name']) else "",
            "Service Provider": row["Broker"] if not pd.isna(row['Broker']) else "",
            "Source":"No API STATIC DATA",
            "Date": row['Date Modified'].strftime("%d-%m-%Y") if not pd.isna(row['Date Modified']) else ""
        })

    ftl_jb = jbhunt_api(fpod_zip, fba_code, fba_zip, "11024", quote_id,unique_id,"FTL")
    ftl_cand.append(ftl_jb)

    ftl53_cand = []
    ftl53_match = lm_ftl53[
        (lm_ftl53['FPOD ZIP'].astype(str).str.zfill(5) == str(fpod_zip).zfill(5)) &
        (lm_ftl53['FBA ZIP'].astype(str).str.zfill(5) == str(fba_zip).zfill(5)) &
        (lm_ftl53['Valid From'] <= today) & (lm_ftl53['Valid To'] >= today)
    ]

    for _, row in ftl53_match.iterrows():
        ftl53_cand.append({
            "Rate Type": "FTL53",
            "Rate": round(float(row['Rate']), 2),
            "Carrier Name": row['Carrier Name'] if not pd.isna(row['Carrier Name']) else "",
            "Service Provider": row["Broker"] if not pd.isna(row['Broker']) else "",
            "Source":"No API STATIC DATA",
            "Date": row['Date Modified'].strftime("%d-%m-%Y") if not pd.isna(row['Date Modified']) else ""
        })

    ftl53_jb = jbhunt_api(fpod_zip, fba_code, fba_zip, "45000", quote_id,unique_id,"FTL53")
    ftl53_cand.append(ftl53_jb)

    return ftl_cand, ftl53_cand

def trans_rates(data):
    errors = []
    
    # --- Default results ---
    ltl, ftl, ftl53, drayage = {}, {}, {}, {}

    try:
        origin_address = data.get("Origin", "")
        destination_address = data.get("Destination", "")
        cargo_details = data.get("CargoDetails", [])
        toggles = data.get("Toggles", {})
        datatype = data.get("DataType", "")
                        

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

        if datatype == "Totals":
            totals = data.get("Totals", {})
            weight = float(totals.get("Weight",0.0))
            cbm = float(totals.get("VolumeCBM",0.0))
            total_pallet_count = ceil(cbm / 1.8) if cbm > 0 else 0

        elif datatype == "CargoDetails":
            qty = 0
            weight = 0.0
            pallets = 0
            loose_cbm = 0.0
            total_cbm = 0.0
            # --- Cargo loop ---
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

            # --- Palletization ---
            loose_as_pallets = ceil(loose_cbm / 1.8) if loose_cbm > 0 else 0
            total_pallet_count = pallets + loose_as_pallets

        # --- Unique request ID ---
        dt_str = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_id = f"TRANSPORT_RATES_{dt_str}"

        # --- API calls ---
        try:
            ltl = ltl_rate(
                origin_city, origin_stcode, origin_zip, "-",
                destination_city, destination_stcode, destination_zip,
                total_pallet_count, weight, "-", unique_id, toggles
            )
        except Exception as e:
            errors.append(f"❌ Error fetching LTL rate: {e}")

        try:
            ftl, ftl53 = ftl_rate(
                origin_zip, "-", destination_zip,
                total_pallet_count, "-", unique_id
            )
        except Exception as e:
            errors.append(f"❌ Error fetching FTL/FTL53 rates: {e}")

        try:
            drayage = jbhunt_api(
                origin_zip, "-", destination_zip,
                "45000", "-", unique_id, "Drayage"
            )
        except Exception as e:
            errors.append(f"❌ Error fetching Drayage rate: {e}")

    except Exception as e:
        errors.append(f"❌ Unexpected error in trans_rates: {e}")

    # --- Return structured results ---
    results = {
        "LTL": ltl,
        "FTL": ftl,
        "FTL53": ftl53,
        "Drayage": drayage,
        "errors": errors
    }

    log_trans_rates(data, results)  # ✅ log inputs + outputs

    return results


def trans_cal():
    with st.container():
        # ---- Two main columns: Left (origin/dest) | Right (cargo details) ---- #
        left, right = st.columns([1, 2])

        # ================= LEFT SIDE ================= #
        with left:
            st.subheader("🛣️ Route")
            with st.container(border=True):
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

            # ---- Toggles ---- #
            with st.container(border=True):

                # FBA toggle (default ON)
                fba_toggle = st.toggle("FBA", value=True, key="fba_toggle")

                liftgate_required, residential_delivery = False, False
                if not fba_toggle:
                    # Liftgate Required toggle
                    liftgate_required = st.toggle("Liftgate Required?", value=False, key="liftgate_toggle")

                    # If Liftgate is ON → Residential auto ON and disabled
                    if liftgate_required:
                        residential_delivery = True
                        st.toggle("Residential Delivery?", value=True, disabled=True, key="residential_toggle_locked")
                    else:
                        residential_delivery = st.toggle("Residential Delivery?", value=False, key="residential_toggle_free")

        # ================= RIGHT SIDE ================= #
        with right:
            st.subheader("📦 Cargo Details")
            with st.container(border=True):
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
                        if st.button("Delete", key=f"del_{i}"):
                            st.session_state.cargo_rows.pop(i)
                            st.rerun()

                    new_rows.append({
                        "package_type": package_type, "qty": qty, "weight": weight,
                        "L": L, "W": W, "H": H
                    })

                st.session_state.cargo_rows = new_rows

                if st.button("➕ Add Row"):
                    st.session_state.cargo_rows.append(
                        {"package_type": "Loose Cartons", "qty": 0, "weight": 0, "L": 0, "W": 0, "H": 0}
                    )
                    st.rerun()

                total_weight = sum(r["qty"] * r["weight"] for r in st.session_state.cargo_rows)
                total_volume_cbm = sum(
                    r["qty"] * ((r["L"] * r["W"] * r["H"]) / 1000000)
                    for r in st.session_state.cargo_rows
                )

                total_pallets = 0
                total_palletization = 0
                for r in st.session_state.cargo_rows:
                    if r["package_type"] == "Loose Cartons":
                        row_cbm = r["qty"] * ((r["L"] * r["W"] * r["H"]) / 1000000)
                        pallets_for_row = ceil(row_cbm / 1.8) if row_cbm > 0 else 0
                        total_pallets += pallets_for_row
                        palletization = total_pallets * 20
                        total_palletization += palletization
                    elif r["package_type"] == "Pallets":
                        total_pallets += r["qty"]   

                st.markdown(
                    f"""
                    <div style="font-size:16px; margin-top:10px; display:flex; gap:30px;">
                        <div><b style="color:orange;">Grand Total Weight:</b> {total_weight} Kgs</div>
                        <div><b style="color:orange;">Grand Total Volume:</b> {total_volume_cbm:.2f} CBM</div>
                        <div><b style="color:orange;">Total Pallets:</b> {total_pallets}</div>
                        <div><b style="color:orange;">Palletization Cost:</b> ${total_palletization:.2f}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )


            st.markdown(
                "<div style='display:flex; justify-content:center; align-items:center; height:100%; font-weight:bold;'>OR</div>",
                unsafe_allow_html=True,
            )

            # --- Totals section --- #
            with st.container(border=True):
                tcol1, tcol2, tcol3, tcol4 = st.columns([2,1,1,1])
                with tcol1:
                    tpackage_type = st.selectbox(
                        "Package Type*",
                        ["Loose Cartons"],
                        key=f"tpkg",
                        index=0)
                    
                with tcol2:
                    tqty = st.number_input("Total Quantity *", min_value=0, step=1, key="tqty")
                with tcol3:
                    tweight = st.number_input("Total Weight (Kgs)", min_value=0.0, step=1.0, key="twt")
                with tcol4:
                    tvolume = st.number_input("Total Volume (CBM)", min_value=0.0, step=0.01, key="tvolume")


                tpallets = ceil(tvolume / 1.8) if tvolume > 0 else 0
                tpalletization = tpallets * 20 if tpallets > 0 else 0

                st.markdown(f""" <div style="font-size:16px; margin-top:10px;"> 
                            <b style="color:orange;">Total Pallets:</b> {tpallets} &nbsp;&nbsp;&nbsp;&nbsp; 
                            <b style="color:orange;">Palletization Cost:</b> ${tpalletization:.2f} </div> """, unsafe_allow_html=True) 

            # Action button
            submit = st.button("Get Rates", type="primary")

    # ================= SUBMIT HANDLING ================= #
    if submit:
        # --- Validation: Route ---
        if not origin_selection:
            st.error("⚠️ Please select an Origin before proceeding.")
            return
        if not dest_selection:
            st.error("⚠️ Please select a Destination before proceeding.")
            return
        
        if origin_selection.strip().lower() == dest_selection.strip().lower():
            st.error("⚠️ Origin and Destination cannot be the same.")
            return
        
        if not is_us_location(origin_selection):
            st.error("⚠️ Origin must be in the United States.")
            return
        if not is_us_location(dest_selection):
            st.error("⚠️ Destination must be in the United States.")
            return
        
        detailed_used = any(
            r["qty"] > 0 or r["weight"] > 0 or r["L"] > 0 or r["W"] > 0 or r["H"] > 0
            for r in st.session_state.cargo_rows
        )
        totals_used = (tqty > 0 or tweight > 0 or tvolume > 0)

        # --- Validation ---
        if detailed_used and totals_used:
            st.error("❌ Please provide either detailed cargo rows OR totals — not both.")
            return

        if not detailed_used and not totals_used:
            st.error("⚠️ Please provide cargo details or totals before proceeding.")
            return

        # --- If totals used, validate ---
        if totals_used:
            if tqty <= 0:
                st.error("⚠️ Total Quantity must be greater than zero.")
                return
            if tweight <= 0:
                st.error("⚠️ Total Weight must be greater than zero.")
                return
            if tvolume <= 0:
                st.error("⚠️ Total Volume must be greater than zero.")
                return

        # --- If detailed used, validate ---
        if detailed_used:
            for idx, r in enumerate(st.session_state.cargo_rows, start=1):
                if r["qty"] <= 0:
                    st.error(f"⚠️ Row {idx}: Quantity must be greater than zero.")
                    return
                if r["weight"] <= 0:
                    st.error(f"⚠️ Row {idx}: Weight must be greater than zero.")
                    return
                if r["L"] <= 0 or r["W"] <= 0 or r["H"] <= 0:
                    st.error(f"⚠️ Row {idx}: Dimensions (L, W, H) must be greater than zero.")
                    return
                
        # --- Build payload ---
        start_time = time.time()
        # 🚀 Continue with rate fetching
        st.markdown("---")
        with st.spinner("✅ Getting rates based on provided inputs...",show_time = True):
        # --- Common toggle info ---
            toggle_info = {
                "FBA": fba_toggle,
                "LiftgateRequired": liftgate_required,
                "ResidentialDelivery": residential_delivery
            }

            if totals_used:
                payload = {
                    "DataType": "Totals",
                    "Origin": origin_selection,
                    "Destination": dest_selection,
                    "Totals": {
                        "package_type": tpackage_type,
                        "Total quantity": tqty,
                        "Weight": tweight,
                        "VolumeCBM": tvolume
                    },
                    "Toggles": toggle_info
                }
            else:
                payload = {
                    "DataType": "CargoDetails",
                    "Origin": origin_selection,
                    "Destination": dest_selection,
                    "CargoDetails": st.session_state.cargo_rows,
                    "Totals": {
                        "Weight": total_weight,
                        "VolumeCBM": round(total_volume_cbm, 2)
                    },
                    "Toggles": toggle_info
                }
            
            response = trans_rates(payload)

        end_time = time.time()
        elapsed_time = end_time - start_time

        minutes = int(elapsed_time // 60)
        seconds = round(elapsed_time % 60, 2)

        st.success(f"✅ Done! Execution completed in {minutes} minutes, {seconds} seconds.")

        # --- Errors ---
        if response["errors"]:
            st.error("⚠️ Some errors occurred during rate fetching:")
            for e in response["errors"]:
                st.markdown(f"- {e}")

        # --- Results ---
        st.subheader("📊 Transport Rates")

        with st.expander("🚛 Less Than Truckload (LTL)", expanded=True):
            if response["LTL"] is not None and not response["LTL"] == {}:
                st.dataframe(response["LTL"], use_container_width=True)
            else:
                st.info("ℹ️ No LTL rates found.")

        with st.expander("🏗️ Full Truckload (FTL)", expanded=False):
            if response["FTL"] is not None and not response["FTL"] == {}:
                st.dataframe(response["FTL"], use_container_width=True)
            else:
                st.info("ℹ️ No FTL rates found.")

        with st.expander("📦 Full Truckload 53’", expanded=False):
            if response["FTL53"] is not None and not response["FTL53"] == {}:
                st.dataframe(response["FTL53"], use_container_width=True)
            else:
                st.info("ℹ️ No FTL53 rates found.")

        with st.expander("🏢 Drayage", expanded=False):
            if response["Drayage"] is not None and not response["Drayage"] == {}:
                st.dataframe(response["Drayage"], use_container_width=True)
            else:
                st.info("ℹ️ No Drayage rates found.")


        #     response = trans_rates(payload)
        #     result = response["result"]
        #     errors = response["errors"]

        # elapsed_time = round(time.time() - start_time, 2)
        # st.success(f"✅ Done in {elapsed_time} seconds")

        # if errors:
        #     st.warning("⚠️ Some issues were detected while processing:")
        #     for err in errors:
        #         st.text(err)

        # if result:
        #     st.markdown("### 📊 Best Available Rate")
        #     st.markdown(
        #         f"""
        #         <div style="
        #             text-align:center;
        #             padding:20px;
        #             border-radius:12px;
        #             background:linear-gradient(135deg, #f6d365 0%, #fda085 100%);
        #             color:white;
        #             font-size:24px;
        #             font-weight:bold;">
        #             💰 ${result.get("Rate","-"):,.2f}
        #         </div>
        #         """,
        #         unsafe_allow_html=True
        #     )

        #     left, right = st.columns(2)
        #     with left:
        #         st.metric("Rate Type", result.get("Rate Type", "-"))
        #         st.metric("Carrier", result.get("Carrier Name", "-"))
        #         st.metric("Service Provider", result.get("Service Provider", "-"))
        #     with right:
        #         st.metric("Source", result.get("Source", "-"))
        #         st.metric("Date", result.get("Date", "-"))
        # else:
        #     st.error("❌ No valid rates found. Please check inputs.")





