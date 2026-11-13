# CLAUDE.md — Projet 2 : Automatisation intelligente du traitement des factures

Ce fichier donne à Claude Code le contexte et les décisions déjà prises pour ce projet.
Le lire en entier avant toute action.

## 1. Le projet en bref

Mini-projet de Master 1 Informatique (IA et automatisation intelligente), 20 jours de travail.
Objectif : un MVP local qui transforme une facture PDF ou image en enregistrement structuré,
contrôlé, puis validé par un humain. Budget logiciel et API : 0 €.

Chaîne de traitement :
dépôt (Streamlit ou dossier surveillé) → n8n (déclenche et route) → API FastAPI
(OCR → extraction regex + LLM → contrôles métier) → SQLite → revue humaine (Streamlit) → validée / rejetée / doublon.

Champs extraits (6) : fournisseur, numero_facture, date, montant_ht, tva, montant_ttc.

## 2. Cadre académique — règles à respecter

- L'étudiante doit comprendre et pouvoir expliquer chaque fichier à la soutenance :
  expliquer brièvement ce que fait chaque fichier créé et les choix faits.
- Le rapport académique est rédigé par l'étudiante elle-même : ne pas le rédiger.
  Aider à le structurer, relire, ou produire des chiffres et tableaux de résultats est possible.
- Pas d'application de production : pas d'authentification, pas d'intégration payante,
  pas d'entraînement de modèle, pas de fonctionnalités secondaires hors cahier des charges.
- Le système doit être comparé à des méthodes de référence (saisie manuelle, regex seules).

## 3. Façon de travailler (préférences de l'étudiante)

- Avancer pas à pas : une étape à la fois, expliquer ce qui est fait avant de passer à la suite.
- Ne jamais écraser du code existant : un fichier modifié garde tout ce qui y est déjà,
  sauf demande explicite. Lire un fichier avant de le modifier.
- Quand du code est montré dans la conversation, montrer le fichier en entier,
  pas des morceaux à chercher et remplacer.
- Langue : français pour les explications, les commentaires et les messages de l'interface.
  Noms de variables et de fonctions en français sans accents (ex. `montant_ttc`, `extraire_champs`).
- Faire des commits Git clairs et fréquents (messages en français), seulement quand l'étudiante le demande.

## 4. Environnement de la machine (mesuré au « jour 0 »)

