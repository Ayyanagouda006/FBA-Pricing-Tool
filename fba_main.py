import streamlit as st
from streamlit_option_menu import option_menu
from calculator import fba_quote_app
from search_quotes import search_quotations_app
# ----------------- Page Setup -----------------
st.set_page_config(page_title="Shipping Suite", layout="wide")

# ----------------- Top Horizontal Menu -----------------
selected = option_menu(
    menu_title=None,
    options=["📦 FBA Quote", "🔍 Search Quotations"],
    orientation="horizontal"
)

if selected == "📦 FBA Quote":
    st.title("📦 FBA Quote Calculator")
    fba_quote_app()

elif selected == "🔍 Search Quotations":
    st.title("🔍 Search Quotations")
    search_quotations_app()

