
const connectBtn = document.getElementById('btn-connect-stream')
const disconnectBtn = document.getElementById('btn-disconnect-stream')
const startBtn = document.getElementById('btn-start-stream')
const stopBtn = document.getElementById('btn-stop-stream')
const streamerStatus = document.getElementById('status-stream')
const symbolInput = document.getElementById('input-symbol')
const symbolStatus = document.getElementById('status-symbol')
const streamMessagesContainer = document.getElementById('stream-messages-container')
const flashMessageContainer = document.getElementById('flash-message-container')
const flashMessage = document.getElementById('flash-message')

// initial state
let connectionStatus = false

// empty and enable empty symbol textbox when first loaded
symbolInput.value = ""
symbolInput.disabled = false

// open forward socket to receive stream messages
const wsProto = location.protocol === "https:" ? "wss" : "ws"
const wsUrl = wsProto + "://" + location.host + "/ws"
const forwardWs = new WebSocket(wsUrl)


// initialize chart (guard missing container)
let chart = null
let lineSeries = null
const chartDiv = document.getElementById('chart')
if (chartDiv && window.LightweightCharts) {

    chart = LightweightCharts.createChart(chartDiv, {
        layout: { background: { color: '#ffffff' }, textColor: '#000' },
        rightPriceScale: { visible: true },
        timeScale: { timeVisible: true, secondsVisible: true },
    })
    // lineSeries = chart.addSeries(LightweightCharts.LineSeries, { 
    //     color: '#2b8cff', 
    //     lineWidth: 2 
    // })

} else {
    console.warn('Chart container or LightweightCharts missing')
}


    // main tick series (line of last price)
    const priceSeries = chart.addSeries(LightweightCharts.LineSeries, { color: '#2b8cff', lineWidth: 2})

    // metric overlay series: VWAP (orange), SMA (green), EMA (purple)
    const vwapSeries = chart.addSeries(LightweightCharts.LineSeries, { color: '#ff7f0e', lineWidth: 1 })
    const smaSeries  = chart.addSeries(LightweightCharts.LineSeries, { color: '#2ca02c', lineWidth: 1 })
    const emaSeries  = chart.addSeries(LightweightCharts.LineSeries, { color: '#9467bd', lineWidth: 1 })

    // small in-memory buffers to avoid sending huge setData frequently
    const MAX_POINTS = 1000
    const priceBuffer = []

    function pushPricePoint(timeSec, value) {
        priceBuffer.push({ time: timeSec, value })
        if (priceBuffer.length > MAX_POINTS) priceBuffer.shift()
        priceSeries.update({ time: timeSec, value })
    }

    // track last metric point time per symbol to avoid overlapping identical timestamps
    const lastMetricTime = {}


function parseTimestampMs(item) {
    if (!item) return null
    if (item.t) {
        const parsed = Date.parse(item.t)
        if (!isNaN(parsed)) return parsed
        const num = Number(item.t)
        if (!isNaN(num)) return (String(item.t).length === 10) ? num * 1000 : num
    }
    if (item.timestamp) {
        const parsed = Date.parse(item.timestamp)
        if (!isNaN(parsed)) return parsed
    }
    if (item.ts) {
        const num = Number(item.ts)
        if (!isNaN(num)) return (String(item.ts).length === 10) ? num * 1000 : num
    }
    if (item._epoch_ms) return Number(item._epoch_ms)
    return null
}

forwardWs.addEventListener("open", () => {
    console.log("Forward socket open", wsUrl)
})

forwardWs.addEventListener("message", (evt) => {
    try {
        const item = JSON.parse(evt.data)

        // If analyzer forwarded a metrics message, update overlay series
        if (item.type === 'metrics' && item.symbol) {
            const nowSec = Math.round((Date.now()) / 1000)
            const sym = item.symbol
            // use now as time for metrics (backend throttles frequency)
            if (item.vwap !== null && item.vwap !== undefined) {
                vwapSeries.update({ time: nowSec, value: Number(item.vwap) })
            }
            if (item.sma !== null && item.sma !== undefined) {
                smaSeries.update({ time: nowSec, value: Number(item.sma) })
            }
            if (item.ema20 !== null && item.ema20 !== undefined) {
                emaSeries.update({ time: nowSec, value: Number(item.ema20) })
            }
            // update symbol label
            if (symbolStatus) symbolStatus.textContent = `Symbol: ${sym}`
            return
        }

        // If backend sent a finished bar, update priceSeries with close
        if (item.type === 'bar' && item.close !== undefined && item.time !== undefined) {
            // backend bar.time is seconds
            const timeSec = Number(item.time)
            pushPricePoint(timeSec, Number(item.close))
            return
        }

        // Try to extract price and timestamp; adapt to your Alpaca message shape
        const price = item.p ?? item.price ?? item.last ?? item.px
        const tsMs = parseTimestampMs(item)

        if (price !== undefined && tsMs !== null) {
            const timeSec = Math.round(tsMs / 1000)
            pushPricePoint(timeSec, Number(price))
            return
        }

        if (streamMessagesContainer) {
            // create a new div for each message row
            const node = document.createElement("div")
            node.textContent = messageParser(item)
            streamMessagesContainer.appendChild(node)
            // keep the most recent ~100 lines
            while (streamMessagesContainer.childNodes.length > 100) streamMessagesContainer.removeChild(streamMessagesContainer.firstChild)
        }
    } catch (err) {
        console.error("parse forward message", err, evt.data)
    }
})

