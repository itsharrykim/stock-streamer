const connectBtn = document.getElementById('btn-connect-stream');
const disconnectBtn = document.getElementById('btn-disconnect-stream');
const startBtn = document.getElementById('btn-start-stream');
const stopBtn = document.getElementById('btn-stop-stream');
const streamerStatus = document.getElementById('status-stream');

connectBtn.addEventListener('click', async function () {
    try {
        const resp = await fetch('/api/connect', { method: 'POST' });

        // http request failed
        if (!resp.ok) {
            const text = await resp.text().catch(() => resp.statusText);
            alert(`Request failed: ${resp.status} ${resp.statusText}`);
            return;
        }

        const body = await resp.json();
        if (body && body.running && body.started === false) {
            alert('Streamer is already connected.');
            streamerStatus.textContent = 'Stream: Connected';
        } else if (body && body.running && body.started) {
            alert('Streamer started successfully.');
            streamerStatus.textContent = 'Stream: Connected';
        } else {
            alert("Unexpected response: " + JSON.stringify(body));
        }
    } catch (err) {
        console.error('Failed to connect streamer:', err);
        alert('Failed to start streamer. Check server logs.');  
    }
});

disconnectBtn.addEventListener('click', async function () {
    try {
        const resp = await fetch('/api/disconnect', { method: 'POST' });    
        // http request failed
        if (!resp.ok) {
            const text = await resp.text().catch(() => resp.statusText);
            alert(`Request failed: ${resp.status} ${resp.statusText}`);
            return;
        }

        const body = await resp.json();
        if (body && body.ok && body.stopped) {
            alert('Streamer disconnected successfully.');
            streamerStatus.textContent = 'Stream: Disconnected';
        } else {
            alert("Unexpected response: " + JSON.stringify(body));
        }
    } catch (err) {
        console.error('Failed to disconnect streamer:', err);
        alert('Failed to disconnect streamer. Check server logs.');  
    }
})