| Élément | Valeur |
|---|---|
| Système | Windows 11, terminal PowerShell |
| Dossier du projet | `D:\projet_fin_a_IA` |
| Processeur / RAM | Intel Core 6e génération, 4 cœurs / 16 Go |
| GPU | GeForce GTX 960M, 2 Go, pilote 398.35 (2018) : NON utilisé |
| Python | 3.13 |
| Tesseract | 5.5, installé dans `C:\Program Files\Tesseract-OCR`, langues `fra`, `eng`, `osd` |
| Ollama | installé nativement sur Windows (pas dans Docker), `http://localhost:11434` |
| Docker Desktop | installé ; sert à n8n (vérifier qu'il est démarré) |

### Ollama : processeur uniquement (important)
Le GPU fait planter Ollama (erreur `0xc0000005`). Ollama doit tourner sur le processeur :
- variables d'environnement utilisateur : `CUDA_VISIBLE_DEVICES=-1` et `OLLAMA_VULKAN=0` ;
- par sécurité, envoyer aussi `"options": {"num_gpu": 0, "temperature": 0}` dans chaque appel à l'API Ollama ;
- utiliser `keep_alive` pour garder le modèle chargé (chargement à froid du 7B : environ 53 s).

### Modèles
| Modèle | Rôle | Résultat du test (1 facture texte) |
|---|---|---|
| `qwen2.5:7b` | modèle principal | 6/6 champs, 22 s par facture |
| `qwen2.5:3b` | développement rapide et comparaison | 2/6 (format non respecté : « 555,00 », préfixe « FACTURE N° »), 12 s |

Conséquence : une étape de normalisation est indispensable (montants français → nombres,
nettoyage des préfixes, dates en ISO `AAAA-MM-JJ`).

## 5. Stack

| Composant | Outil |
|---|---|
| Génération des factures | Python : fpdf2 ou ReportLab, Faker (locale `fr_FR`), Pillow |
| Lecture PDF texte | pdfplumber |
| OCR des images | Tesseract via pytesseract (langue `fra`), prétraitement Pillow/OpenCV |
| Extraction | regex + Ollama (`format: "json"`) |
| API | FastAPI + Uvicorn |
| Base de données | SQLite |
| Orchestration | n8n Community Edition (Docker) |
| Interface | Streamlit |
| Tests | pytest |

Depuis le conteneur n8n, l'API et Ollama tournant sur Windows sont joignables via `host.docker.internal`.

## 6. Structure du dépôt prévue

```
projet_fin_a_IA/
├── generateur/          # création des factures fictives et de la vérité terrain
├── donnees/
│   ├── dev/             # jeu de développement
│   ├── test/            # jeu de test (ne pas utiliser avant l'évaluation)
│   └── verite_terrain/  # un JSON par facture
├── api/                 # FastAPI : OCR, extraction, normalisation, contrôles, base
├── interface/           # Streamlit
├── n8n/                 # workflow exporté en JSON
├── evaluation/          # script de mesure et résultats
├── tests/               # pytest
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## 7. Données

- 30 factures originales sur 4 modèles de mise en page (A, B, C, D), générées par script à graine fixe.
- Environ un tiers converties en images dégradées (flou, légère rotation, bruit).
- 5 doublons volontaires en plus (copie exacte, rescan, même facture renommée) : 35 fichiers au total.
- Une vérité terrain JSON par facture.
- Séparation :
  - `dev/` : 10 factures, modèles A, B, C → mise au point des regex et du prompt ;
  - `test/` : 20 factures dont le modèle D jamais vu + les 5 doublons → évaluation finale uniquement.
- Ne jamais régler les regex ou le prompt en regardant le jeu de test.
- Données 100 % fictives : aucune facture réelle, aucune donnée personnelle.

## 8. Format commun d'une facture extraite

```json
{
  "fichier": "facture_012.pdf",
  "fournisseur":    {"valeur": "SARL Informatique Plus", "confiance": 0.95, "source": "llm"},
  "numero_facture": {"valeur": "FAC-2026-0147", "confiance": 0.98, "source": "regex"},
  "date":           {"valeur": "2026-10-14", "confiance": 0.98, "source": "regex"},
  "montant_ht":     {"valeur": 555.00, "confiance": 0.97, "source": "regex"},
  "tva":            {"valeur": 111.00, "confiance": 0.97, "source": "regex"},
  "montant_ttc":    {"valeur": 666.00, "confiance": 0.97, "source": "regex"},
  "controles": {"arithmetique": true, "date_valide": true, "doublon": false},
  "statut": "prete"
}
```

Statuts : `recue`, `extraite`, `a_verifier`, `prete`, `validee`, `rejetee`, `doublon`.

## 9. Règles métier (non négociables)

- Aucune facture n'est `validee` sans action humaine.
- Un champ absent reste `null` : ne jamais inventer une valeur. Vérifier que la valeur du LLM apparaît dans le texte OCR.
- Contrôle arithmétique : HT + TVA = TTC, tolérance 0,01 €.
- Doublons : empreinte du fichier (SHA-256) ET couple fournisseur + numéro de facture.
- Un champ est signalé (`a_verifier`) si regex et LLM divergent, si le contrôle arithmétique échoue,
  ou si la confiance OCR est faible.
- Un OCR vide ou un LLM indisponible → statut `a_verifier`, jamais un plantage.
- Aucune API payante, aucun mot de passe ni secret dans le dépôt (`.env` dans `.gitignore`, `.env.example` fourni).

## 10. Calendrier imposé (5 phases)

| Jours | Phase | Livrable |
|---|---|---|
| J1–J3 | Analyse et cadrage | Cahier des charges + plan de rapport (validation de l'encadrant à J3) |
| J4–J6 | Conception et préparation | Architecture, jeux de données, environnement opérationnel |
| J7–J13 | Développement du MVP | Première version de bout en bout (jalon J13) |
| J14–J16 | Tests et évaluation | Résultats, métriques, analyse des limites |
| J17–J20 | Rapport et soutenance | Rapport PDF, code, workflow n8n en JSON, démonstration |

Ordre de développement prévu : OCR → extraction regex (méthode de référence) → extraction LLM
+ fusion + confiance → API + contrôles + SQLite → workflow n8n → interface Streamlit → intégration.

## 11. Évaluation (pour le rapport)

Comparer 4 configurations sur le jeu de test : saisie manuelle (chronométrée, 10 factures),
regex seules, LLM seul, système complet. Mesures : précision par champ, factures entièrement
correctes, rappel/précision des doublons, part des erreurs signalées, temps par facture.
Analyses : PDF natifs vs images ; modèles A-B-C vs D ; 3B vs 7B.
Noter les paramètres de reproduction : modèle, température, prompt, version de Tesseract, graine.

## 12. État d'avancement

- [x] Jour 0 : Python, Tesseract (fra), Ollama (CPU) et modèles validés
- [ ] Jour 0 : Docker Desktop à démarrer et vérifier
- [ ] Étape suivante : créer la structure du dépôt, `.gitignore`, `.env.example`, `requirements.txt`,
      `README.md`, `docker-compose.yml` (n8n), puis initialiser Git
- [ ] Ensuite : le générateur de factures (`generateur/`)

Le script `test_jour0.py` (à la racine) vérifie l'environnement : `python test_jour0.py --modele qwen2.5:7b`.
