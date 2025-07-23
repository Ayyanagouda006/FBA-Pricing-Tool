import streamlit as st
from streamlit_option_menu import option_menu
from calculator import fba_quote_app

# ----------------- Page Setup -----------------
st.set_page_config(page_title="Shipping Suite", layout="wide")

# ----------------- Top Horizontal Menu -----------------
selected = option_menu(
    menu_title=None,
    options=["📦 FBA Quote", "🔍 Other Module", "⚙️ Settings"],
    orientation="horizontal"
)

if selected == "📦 FBA Quote":
    st.title("📦 FBA Quote Calculator")
    fba_quote_app()

elif selected == "🔍 Other Module":
    st.title("🔍 Other Module")
    st.write("Coming soon...")

elif selected == "⚙️ Settings":
    st.title("⚙️ App Settings")
    st.write("Manage user settings, preferences, and more.")

