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
# À faire une seule fois
copy .env.example .env
# Ajuster les ports dans .env si nécessaire
```

Ollama reste installé nativement sous Windows. Pour que l'API en conteneur y accède,
Ollama doit écouter sur une interface accessible depuis Docker (`OLLAMA_HOST=0.0.0.0:11434`).
Ne rendez pas le port 11434 accessible à des réseaux non fiables ; vérifiez les règles du pare-feu Windows.

Importer `api/n8n/workflow_factures.json` dans n8n et activer le workflow Webhook.
La branche e-mail enregistre un bilan des pièces jointes traitées ; Streamlit affiche les
dernières notifications et leur nombre, avec actualisation automatique. La réception IMAP
demande la configuration de ses identifiants dans n8n.

## Lancement

Depuis la racine du projet, une commande démarre les services conteneurisés n8n, l'API
et l'interface :

```powershell
docker compose up -d --build
```

Ollama doit déjà tourner sur Windows. Arrêter les anciens serveurs API et Streamlit lancés
directement sur Windows avant le premier démarrage Compose.

Pour arrêter les conteneurs :

```powershell
docker compose down
```

| Service | Adresse |
|---|---|
| Interface Streamlit | http://localhost:9400 |
| n8n | http://localhost:<N8N_PORT> (valeur actuelle dans `.env` : 5800) |
| Documentation API | http://localhost:11435/docs |

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
