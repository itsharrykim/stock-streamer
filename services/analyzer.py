from collections import deque, defaultdict
from typing import Deque, Dict, Iterable, List, Optional, Tuple
import math
import time
import statistics

# Each tick: (ts_ms, price, size)
Tick = Tuple[int, float, float]


class TickWindow:
    """Time-windowed tick buffer with simple metric helpers."""
    def __init__(self, window_seconds: int):
        self.window_ms = int(window_seconds * 1000)
        self.deq: Deque[Tick] = deque()
        self._vol_sum = 0.0
        self._pv_sum = 0.0  # price * volume

    def add(self, ts_ms: int, price: float, size: float = 1.0):
        self.deq.append((ts_ms, float(price), float(size)))
        self._pv_sum += price * size
        self._vol_sum += size
        self._prune(ts_ms)

    def _prune(self, now_ms: int):
        cutoff = now_ms - self.window_ms
        while self.deq and self.deq[0][0] < cutoff:
            ts, p, s = self.deq.popleft()
            self._pv_sum -= p * s
            self._vol_sum -= s

    def prices(self) -> List[float]:
        return [p for _, p, _ in self.deq]

    def volumes(self) -> List[float]:
        return [s for _, _, s in self.deq]

    def vwap(self) -> Optional[float]:
        if self._vol_sum <= 0:
            return None
        return self._pv_sum / self._vol_sum

    def sma(self) -> Optional[float]:
        ps = self.prices()
        if not ps:
            return None
        return statistics.mean(ps)

    def std(self) -> Optional[float]:
        ps = self.prices()
        if len(ps) < 2:
            return None
        return statistics.pstdev(ps)

    def log_returns(self) -> List[float]:
        ps = self.prices()
        if len(ps) < 2:
            return []
        return [math.log(ps[i] / ps[i - 1]) for i in range(1, len(ps))]


class BarAggregator:
    """Aggregate ticks into time bars (open/high/low/close, volume)."""
    def __init__(self, bar_seconds: int = 1):
        self.bar_ms = int(bar_seconds * 1000)
        self.current_start: Optional[int] = None
        self.open: Optional[float] = None
        self.high: Optional[float] = None
        self.low: Optional[float] = None
        self.close: Optional[float] = None
        self.volume: float = 0.0

    def add_tick(self, ts_ms: int, price: float, size: float = 1.0) -> Optional[Dict]:
        """Return finished bar dict when a bar completes, otherwise None."""
        bar_start = ts_ms - (ts_ms % self.bar_ms)
        if self.current_start is None:
            # start first bar
            self.current_start = bar_start
            self._init_bar(price, size)
            return None

        if bar_start == self.current_start:
            self._update_bar(price, size)
            return None

        # bar rolled over -> emit previous bar and start new
        finished = {
            "time": self.current_start // 1000,  # seconds
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }
        # start new bar from this tick
        self.current_start = bar_start
        self._init_bar(price, size)
        return finished

    def _init_bar(self, price: float, size: float):
        self.open = self.high = self.low = self.close = price
        self.volume = size

    def _update_bar(self, price: float, size: float):
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        self.close = price
        self.volume += size


class Analyzer:
    """Top-level helper to manage per-symbol buckets and compute metrics."""
    def __init__(self, default_window_seconds: int = 60):
        self.default_window_seconds = default_window_seconds
        self.windows: Dict[str, TickWindow] = {}
        self.buckets: Dict[Tuple[str, int], BarAggregator] = {}
        # optional: maintain last EMA per symbol/window
        self._last_ema: Dict[Tuple[str, int], float] = {}

    def _get_window(self, symbol: str, window_seconds: int) -> TickWindow:
        key = f"{symbol}:{window_seconds}"
        if key not in self.windows:
            self.windows[key] = TickWindow(window_seconds)
        return self.windows[key]

    def add_tick(self, symbol: str, ts_ms: int, price: float, size: float = 1.0):
        """Call for each incoming tick."""
        # default window
        w = self._get_window(symbol, self.default_window_seconds)
        w.add(ts_ms, price, size)
        # update any bar aggregators for this symbol
        # common bar sizes: 1s, 60s
        for bar_sec in (1, 60):
            key = (symbol, bar_sec)
            if key not in self.buckets:
                self.buckets[key] = BarAggregator(bar_sec)
            finished = self.buckets[key].add_tick(ts_ms, price, size)
            if finished:
                # you can store finished bars or compute indicators that need bars
                pass

    def vwap(self, symbol: str, window_seconds: Optional[int] = None) -> Optional[float]:
        ws = window_seconds or self.default_window_seconds
        return self._get_window(symbol, ws).vwap()

    def sma(self, symbol: str, window_seconds: Optional[int] = None) -> Optional[float]:
        ws = window_seconds or self.default_window_seconds
        return self._get_window(symbol, ws).sma()

    def std(self, symbol: str, window_seconds: Optional[int] = None) -> Optional[float]:
        ws = window_seconds or self.default_window_seconds
        return self._get_window(symbol, ws).std()

    def ema(self, symbol: str, span: int = 20, window_seconds: Optional[int] = None) -> Optional[float]:
        """Simple EMA computed over available window prices; maintains last value for efficiency."""
        ws = window_seconds or self.default_window_seconds
        window = self._get_window(symbol, ws)
        ps = window.prices()
        if not ps:
            return None
        alpha = 2 / (span + 1)
        key = (symbol, span)
        last = self._last_ema.get(key)
        if last is None:
            # seed with SMA
            last = statistics.mean(ps)
        # compute EMA by iterating through prices (cheap if window small)
        for p in ps:
            last = alpha * p + (1 - alpha) * last
        self._last_ema[key] = last
        return last

    def volatility(self, symbol: str, window_seconds: Optional[int] = None) -> Optional[float]:
        """Return simple volatility = std(log returns) annualized approx (assuming seconds -> trading seconds per year)."""
        ws = window_seconds or self.default_window_seconds
        lr = self._get_window(symbol, ws).log_returns()
        if not lr:
            return None
        sigma = statistics.pstdev(lr)
        # annualize: sqrt(N) where N ~ trading seconds/year / window_seconds
        # approximate trading seconds per year ~ 252 * 6.5 * 3600 = 589,680
        seconds_per_year = 252 * 6.5 * 3600
        factor = math.sqrt(seconds_per_year / ws)
        return sigma * factor

    def get_recent_bars(self, symbol: str, bar_seconds: int = 60, limit: int = 100) -> List[Dict]:
        """Return last N finished bars if you stored them — placeholder to show API shape."""
        # For a full implementation you'd persist finished bars; this stub returns empty list.
        return []



