import streamlit as st
import pandas as pd
from pathlib import Path

def demo_page():
    # resolve demo CSV path relative to project root
    data_file = Path(__file__).parents[1] / "resources" / "demo_stock_data.csv"
    if not data_file.exists():
        st.error(f"Demo data file not found: {data_file}\nPlease ensure resources/demo_stock_data.csv exists.")
        return
    # load demo data
    df = pd.read_csv(data_file, parse_dates=["ts"])
    
    # Get unique symbols
    symbols = df["symbol"].unique().tolist()

    # Sidebar controls grouped in an expander to avoid clutter
    with st.sidebar.expander("Demo Controls", expanded=True):
        symbol_selected = st.selectbox("Symbol", symbols, index=0)
    
    # Filter data for the selected symbol
    df_sym = df[df["symbol"] == symbol_selected].sort_values("ts").set_index("ts")
    
    # Display the line chart for the selected symbol
    st.subheader(f"{symbol_selected} price over time (demo data)")
    st.line_chart(df_sym["price"])



if __name__ == "__main__":
    # When Streamlit runs this file directly (as a page), render the demo page.
    demo_page()