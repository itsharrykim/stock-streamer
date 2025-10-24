import asyncio
import datetime
import json
import threading
import time
from queue import Queue
from typing import Dict, Optional, Set

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from services.websocket_alpaca import WebSocketStreamer
from services.analyzer import Analyzer

#globals
streamer: Optional[WebSocketStreamer] = None
_forwarder_thread: Optional[threading.Thread] = None

#client communication
forward_q: Queue = Queue()
clients: Set[WebSocket] = set()
clients_lock = threading.Lock()

# analyzer instance
analyzer = Analyzer(default_window_seconds=60)

# simple throttling state: send metrics no more often than metrics_interval_ms per symbol
_last_metrics_sent: Dict[str, float] = {}
_metrics_interval_ms = 1000

app = FastAPI()
app.mount("/static", StaticFiles(directory="server/static", html=True), name="static")

@app.get("/", response_class=FileResponse)
async def root_index():
    return FileResponse("server/static/index.html")

def _iso_to_ms(s: str) -> Optional[int]:
    if s is None:
        return None
    try:
        # try epoch in seconds or milliseconds
        num = float(s)
        if num > 1e12:  # already ms
            return int(num)
        if num > 1e9:  # seconds
            return int(num * 1000)
    except Exception:
        pass
    try:
        # parse ISO string
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return None

def _queue_forwarder(loop: asyncio.AbstractEventLoop):
    while True:
        item = forward_q.get()
        try:
            text = json.dumps(item, default=str)
        except Exception:
            text = json.dumps({"_serialize_error": True, "raw": str(item)})

        # First: forward raw item to clients (tick/control)
        with clients_lock:
            for ws in list(clients):
                try:
                    asyncio.run_coroutine_threadsafe(ws.send_text(text), loop)
                except Exception:
                    pass
                
        # Try to extract tick fields for analysis
        try:
            symbol = item.get("S")
            price = item.get("p")
            # optional size/volume
            size = item.get("s")
            ts_raw = item.get("t")
            ts_ms = None
            if isinstance(ts_raw, (int, float)):
                ts_ms = int(float(ts_raw) * (1000 if ts_raw < 1e12 else 1))
            elif isinstance(ts_raw, str):
                ts_ms = _iso_to_ms(ts_raw)
            # fallback to now
            if ts_ms is None:
                ts_ms = int(time.time() * 1000)
            if symbol and price is not None:
                # normalize
                symbol = str(symbol).upper()
                price = float(price)
                size = float(size) if size is not None else 1.0

                # feed analyzer (returns finished bars if any)
                finished_bars = analyzer.add_tick(symbol, ts_ms, price, size)

                # send finished bars to clients
                if finished_bars:
                    for fb in finished_bars:
                        try:
                            asyncio.run_coroutine_threadsafe(
                                ws.send_text(json.dumps(fb, default=str)), loop
                            )
                        except Exception:
                            pass

                # throttle metrics per symbol
                now_ms = int(time.time() * 1000)
                last = _last_metrics_sent.get(symbol, 0)
                if now_ms - last >= _metrics_interval_ms:
                    _last_metrics_sent[symbol] = now_ms
                    metrics = {
                        "type": "metrics",
                        "symbol": symbol,
                        "window_s": analyzer.default_window_seconds,
                        "vwap": analyzer.vwap(symbol),
                        "sma": analyzer.sma(symbol),
                        "ema20": analyzer.ema(symbol, span=20),
                        "std": analyzer.std(symbol),
                        # do not call heavy ops too frequently
                    }
                    metrics_text = json.dumps(metrics, default=str)
                    with clients_lock:
                        for ws in list(clients):
                            try:
                                asyncio.run_coroutine_threadsafe(ws.send_text(metrics_text), loop)
                            except Exception:
                                pass
        except Exception:
            # swallow per-item errors, optionally log
            import traceback
            traceback.print_exc()

@app.on_event("startup")
def startup_event():
    global streamer, _forwarder_thread
    loop = asyncio.get_event_loop()
    # start forwarder thread
    if _forwarder_thread is None or not _forwarder_thread.is_alive():
        _forwarder_thread = threading.Thread(target=_queue_forwarder, args=(loop,), daemon=True)
        _forwarder_thread.start()
    # start your Alpaca streamer and point it at forward_q
    streamer = WebSocketStreamer(on_message_cb=None, out_queue=forward_q)
    streamer.start()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    with clients_lock:
        clients.add(ws)
    try:
        # keep the socket open; clients usually don't send data here
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        with clients_lock:
            clients.discard(ws)

@app.post("/api/connect")
async def api_connect():
    global streamer, _forwarder_thread
    if streamer is not None and streamer.running:
        # streamer already initialized and running
        print("Streamer already connected and running")
        return {"running": True, "started": False}
    else:
        # streamer not running, start it
        try:
            loop = asyncio.get_event_loop()
            streamer = WebSocketStreamer(on_message_cb=None, out_queue=Queue())
            streamer.start()
            if _forwarder_thread is None or not _forwarder_thread.is_alive():
                _forwarder_thread = threading.Thread(
                    target=_queue_forwarder, args=(loop,), daemon=True, name="queue-forwarder"
                )
                _forwarder_thread.start()
            print("Streamer connected and started")
            return {"running": True, "started": True}
        except Exception:
            print("Error starting streamer")
            return {"running": False, "started": False}

@app.post("/api/disconnect")
async def api_disconnect():
    try:
        global streamer
        if streamer:
            streamer.stop()
            streamer = None
        print("Streamer disconnected")
        return {"ok": True, "stopped": True}
    except Exception:
        print("Error stopping streamer")
        return {"ok": False, "stopped": False}

@app.post("/api/subscribe")
async def api_subscribe(req: Request):
    global streamer
    body = await req.json()
    symbol = (body.get("symbol") or "").strip().upper()
    
    if not symbol:
        return {"ok": False, "error": "missing_symbol"}

    if streamer is None:
        return {"ok": False, "error": "streamer_not_running"}

    try:
        streamer.subscribe_trades([symbol])
    except Exception as e:
        return {"ok": False, "error": str(e)}
    print(f"Subscribed to {symbol}")
    return {"ok": True, "symbol": symbol}

@app.post("/api/unsubscribe")
async def api_unsubscribe(req: Request):
    global streamer
    body = await req.json()
    symbol = (body.get("symbol") or "").strip().upper()

    if not symbol:
        return {"ok": False, "error": "missing_symbol"}

    if streamer is None:
        return {"ok": False, "error": "streamer_not_running"}

    try:
        streamer.unsubscribe_trades([symbol])
    except Exception as e:
        print(e)
        return {"ok": False, "error": str(e)}
    
    print(f"Unsubscribed from {symbol}")
    return {"ok": True, "symbol": symbol}