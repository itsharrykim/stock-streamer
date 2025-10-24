import os
import streamlit as st
import pandas as pd
import queue
import time
from services.websocket_alpaca import WebSocketStreamer


def alpaca_page():
    st.header("Alpaca Real-Time WebSocket Stream")

    # Sidebar controls
    with st.sidebar.expander("Alpaca Controls", expanded=True):
        stream_symbol = st.text_input("Symbol", "FAKEPACA").upper().strip()
        max_points = st.number_input("Max points to keep", 50, 5000, 500, step=50)
        start_btn = st.button("Start Stream")
        stop_btn = st.button("Stop Stream")

    # Session state initialization
    if "alpaca_ws" not in st.session_state:
        st.session_state.alpaca_ws = None
    if "alpaca_queue" not in st.session_state:
        st.session_state.alpaca_queue = queue.Queue()
    if "alpaca_df" not in st.session_state:
        st.session_state.alpaca_df = pd.DataFrame(columns=["price"]).astype(float)

    status_placeholder = st.empty()
    records_placeholder = st.empty()

    # Start stream
    if start_btn:
        if st.session_state.alpaca_ws is None or not st.session_state.alpaca_ws.running:
            # Create new WebSocketStreamer instance
            st.session_state.alpaca_queue = queue.Queue()  # fresh queue
            st.session_state.alpaca_df = pd.DataFrame(columns=["price"]).astype(float)  # reset data
            
            ws = WebSocketStreamer(
                out_queue=st.session_state.alpaca_queue
            )
            try:
                ws.start()
            except Exception as e:
                status_placeholder.error(f"Failed to start stream: {e}")
                return
            
            # Subscribe to trades for the symbol
            try:
                ws.subscribe_trades([stream_symbol])
            except Exception as e:
                status_placeholder.error(f"Failed to subscribe to symbol {stream_symbol}: {e}")
                return
            
            st.session_state.alpaca_ws = ws
            status_placeholder.success(f"Stream started for {stream_symbol}. Waiting for trades...")
        else:
            status_placeholder.info("Stream already running.")

    # Stop stream
    if stop_btn:
        if st.session_state.alpaca_ws and st.session_state.alpaca_ws.running:
            st.session_state.alpaca_ws.stop()
            st.session_state.alpaca_ws = None
            status_placeholder.warning("Stream stopped.")
        else:
            status_placeholder.info("No active stream to stop.")

    # Show connection status
    ws = st.session_state.alpaca_ws
    if ws:
        status_text = f"Running: {ws.running} | Connected: {ws.connected}"
        st.sidebar.text(status_text)

    # Consume queue and check if we got new data
    new_data = False
    start_time = time.time()
    while time.time() - start_time < 0.5:
        try:
            item = st.session_state.alpaca_queue.get_nowait()
        except queue.Empty:
            break
        if not item:
            break

        # Handle control messages
        if item.get("_ws_error"):
            st.error(f"WebSocket error: {item.get('error')}")
            continue
        if item.get("_ws_closed"):
            st.warning(f"WebSocket closed: {item.get('msg')}")
            continue

        # Handle trade messages
        # Alpaca v2 trade shape: {'T': 't', 'S': 'AAPL', 'p': 150.25, 't': '2025-10-23T...', ...}
        if item.get("T") == "t":
            try:
                symbol = item.get("S")
                price = float(item.get("p", 0))
                timestamp = pd.to_datetime(item.get("t"))
                
                # Append to dataframe using loc (avoids FutureWarning with empty df)
                st.session_state.alpaca_df.loc[timestamp] = price
                
                # Keep only max_points most recent
                if len(st.session_state.alpaca_df) > max_points:
                    st.session_state.alpaca_df = st.session_state.alpaca_df.iloc[-max_points:]
                
                st.session_state.alpaca_df = st.session_state.alpaca_df.sort_index()
                new_data = True
            except Exception as e:
                st.error(f"Error processing trade: {e}")

    # Render trade records as text rows
    if len(st.session_state.alpaca_df) > 0:
        records_text = ""
        for ts, row in st.session_state.alpaca_df.iterrows():
            records_text += f"{ts.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} | Price: ${row['price']:.4f}\n"
        records_placeholder.text(records_text)
    else:
        records_placeholder.info("No trade data yet. Start the stream and wait for trades.")
    
    # Auto-refresh when stream is active
    if ws and ws.running:
        time.sleep(0.1)  # Small delay to avoid too frequent reruns
        st.rerun()


if __name__ == "__main__":
    alpaca_page()
