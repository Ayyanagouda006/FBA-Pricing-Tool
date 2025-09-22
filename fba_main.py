import streamlit as st
from streamlit_option_menu import option_menu
from calculator import fba_quote_app
from data_management import data_management_app
from US_lm_calculator import trans_cal
# ----------------- Page Setup -----------------
st.set_page_config(page_title="FBA Rates Calculator", layout="wide")

VALID_EMAIL = "anshul.marele@agraga.com"
VALID_PASSWORD = "An$M@Ag#FBA!"

# ------------------ Session Setup ------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "previous_tab" not in st.session_state:
    st.session_state.previous_tab = "FBA Quote"

selected = option_menu(
    menu_title=None,
    options=["FBA Quote", "US Transport Rate Calculator", "Data Management"],
    icons=["box", "truck", "cloud-upload"],
    orientation="horizontal",
    styles={
        "container": {
            "padding": "0!important",
            "background-color": "#d4d5d7",
            "width": "100%",
            "display": "flex",
            "justify-content": "space-around"  # or "space-between"
        },
        "icon": {"color": "black", "font-size": "16px"},
        "nav-link": {
            "font-size": "16px",
            "text-align": "center",
            "flex": "1",  # make each option share equal space
            "--hover-color": "#eee",
        },
        "nav-link-selected": {"background-color": "#050E90"},
    },
)


# ------------------ Reset auth on tab switch ------------------
if selected != st.session_state.previous_tab and selected == "🔍 Data Management":
    st.session_state.authenticated = False
st.session_state.previous_tab = selected

if selected == "FBA Quote":
    st.title("📦 FBA Quote Calculator")
    fba_quote_app()
elif selected == "US Transport Rate Calculator":
    trans_cal()

elif selected == "Data Management":
    if not st.session_state.authenticated:
        st.subheader("🔐 Login Required")
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            login = st.form_submit_button("🔐 Login")

        if login:

            if email == VALID_EMAIL and password == VALID_PASSWORD:
                st.session_state.authenticated = True
                st.success("✅ Logged in successfully!")
                st.rerun()
            else:
                st.error("❌ Invalid credentials.")
    else:
        # Logout Button
        if st.button("🚪 Logout"):
            st.session_state.authenticated = False
            st.rerun()
        data_management_app()

