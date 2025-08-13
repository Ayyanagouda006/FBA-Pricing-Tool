import streamlit as st
from streamlit_option_menu import option_menu
from search_quotes import search_quotations_app
from pathlib import Path
import pandas as pd
import datetime as dt
import os
import time

# ---------- FBA Tariff Validation Setup ----------
FBA_FILE_PATH = "Data/FBA Rates.xlsx"

EXPECTED_SHEETS = ["FBA Locations", "P2P", "Accessorials", "Palletization"]

EXPECTED_FBA_LOCATIONS = [
    "FPOD ZIP", "FPOD CITY", "FPOD UNLOC", "FPOD STATE CODE", "FPOD CFS NAME",
    "FBA Code", "FBA ZIP", "FBA CITY", "FBA STATE CODE", "Last 10 weeks",
    "Last 1 Week", "Last 3 Week", "Pre-Determined Bucket", "Loadability",
    "Consolidator", "FBA / Destn Coast"
]

EXPECTED_P2P = [
    "P2P Type", "Carrier SCAC", "POL Name", "POR/POL", "FPOD Name", "FPOD UNLOC", "FPOD Name",
    "Origin charges per Container(INR)", "OIH", "Ocean Freight (USD)", "DIH", "Drayage & Devanning(USD)",
    "Total cost (USD)", "Loadability", "Per CBM(USD)", "Valid From", "Valid To", "Notes"
]

EXPECTED_ACCESSORIALS = ["Charge Head", "FPOD", "Location Unloc", "Currency", "Amount"]
EXPECTED_PALLETIZATION = ["Service Type", "FPOD", "FPOD UNLOC", "Currency", "Amount"]

def validate_fba_tariff(file_path):
    try:
        xl = pd.ExcelFile(file_path)

        for sheet in EXPECTED_SHEETS:
            if sheet not in xl.sheet_names:
                return f"❌ Missing sheet: {sheet}"

        df_fba = pd.read_excel(file_path, sheet_name="FBA Locations")
        for col in EXPECTED_FBA_LOCATIONS:
            if col not in df_fba.columns:
                return f"❌ Missing column '{col}' in FBA Locations"

        for col in EXPECTED_FBA_LOCATIONS[:10]:
            if df_fba[col].isna().any() or df_fba[col].eq("").any():
                return f"❌ Blank value found in column '{col}' of FBA Locations"

        for col in ["Last 10 weeks", "Last 1 Week", "Last 3 Week"]:
            if not pd.api.types.is_numeric_dtype(df_fba[col]):
                return f"❌ Column '{col}' must contain only numeric values in FBA Locations"

        df_p2p = pd.read_excel(file_path, sheet_name="P2P")
        for col in EXPECTED_P2P:
            if col not in df_p2p.columns:
                return f"❌ Missing column '{col}' in P2P"

        for col in ["POL Name", "POR/POL", "FPOD Name", "FPOD UNLOC", "Per CBM(USD)", "Valid From", "Valid To"]:
            if df_p2p[col].isna().any() or df_p2p[col].eq("").any():
                return f"❌ Blank value found in column '{col}' of P2P"

        if not df_p2p["P2P Type"].isin(["Own Console", "Coload"]).all():
            return "❌ P2P Type must be either 'Own Console' or 'Coload'"

        own_console = df_p2p[df_p2p["P2P Type"] == "Own Console"]
        for col in ["Origin charges per Container(INR)", "Ocean Freight (USD)", 
                    "Drayage & Devanning(USD)", "Total cost (USD)", "Loadability", "Per CBM(USD)"]:
            if own_console[col].isna().any():
                return f"❌ Missing value in '{col}' for Own Console rows"
            if not pd.api.types.is_numeric_dtype(own_console[col]):
                return f"❌ Column '{col}' must be numeric for Own Console rows"

        coload = df_p2p[df_p2p["P2P Type"] == "Coload"]
        if coload["Per CBM(USD)"].isna().any() or not pd.api.types.is_numeric_dtype(coload["Per CBM(USD)"]):
            return "❌ 'Per CBM(USD)' must be numeric for Coload rows"

        today = dt.datetime.today()
        for i, row in df_p2p.iterrows():
            try:
                valid_from = pd.to_datetime(row["Valid From"])
                valid_to = pd.to_datetime(row["Valid To"])
                if not (valid_from <= today <= valid_to):
                    return f"❌ Rates expired for row {i+2} in P2P"
            except Exception:
                return f"❌ Invalid date format in Valid From/Valid To at row {i+2}"

        df_acc = pd.read_excel(file_path, sheet_name="Accessorials")
        for col in EXPECTED_ACCESSORIALS:
            if col not in df_acc.columns:
                return f"❌ Missing column '{col}' in Accessorials"

        if not df_acc["Currency"].eq("USD").all():
            return "❌ All Currency values in Accessorials must be 'USD'"
        if not pd.api.types.is_numeric_dtype(df_acc["Amount"]):
            return "❌ 'Amount' in Accessorials must be numeric"

        df_pal = pd.read_excel(file_path, sheet_name="Palletization")
        for col in EXPECTED_PALLETIZATION:
            if col not in df_pal.columns:
                return f"❌ Missing column '{col}' in Palletization"

        if not df_pal["Currency"].eq("USD").all():
            return "❌ All Currency values in Palletization must be 'USD'"
        if not pd.api.types.is_numeric_dtype(df_pal["Amount"]):
            return "❌ 'Amount' in Palletization must be numeric"

        return "✅ File validation passed"

    except Exception as e:
        return f"❌ Error reading file: {str(e)}"


