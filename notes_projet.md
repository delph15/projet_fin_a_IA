# Notes projet — Automatisation du traitement des factures

## Enchaînement des outils

```
Facture (PDF ou image)
        │
        ▼
   n8n OU Streamlit          ← tu déposes le fichier ici
        │
        │  envoie le fichier en POST
        ▼
   API FastAPI (port 8000)
        │
        ├─ 1. OCR
        │      pdfplumber si PDF natif  → texte propre
        │      Tesseract si image       → texte approximatif
        │
        ├─ 2. Extraction regex
        │      cherche les 6 champs avec des patterns
        │
        ├─ 3. Extraction LLM
        │      envoie le texte à Ollama (qwen2.5:7b)
        │      Ollama répond en JSON
        │
        ├─ 4. Fusion
        │      compare regex vs LLM champ par champ
        │      accord → confiance haute
        │      désaccord → confiance basse + signaler
        │
        ├─ 5. Contrôles métier
        │      HT + TVA = TTC ?
        │      date valide ?
        │      doublon (SHA-256 + fournisseur+numéro) ?
        │
        ├─ 6. SQLite
        │      enregistre tout en base
        │
        └─ répond avec le JSON de la facture + statut
                │
                ▼
         Streamlit (port 8501)
                │
                ├─ affiche les champs extraits
                ├─ affiche la confiance de chaque champ
                ├─ signale les anomalies en rouge
                │
                └─ toi tu cliques "Valider" ou "Rejeter"
                        │
                        ▼
                   Statut final en base
                   (validée ou rejetée)
```

**Ollama** tourne en dehors de tout ça, en tâche de fond sur Windows — l'API l'appelle directement via `http://localhost:11434`.

**n8n** est optionnel : il automatise juste le dépôt. Sans lui, tu fais la même chose manuellement depuis Streamlit.

---

## Si on dynamise le projet (infrastructure et périmètre)

**Données**
- Vraies factures de vrais fournisseurs (données personnelles → RGPD à gérer)
- Formats variés et imprévisibles, pas seulement 4 modèles connus

**Sécurité**
- Authentification (login/mot de passe) sur Streamlit et l'API
- HTTPS au lieu de HTTP
- Secrets chiffrés, pas dans `.env`

**Infrastructure**
- Base PostgreSQL au lieu de SQLite
- API déployée sur un serveur (pas `localhost`)
- Ollama remplacé par une API LLM payante (OpenAI, etc.) pour la vitesse et la qualité
- n8n connecté à une vraie boîte mail ou un cloud storage (S3, Google Drive) au lieu d'un dossier local

**Performance**
- File d'attente pour traiter plusieurs factures en parallèle
- Tesseract remplacé par un OCR professionnel (Azure, Google Vision) pour les images dégradées — c'est le vrai point faible actuel (0% sur images)

**Métier**
- Gestion des utilisateurs (qui a validé quoi)
- Export comptable (CSV, ERP)
- Alertes email/Slack quand une facture est à vérifier

**Ce qui ne change pas** : la logique de base (OCR → extraction → fusion → contrôles → validation humaine) reste identique.

---

## Si on dynamise seulement les fonctionnalités déjà présentes

**OCR**
- Prétraitement image plus agressif (déskew automatique, amélioration du contraste) → passer de 0% à quelque chose sur les images dégradées
- Choisir automatiquement la langue (fra/eng) selon le contenu détecté

**Extraction regex**
- Ajouter des patterns pour d'autres formats de numéro de facture (pas seulement `FAC-AAAA-NNNN`)
- Gérer les dates en format français (`14/10/2026` → ISO)
- Gérer les montants en livres sterling, dollars, etc.

**Extraction LLM**
- Tester `qwen2.5:7b` vs d'autres modèles Ollama disponibles localement
- Ajuster le prompt selon le type de document détecté

**Fusion**
- Affiner les seuils de confiance (actuellement fixes : +0.05 accord, -0.15 désaccord)
- Ajouter un 3ème vote si regex et LLM divergent

**Contrôles métier**
- Vérifier que le numéro de facture respecte un format connu du fournisseur
- Détecter les montants anormaux (trop élevés, négatifs)

**Interface Streamlit**
- Filtrer par fournisseur, par date, par statut
- Afficher les statistiques (nombre de factures validées ce mois, taux d'erreur)
- Permettre de corriger manuellement un champ avant de valider

**Évaluation**
- Lancer automatiquement `evaluer.py` après chaque modification du code pour détecter les régressions
