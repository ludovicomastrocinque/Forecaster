"""Sales Forecaster - Main entry point with navigation."""

import streamlit as st

st.set_page_config(
    page_title="Sales Forecaster",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.logo("assets/wildix_logo.png", size="large")

st.markdown("""
<style>
[data-testid="stSidebar"] {
    background-color: #003865 !important;
}
[data-testid="stSidebar"] * {
    color: white !important;
}
/* Nav page links — up from default ~14px to 16px */
[data-testid="stSidebar"] nav a span,
[data-testid="stSidebarNavLink"] span {
    font-size: 1rem !important;
}
/* Section headers e.g. "Dev" */
[data-testid="stSidebar"] nav li > div > p,
[data-testid="stSidebarNavSeparator"] p {
    font-size: 0.95rem !important;
}
/* Force logo to display at 2x height */
[data-testid="stSidebarHeader"] {
    padding: 16px 16px !important;
    min-height: 80px !important;
}
[data-testid="stSidebarHeader"] img {
    height: 64px !important;
    width: auto !important;
    max-width: 100% !important;
}
</style>
""", unsafe_allow_html=True)

pg = st.navigation({
    " ": [
        st.Page("pages/1_Forecast_Input.py", title="Forecast Input", icon="📝", default=True),
        st.Page("pages/2_Pipeline_Overview.py", title="Regional Overview", icon="📋"),
        st.Page("pages/3_Deal_View.py", title="Deal View", icon="🔍"),
    ],
    "Dev": [
        st.Page("pages/4_Admin.py", title="Admin", icon="⚙️"),
        st.Page("pages/5_Data_Upload.py", title="Data Upload", icon="📤"),
        st.Page("pages/6_Roster.py", title="Sales Roster", icon="👥"),
    ],
})

pg.run()
