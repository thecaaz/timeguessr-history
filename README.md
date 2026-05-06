# timeguessr-history

MVP to collect daily TimeGuessr challenges and serve them via a small web UI.

Quickstart (local):

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -m playwright install
```

Run a quick DB test:

```bash
python3 scripts/test_db.py
```

Run the web server:

```bash
uvicorn server.app:app --reload --port 8000
# open http://localhost:8000
```

Collector (manual run):

```bash
python3 collector/run.py --date 2026-05-05 --headless
```

Docker (optional):

```bash
docker-compose up --build
```
