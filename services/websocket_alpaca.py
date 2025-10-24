import os
import json
import threading
import websocket
from typing import Callable, Iterable, Optional
from queue import Queue
from pathlib import Path
from dotenv import load_dotenv

# load secrets
env_path = Path(__file__).parents[1] / ".env"
load_dotenv(env_path)

ALPACA_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET = os.getenv("ALPACA_API_SECRET")
ALPACA_URL = "wss://stream.data.alpaca.markets/v2/test"


class WebSocketStreamer:

    def __init__(
        self,
        on_message_cb: Optional[Callable[[dict], None]] = None,
        out_queue: Optional[Queue] = None,
        ping_interval: int = 20,
        ping_timeout: int = 10,
    ):
        self._on_message_cb = on_message_cb
        self._queue = out_queue
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout

        self.ws: Optional[websocket.WebSocketApp] = None
        self.thread: Optional[threading.Thread] = None
        self._running = False
        self._authenticated = False
        self._pending_subscriptions = []

    def _handle_item(self, item: dict):
        # deliver parsed item to callback or queue
        if self._on_message_cb:
            try:
                self._on_message_cb(item)
            except Exception:
                # swallow exceptions from user callback
                import traceback
                traceback.print_exc()
        if self._queue:
            try:
                self._queue.put(item)
            except Exception:
                pass

    def _on_open(self, ws):
        auth_msg = {"action": "auth", "key": ALPACA_KEY, "secret": ALPACA_SECRET}
        try:
            # print(auth_msg)
            ws.send(json.dumps(auth_msg))
        except Exception as e:
            self._handle_item({"_ws_error": True, "error": f"Auth send failed: {e}"})

    def _flush_pending_subscriptions(self):
        while self._pending_subscriptions:
            payload = self._pending_subscriptions.pop(0)
            try:
                if self.ws:
                    self.ws.send(json.dumps(payload))
            except Exception as e:
                # Put it back and stop trying
                self._pending_subscriptions.insert(0, payload)
                self._handle_item({"_ws_error": True, "error": f"Subscribe send failed: {e}"})
                break

    def _on_message(self, ws, message: str):
        try:
            data = json.loads(message)
        except Exception:
            return
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not self._authenticated:
                if (item.get("T") == "success" and "authenticated" in item.get("msg", "").lower()) or \
                   (item.get("action") == "auth" and item.get("status") in ("authorized", "authorized.0")):
                    self._authenticated = True
                    self._flush_pending_subscriptions()
            
            self._handle_item(item)

    def _on_error(self, ws, error):
        self._handle_item({"_ws_error": True, "error": str(error)})

    def _on_close(self, ws, close_status_code=None, close_msg=None):
        self._handle_item({"_ws_closed": True, "code": close_status_code, "msg": close_msg})
        self._running = False
        self._authenticated = False

    def start(self, run_async: bool = True):
        if self._running:
            return
        
        self._authenticated = False
        self.ws = websocket.WebSocketApp(
            ALPACA_URL,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

        def _run():
            self._running = True
            try:
                self.ws.run_forever(ping_interval=self._ping_interval, ping_timeout=self._ping_timeout)
            except Exception as e:
                self._handle_item({"_ws_error": True, "error": str(e)})
            finally:
                self._running = False
                self._authenticated = False

        self.thread = threading.Thread(target=_run, name="WebSocketStreamer", daemon=True)
        self.thread.start()
        if not run_async:
            self.thread.join()

    def stop(self, timeout: float = 2.0):
        if not self.ws:
            return
        try:
            self.ws.close()
        except Exception:
            pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout)

        self.ws = None
        self.thread = None
        self._running = False
        self._authenticated = False
        self._pending_subscriptions.clear()

    def send_raw(self, payload: dict):
        if self.ws and getattr(self.ws, "sock", None) and getattr(self.ws.sock, "connected", False):
            try:
                self.ws.send(json.dumps(payload))
                return
            except Exception:
                pass
        self._pending_subscriptions.append(payload)

    def subscribe_trades(self, symbols: Iterable[str]):
        subscribe_msg = {"action": "subscribe", "trades": list(symbols)}
        self.send_raw(subscribe_msg)

    def unsubscribe_trades(self, symbols: Iterable[str]):
        unsubscribe_msg = {"action": "unsubscribe", "trades": list(symbols)}
        self.send_raw(unsubscribe_msg)

    def subscribe(self, trades: Optional[Iterable[str]] = None, quotes: Optional[Iterable[str]] = None, bars: Optional[Iterable[str]] = None):
        payload = {"action": "subscribe"}
        if trades:
            payload["trades"] = list(trades)
        if quotes:
            payload["quotes"] = list(quotes)
        if bars:
            payload["bars"] = list(bars)
        self.send_raw(payload)

    @property
    def running(self):
        return self._running
    
    @property
    def connected(self):
        return self._running and self._authenticated and \
               self.ws and getattr(self.ws, "sock", None) and \
               getattr(self.ws.sock, "connected", False)
