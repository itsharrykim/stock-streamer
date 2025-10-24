let connectionStatus = false

const connectBtn = document.getElementById('btn-connect-stream')
const disconnectBtn = document.getElementById('btn-disconnect-stream')
const startBtn = document.getElementById('btn-start-stream')
const stopBtn = document.getElementById('btn-stop-stream')
const streamerStatus = document.getElementById('status-stream')
const symbolStatus = document.getElementById('status-symbol')
const streamMessagesContainer = document.getElementById('stream-messages-container')

// open forward socket to receive stream messages
const wsProto = location.protocol === "https:" ? "wss" : "ws"
const wsUrl = wsProto + "://" + location.host + "/ws"
const forwardWs = new WebSocket(wsUrl)

forwardWs.addEventListener("open", () => {
    console.log("Forward socket open", wsUrl)
})

forwardWs.addEventListener("message", (evt) => {
    try {
        const item = JSON.parse(evt.data)
        // try to show a compact line: timestamp | symbol | price
        const timestamp = item.t
        const symbol = item.s
        const price = item.p
        let line = JSON.stringify(item)
        
        if (timestamp || symbol || price) {
            const when = timestamp ? new Date(timestamp).toLocaleString() : ""
            line = `${when} | ${symbol} | ${price}`
        }

        if (streamMessagesContainer) {
            // create a new div for each message row
            const node = document.createElement("div")
            node.textContent = line
            streamMessagesContainer.appendChild(node)
            // keep the most recent ~100 lines
            while (streamMessagesContainer.childNodes.length > 100) streamMessagesContainer.removeChild(streamMessagesContainer.firstChild)
        }
    } catch (err) {
        console.error("parse forward message", err, evt.data)
    }
})

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
        const symbol = "FAKEPACA"
        
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
                alert("Subscribed: " + body.symbol)
            } else if (body && body.ok && body.symbol !== symbol) {
                symbolStatus.textContent = `Symbol: ${body.symbol}`
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
    symbol = "FAKEPACA"
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