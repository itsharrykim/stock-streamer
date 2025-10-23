import streamlit as st
import pandas as pd

st.title("Stock price vs time")

# load demo data to a dataframe
df = pd.read_csv('./resources/demo_stock_data.csv', parse_dates=["ts"])

# get unique symbols
symbols = df["symbol"].unique().tolist()

# sidemenu
st.sidebar.header("Menu")
symbolSelected = st.sidebar.selectbox("Symbol", symbols, index=0)

# filter dataframe by selected symbol and sort by timestamp
df_sym = df[df["symbol"] == symbolSelected].sort_values("ts").set_index("ts")

# line chart of price vs timestamp
st.subheader(f"{symbolSelected} price over time")
st.line_chart(df_sym["price"])