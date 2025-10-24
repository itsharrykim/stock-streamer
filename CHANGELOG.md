v0.8
- Replace all javascript alert dialog to HTML/CSS/JS flash message

v0.7
- Symbol textbox added
- Alpaca websocket url changed from test to IEX

v0.6
- Display real-time line chart

v0.5
- Alpaca stream responses display as text

v0.4
- Streamlit not ideal for real-time streaming data visualization (continuous app re-run not ideal for high performance)
- Decoupling server and UI: FastAPI for backend and Lightweight-Charts (HTML + Javascript) for frontend
- Simple connect / disconnect websocket to Alpaca using FastAPI and vanilla HTML + Javascript

v0.3 
- App name includes crypto
- Alpaca trade api library added
- Demo websocket streaming from Alpaca added

v0.2
- Panda library added
- Demo data (csv) added
- Simple line chart using the demo data

v0.1 
- Empty Streamlit app