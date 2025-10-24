## Stock & Crypto Streamer

### End-to-End Stock & Crypto Stream & Analyzer

How to start the app:

```powershell
python -m venv .venv (or use python3)
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
uvicorn server.app_server:app --host 0.0.0.0 --port 8000
```