# Lancement du projet

## Preparation initiale

1. Installer et démarrer Docker Desktop.
2. Garder Ollama installé sur Windows et vérifier que le modèle `qwen2.5:7b` est disponible.
3. Pour que l'API en conteneur puisse joindre Ollama, configurer Ollama pour écouter sur
   `0.0.0.0:11434`, puis redémarrer Ollama. Ne pas exposer ce port à des réseaux non fiables ;
   vérifier le pare-feu Windows.
4. Si nécessaire, créer le fichier `.env` à partir de `.env.example` et choisir des ports libres.
5. Importer `api/n8n/workflow_factures.json` dans n8n et activer le workflow Webhook.
   Si un ancien workflow du même nom est déjà présent, le mettre à jour ou le désactiver
   avant d'activer la nouvelle version. La réception par e-mail est facultative et demande
   une credential IMAP configurée dans n8n.

## À chaque session

Depuis la racine du dépôt, exécuter une seule commande :

```powershell
docker compose up -d --build
```

Ollama doit déjà être lancé sur Windows. Arrêter toute ancienne API ou interface Streamlit
lancée directement sur Windows avant le premier démarrage Compose.

## Vérifications

| Service | Adresse |
|---|---|
| Interface Streamlit | http://localhost:9400 |
| n8n | http://localhost:<N8N_PORT> (valeur actuelle dans `.env` : 5800) |
| Documentation API | http://localhost:11435/docs |

Les notifications e-mail apparaissent sur la page d'accueil après traitement par n8n.
Elles indiquent le nombre de pièces jointes reçues, celles traitées et leur statut.

## Arrêt

```powershell
docker compose down
```

Les données SQLite, les fichiers de factures et les workflows n8n sont conservés dans les
volumes/dossiers persistants après l'arrêt des conteneurs.
