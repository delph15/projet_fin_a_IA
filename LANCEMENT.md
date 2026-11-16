# Lancer le projet

## Une seule fois

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python generateur/generateur.py
```

## À chaque session

**Terminal 1 — Docker (n8n)**
```powershell
docker compose up -d
```
Le port local par défaut est `5678`. Si Windows le réserve, choisissez un port
libre et non réservé puis changez `N8N_PORT` dans `.env` (par exemple `5800`) ;
l'URL du webhook suit ce réglage.

**Terminal 2 — API**
```powershell
.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "${PWD}\api"
python -m uvicorn api.main:app --reload --port 8000
```

**Terminal 3 — Interface**
```powershell
.venv\Scripts\Activate.ps1
streamlit run interface/app.py
```

## Vérifications

| Service | URL |
|---|---|
| API | http://localhost:8000/docs |
| Interface | http://localhost:8501 |
| n8n | http://localhost:5678 (port par défaut) |

> Ollama tourne déjà en arrière-plan — ne pas le relancer.
