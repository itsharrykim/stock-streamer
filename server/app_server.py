import asyncio
import json
import threading
from queue import Queue
from typing import Optional, Set

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from services.websocket_alpaca import WebSocketStreamer

#globals
streamer: Optional[WebSocketStreamer] = None
_forwarder_thread: Optional[threading.Thread] = None

#client communication
forward_q: Queue = Queue()
clients: Set[WebSocket] = set()
clients_lock = threading.Lock()

app = FastAPI()
app.mount("/static", StaticFiles(directory="server/static", html=True), name="static")

@app.get("/", response_class=FileResponse)
async def root_index():
    return FileResponse("server/static/index.html")

def _queue_forwarder(loop: asyncio.AbstractEventLoop):
    while True:
        item = forward_q.get()
        try:
            text = json.dumps(item, default=str)
        except Exception:
            text = json.dumps({"_serialize_error": True, "raw": str(item)})
        with clients_lock:
            for ws in list(clients):
                try:
                    asyncio.run_coroutine_threadsafe(ws.send_text(text), loop)
                except Exception:
                    print("Removing disconnected client")
                    pass

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