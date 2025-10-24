
const connectBtn = document.getElementById('btn-connect-stream')
const disconnectBtn = document.getElementById('btn-disconnect-stream')
const startBtn = document.getElementById('btn-start-stream')
const stopBtn = document.getElementById('btn-stop-stream')
const streamerStatus = document.getElementById('status-stream')
const symbolInput = document.getElementById('input-symbol')
const symbolStatus = document.getElementById('status-symbol')
const streamMessagesContainer = document.getElementById('stream-messages-container')

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
    lineSeries = chart.addSeries(LightweightCharts.LineSeries, { 
    color: '#2b8cff', 
    lineWidth: 2 
})
} else {
    console.warn('Chart container or LightweightCharts missing')
}

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

        // Try to extract price and timestamp; adapt to your Alpaca message shape
        const price = item.p ?? item.price ?? item.last ?? item.px
        const tsMs = parseTimestampMs(item)

        if (price !== undefined && tsMs !== null && lineSeries) {
            // Lightweight-Charts expects time as unix seconds (integer) or ISO string
            const time = Math.round(tsMs / 1000)
            lineSeries.update({ time: time, value: Number(price) })
        } else {
            // If no chart, optionally log raw message to console
            console.debug('Forwarded item (no chart):', item)
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
            alert('Streamer is already connected.')
            connectionStatus = true
            streamerStatus.textContent = 'Stream: Connected'
        } else if (body && body.running && body.started) {
            alert('Streamer started successfully.')
            connectionStatus = true
            streamerStatus.textContent = 'Stream: Connected'
            symbolStatus.textContent = 'Symbol: N/A'
        } else {
            alert("Unexpected response: " + JSON.stringify(body))
        }
    } catch (err) {
        console.error('Failed to connect streamer:', err)
        alert('Failed to start streamer. Check server logs.') 
    }
})

disconnectBtn.addEventListener('click', async function () {
    try {
        const resp = await fetch('/api/disconnect', { method: 'POST' })
        // http request failed
        if (!resp.ok) {
            const text = await resp.text().catch(() => resp.statusText)
            alert(`Request failed: ${resp.status} ${resp.statusText}`)
            return
        }

        const body = await resp.json()
        if (body && body.ok && body.stopped) {
            alert('Streamer disconnected successfully.')
            connectionStatus = false
            streamerStatus.textContent = 'Stream: Disconnected'
            symbolStatus.textContent = 'Symbol: N/A'
        } else {
            alert("Unexpected response: " + JSON.stringify(body))
        }
    } catch (err) {
        console.error('Failed to disconnect streamer:', err)
        alert('Failed to disconnect streamer. Check server logs.')  
    }
})

startBtn.addEventListener("click", async () => {
    // make sure connection is established
    if (connectionStatus) {
        const symbol = symbolInput.value.trim().toUpperCase()

        if (!symbol) {
            alert("Please enter a symbol.")
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
                alert("Subscribe failed: " + resp.status + " " + txt)
                return
            }
            const body = await resp.json()
            if (body && body.ok && body.symbol === symbol) {
                symbolStatus.textContent = `Symbol: ${body.symbol}`
                symbolInput.disabled = true
                alert("Subscribed: " + body.symbol)
            } else if (body && body.ok && body.symbol !== symbol) {
                symbolStatus.textContent = `Symbol: ${body.symbol}`
                symbolInput.disabled = true
                alert("Subscribe response: " + JSON.stringify(body))
            } else {
                symbolStatus.textContent = `Symbol: N/A`
                alert("Subscribe failed: " + JSON.stringify(body))
            }
        } catch (err) {
            console.error("subscribe error", err)
            alert("Subscribe failed check server logs")
        }
    } else {
        alert("Please connect the streamer first.")
    }
})

stopBtn.addEventListener("click", async () => {
    const symbol = symbolInput.value.trim().toUpperCase()

    if (!symbol) {
        alert("Please enter a symbol.")
        return
    }

    try {
        const resp = await fetch("/api/unsubscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol: symbol }),
        })
        if (!resp.ok) {
            alert("Unsubscribe failed: " + resp.statusText)
            return
        }
        const body = await resp.json()
        
        if (body && body.ok) {
            symbolStatus.textContent = `Symbol: N/A`
            streamMessagesContainer.innerHTML = ""
            symbolInput.disabled = false
            alert("Unsubscribed successfully.")
        } else if (body && body.error) {
            alert("Unsubscribe failed: " + body.error)
        } else {
            alert("Unsubscribe failed: " + JSON.stringify(body))
        }
    } catch (err) {
        console.error("unsubscribe error", err)
        alert("Unsubscribe failed check server logs")
    }
})
