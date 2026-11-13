# Automatisation intelligente du traitement des factures

Mini-projet de Master 1 Informatique — 20 jours.

## Objectif

Transformer une facture PDF ou image en enregistrement structuré, contrôlé, puis validé par un humain. Budget logiciel et API : 0 €.

## Chaîne de traitement

```
Dépôt fichier → n8n → API FastAPI (OCR → extraction → contrôles) → SQLite → revue Streamlit → validée / rejetée / doublon
```

## Prérequis

| Outil | Version | Notes |
|---|---|---|
| Python | 3.13 | |
| Tesseract | 5.5 | langues `fra`, `eng` |
| Ollama | dernier | CPU uniquement (`CUDA_VISIBLE_DEVICES=-1`) |
| Docker Desktop | dernier | pour n8n |

## Installation

```powershell
# 1. Cloner le dépôt
git clone <url>
cd projet_fin_a_IA

# 2. Créer l'environnement virtuel
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer les variables d'environnement
copy .env.example .env
# Éditer .env si besoin

# 5. Démarrer n8n
docker compose up -d
```

## Lancement

```powershell
# API FastAPI
uvicorn api.main:app --reload --port 8000

# Interface Streamlit
streamlit run interface/app.py
```

## Structure

```
generateur/      création des factures fictives
donnees/         jeux dev / test / vérité terrain
api/             FastAPI : OCR, extraction, contrôles, SQLite
interface/       Streamlit : revue humaine
n8n/             workflow exporté en JSON
evaluation/      scripts de mesure et résultats
tests/           pytest
```

## Champs extraits

`fournisseur`, `numero_facture`, `date`, `montant_ht`, `tva`, `montant_ttc`