function messageParser(msg) {
    // msg is JSON
    const type = msg.T
    const timestamp = msg.t
    const symbol = msg.s
    const price = msg.p

    if (type === "t") {
        const line = (timestamp ? new Date(timestamp).toLocaleString() : "") + " | " + symbol + " | " + price
        return line 
    }
}

forwardWs.addEventListener("close", () => {
    console.log("Forward socket closed")
})

connectBtn.addEventListener('click', async function () {
    try {
        const resp = await fetch('/api/connect', { method: 'POST' })

        // http request failed
        if (!resp.ok) {
            const text = await resp.text().catch(() => resp.statusText)
            alert(`Request failed: ${resp.status} ${resp.statusText}`)
            return
        }

        const body = await resp.json()
        if (body && body.running && body.started === false) {
            showFlashMessage('Streamer is already connected.')
            connectionStatus = true
            streamerStatus.textContent = 'Stream: Connected'
        } else if (body && body.running && body.started) {
            showFlashMessage('Streamer started successfully.')
            connectionStatus = true
            streamerStatus.textContent = 'Stream: Connected'
            symbolStatus.textContent = 'Symbol: N/A'
        } else {
            showFlashMessage("Unexpected response: " + JSON.stringify(body), 'error')
        }
    } catch (err) {
        console.error('Failed to connect streamer:', err)
        showFlashMessage('Failed to connect streamer. Check server logs.', 'error')
    }
})

disconnectBtn.addEventListener('click', async function () {
    try {
        const resp = await fetch('/api/disconnect', { method: 'POST' })
        // http request failed
        if (!resp.ok) {
            const text = await resp.text().catch(() => resp.statusText)
            showFlashMessage(`Request failed: ${resp.status} ${text}`, 'error')
            return
        }

        const body = await resp.json()
        if (body && body.ok && body.stopped) {
            showFlashMessage('Streamer disconnected successfully.')
            connectionStatus = false
            streamerStatus.textContent = 'Stream: Disconnected'
            symbolStatus.textContent = 'Symbol: N/A'
        } else {
            showFlashMessage("Unexpected response: " + JSON.stringify(body), 'error')
        }
    } catch (err) {
        console.error('Failed to disconnect streamer:', err)
        showFlashMessage('Failed to disconnect streamer. Check server logs.', 'error')
    }
})

startBtn.addEventListener("click", async () => {
    // make sure connection is established
    if (connectionStatus) {
        const symbol = symbolInput.value.trim().toUpperCase()

        if (!symbol) {
            showFlashMessage("Please enter a symbol.")
            return
        }

        try {
            // Ask server to subscribe
            const resp = await fetch("/api/subscribe", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol: symbol }),
            })
            if (!resp.ok) {
                const txt = await resp.text().catch(() => resp.statusText)
                showFlashMessage("Subscribe failed: " + resp.status + " " + txt, 'error')
                return
            }
            const body = await resp.json()
            if (body && body.ok && body.symbol === symbol) {
                symbolStatus.textContent = `Symbol: ${body.symbol}`
                symbolInput.disabled = true
                showFlashMessage("Subscribed: " + body.symbol)
            } else if (body && body.ok && body.symbol !== symbol) {
                symbolStatus.textContent = `Symbol: ${body.symbol}`
                symbolInput.disabled = true
                showFlashMessage("Subscribe response: " + JSON.stringify(body))
            } else {
                symbolStatus.textContent = `Symbol: N/A`
                showFlashMessage("Subscribe failed: " + JSON.stringify(body), 'error')
            }
        } catch (err) {
            console.error("subscribe error", err)
            showFlashMessage("Subscribe failed check server logs", 'error')
        }
    } else {
        showFlashMessage("Please connect the streamer first.", 'error')
    }
})

stopBtn.addEventListener("click", async () => {
    const symbol = symbolInput.value.trim().toUpperCase()

    if (!symbol) {
        showFlashMessage("Please enter a symbol.")
        return
    }

    try {
        const resp = await fetch("/api/unsubscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol: symbol }),
        })
        if (!resp.ok) {
            showFlashMessage("Unsubscribe failed: " + resp.statusText, 'error')
            return
        }
        const body = await resp.json()
        
        if (body && body.ok) {
            symbolStatus.textContent = `Symbol: N/A`
            streamMessagesContainer.innerHTML = ""
            symbolInput.disabled = false
            showFlashMessage("Unsubscribed successfully.")
        } else if (body && body.error) {
            showFlashMessage("Unsubscribe failed: " + body.error, 'error')
        } else {
            showFlashMessage("Unsubscribe failed: " + JSON.stringify(body), 'error')
        }
    } catch (err) {
        console.error("unsubscribe error", err)
        showFlashMessage("Unsubscribe failed check server logs", 'error')
    }
})

function showFlashMessage(message, type = 'success') {
    const duration = 3000; // 3 seconds

    // 1. Set content and type
    flashMessage.textContent = message;
    flashMessage.className = 'flash-message'; // Reset classes
    if (type === 'error') {
        flashMessageContainer.classList.add('error');
    }

    // 2. SHOW the message by removing the 'hidden' class
    // We use a slight delay with setTimeout to ensure the browser registers the class removal
    // for the CSS transition to work smoothly (though for simple visibility toggle, removing the class usually suffices).
    setTimeout(() => {
        flashMessageContainer.classList.remove('hidden');
    }, 50);


    // 3. HIDE the message after the duration
    setTimeout(() => {
        flashMessageContainer.classList.add('hidden');
    }, duration);
}