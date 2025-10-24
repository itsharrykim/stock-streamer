import os
import streamlit as st
from pages import demo, alpaca_live


st.set_page_config(layout="wide")
st.title("Stock price vs time")

st.sidebar.header("Menu")
page = st.sidebar.selectbox("Page", ["Demo Data", "Alpaca Live"]) 

if page == "Demo Data":
    demo.demo_page()
else:
    alpaca_live.alpaca_page()