# ---------- Row Renderer ----------
def upload_row(label, file_path, validate_func=None):
    uploader_key = f"file_{label}"

    # --- RESET before widget creation ---
    if st.session_state.get(f"reset_{uploader_key}", False):
        # Remove uploader's state value
        st.session_state.pop(uploader_key, None)
        st.session_state[f"reset_{uploader_key}"] = False

    col1, col2, col3 = st.columns([0.5, 2, 3])

    # Download existing file
    with col1:
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                st.download_button(
                    label="⬇️",
                    data=f,
                    file_name=Path(file_path).name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"download_{label}"
                )
        else:
            st.write("❌")

    # Label
    with col2:
        st.markdown(
            f"<div style='font-weight:600; font-size:20px; color:#333; text-align:center;'>{label}</div>",
            unsafe_allow_html=True
        )

    # Uploader
    with col3:
        uploaded_file = st.file_uploader("Choose file", key=uploader_key, label_visibility="collapsed")
        if uploaded_file:
            temp_path = f"temp_{Path(file_path).name}"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            if validate_func:
                result = validate_func(temp_path)
                if result.startswith("✅"):
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    st.success("✅ Data Uploaded Successfully!!!")
                    time.sleep(1)
                    st.cache_data.clear()
                    st.session_state[f"reset_{uploader_key}"] = True
                    st.rerun()
                else:
                    st.error(result)
            else:
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                st.cache_data.clear()
                st.session_state[f"reset_{uploader_key}"] = True
                st.rerun()

    st.markdown("<hr style='margin:0; border: 1px solid #ccc;'>", unsafe_allow_html=True)

# ---------- Main App ----------
def data_management_app():
    selected = option_menu(
        menu_title=None,
        options=["Uploads", "Search Quotation"],
        icons=["upload", "search"],
        orientation="horizontal",
        styles={
            "container": {"padding": "0!important", "background-color": "#d4d5d7"},
            "icon": {"color": "black", "font-size": "14px"},
            "nav-link": {"font-size": "14px", "text-align": "center", "--hover-color": "#eee"},
            "nav-link-selected": {"background-color": "#00050a"},
        },
    )

    if selected == "Uploads":
        st.markdown("<hr style='margin:0; border: 1px solid #ccc;'>", unsafe_allow_html=True)
        upload_row("FBA Tariff", FBA_FILE_PATH, validate_func=validate_fba_tariff)
        upload_row("Last Mile Rates (No API)", "Data/Last Mile Rates (no api).xlsx")
    elif selected == "Search Quotation":
        search_quotations_app()
