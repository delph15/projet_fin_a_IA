# main.py - API FastAPI : reception d'une facture et pipeline complet
#
# Lancement :
#   uvicorn api.main:app --reload --port 8000
#
# Endpoints :
#   POST /factures/                soumettre un fichier (via n8n webhook)
#   GET  /factures/                lister toutes les factures (?statut=...)
#   GET  /factures/{id}            detail d'une facture
#   GET  /factures/{id}/fichier    telecharger le fichier original
#   PUT  /factures/{id}/corriger   corriger des champs (action humaine)
#   PUT  /factures/{id}/valider    valider (action humaine)
#   PUT  /factures/{id}/rejeter    rejeter (action humaine)

import os
import shutil
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from base import (
    corriger_champs,
    enregistrer_notification_email,
    initialiser_base,
    inserer_facture,
    lister_factures,
    lister_notifications_email as charger_notifications_email,
    mettre_a_jour_statut,
    obtenir_connexion,
    obtenir_facture,
)
from controles import appliquer_controles
from extraction import extraire_par_regex
from extraction_llm import extraire_par_llm
from fusion import fusionner
from ocr import extraire_texte

app = FastAPI(
    title="API Traitement de Factures",
    description="Pipeline OCR → extraction → controles → validation humaine",
    version="0.2.0",
)

# Dossier de conservation des fichiers originaux
DOSSIER_ORIGINAUX = Path(os.getenv("DOSSIER_ORIGINAUX", "donnees/originaux"))


class ResultatFichierEmail(BaseModel):
    fichier: str
    statut: str | None = None
    id_facture: int | None = None
    erreur: str | None = None


class NotificationEmail(BaseModel):
    cle_email: str = Field(min_length=1)
    sujet: str
    nb_fichiers_recus: int = Field(ge=1)
    fichiers: list[ResultatFichierEmail] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Initialisation au demarrage
# ---------------------------------------------------------------------------

@app.on_event("startup")
def demarrage():
    DOSSIER_ORIGINAUX.mkdir(parents=True, exist_ok=True)
    conn = obtenir_connexion()
    initialiser_base(conn)
    conn.close()


# ---------------------------------------------------------------------------
# Utilitaire
# ---------------------------------------------------------------------------

def assembler_facture(nom_fichier: str, chemin_original: str, champs: dict, resultats_controles: dict) -> dict:
    return {
        "fichier":          nom_fichier,
        "chemin_original":  chemin_original,
        "empreinte":        resultats_controles["empreinte"],
        "statut":           resultats_controles["statut"],
        "champs":           champs,
        "controles":        resultats_controles["controles"],
    }


# ---------------------------------------------------------------------------
# POST /factures/ - soumettre un fichier (appele par n8n)
# ---------------------------------------------------------------------------

@app.post("/factures/", status_code=201)
def soumettre_facture(
    fichier: UploadFile = File(...),
    source: str = Form(default="interface"),
):
    """
    Recoit un fichier PDF ou image, applique le pipeline complet et
    enregistre le resultat en base. Appele par le webhook n8n.
    """
    if source not in {"interface", "email"}:
        raise HTTPException(status_code=400, detail="Source non supportee")

    extensions_acceptees = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}
    suffixe = Path(fichier.filename).suffix.lower()
    if suffixe not in extensions_acceptees:
        raise HTTPException(status_code=400, detail=f"Format non supporte : {suffixe}")

    # Sauvegarde permanente du fichier original
    chemin_dest = DOSSIER_ORIGINAUX / fichier.filename
    # Eviter les collisions de nom
    compteur = 1
    while chemin_dest.exists():
        stem = Path(fichier.filename).stem
        chemin_dest = DOSSIER_ORIGINAUX / f"{stem}_{compteur}{suffixe}"
        compteur += 1

    with open(chemin_dest, "wb") as f:
        shutil.copyfileobj(fichier.file, f)

    try:
        # 1. OCR
        texte, conf_ocr = extraire_texte(chemin_dest)

        # 2. Extraction
        res_regex = extraire_par_regex(texte)
        res_llm   = extraire_par_llm(texte)

        # 3. Fusion
        champs = fusionner(res_regex, res_llm, conf_ocr)

        # 4. Controles metier + statut
        conn = obtenir_connexion()
        initialiser_base(conn)
        resultats_ctrl = appliquer_controles(champs, chemin_dest, conn)

        # 5. Insertion en base
        facture = assembler_facture(
            fichier.filename,
            str(chemin_dest),
            champs,
            resultats_ctrl,
        )
        facture["source"] = source
        id_facture = inserer_facture(conn, facture)
        conn.close()

    except Exception as exc:
        chemin_dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "id":        id_facture,
        "fichier":   fichier.filename,
        "source":    source,
        "statut":    resultats_ctrl["statut"],
        "champs":    {
            cle: {
                "valeur":    champs[cle]["valeur"],
                "confiance": champs[cle]["confiance"],
                "source":    champs[cle]["source"],
            }
            for cle in ("fournisseur", "numero_facture", "date", "montant_ht", "tva", "montant_ttc")
        },
        "controles": resultats_ctrl["controles"],
        "meta":      champs.get("meta", {}),
    }


# ---------------------------------------------------------------------------
# GET /factures/ - lister
# ---------------------------------------------------------------------------

@app.get("/factures/")
def lister(statut: str = Query(default=None)):
    conn = obtenir_connexion()
    rows = lister_factures(conn, statut)
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Notifications des factures reçues par e-mail
# ---------------------------------------------------------------------------

@app.post("/notifications/email/", status_code=201)
def creer_notification_email(notification: NotificationEmail):
    if len(notification.fichiers) != notification.nb_fichiers_recus:
        raise HTTPException(
            status_code=400,
            detail="Le nombre de résultats doit correspondre aux pièces jointes reçues",
        )

    conn = obtenir_connexion()
    try:
        id_notification = enregistrer_notification_email(
            conn,
            notification.model_dump(),
        )
    finally:
        conn.close()
    return {"id": id_notification}


@app.get("/notifications/email/")
def lister_notifications_email(limite: int = Query(default=5, ge=1, le=20)):
    conn = obtenir_connexion()
    try:
        return charger_notifications_email(conn, limite)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /factures/{id} - detail
# ---------------------------------------------------------------------------

@app.get("/factures/{id_facture}")
def detail_facture(id_facture: int):
    conn = obtenir_connexion()
    facture = obtenir_facture(conn, id_facture)
    conn.close()
    if facture is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    return facture


# ---------------------------------------------------------------------------
# GET /factures/{id}/fichier - telecharger le fichier original
# ---------------------------------------------------------------------------

@app.get("/factures/{id_facture}/fichier")
def telecharger_fichier(id_facture: int):
    """Retourne le fichier original conserve sur disque."""
    conn = obtenir_connexion()
    facture = obtenir_facture(conn, id_facture)
    conn.close()
    if facture is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")

    chemin = facture.get("chemin_original")
    if not chemin or not Path(chemin).exists():
        raise HTTPException(status_code=404, detail="Fichier original introuvable")

    return FileResponse(chemin, filename=facture.get("fichier", Path(chemin).name))


# ---------------------------------------------------------------------------
# PUT /factures/{id}/corriger - correction humaine des champs
# ---------------------------------------------------------------------------

@app.put("/factures/{id_facture}/corriger")
def corriger_facture(id_facture: int, corrections: dict):
    """
    Corrige un ou plusieurs champs extraits (action humaine).
    Corps JSON : {"fournisseur": "...", "montant_ht": 1000.0, ...}
    Les champs corriges passent en confiance 1.0 / source 'humain'.
    """
    conn = obtenir_connexion()
    ok = corriger_champs(conn, id_facture, corrections)
    conn.close()
    if not ok:
        raise HTTPException(status_code=400, detail="Correction impossible (id inconnu ou champs invalides)")
    return {"id": id_facture, "corrections_appliquees": list(corrections.keys())}


# ---------------------------------------------------------------------------
# PUT /factures/{id}/valider et /rejeter - actions humaines
# ---------------------------------------------------------------------------

@app.put("/factures/{id_facture}/valider")
def valider_facture(id_facture: int):
    conn = obtenir_connexion()
    ok = mettre_a_jour_statut(conn, id_facture, "validee")
    conn.close()
    if not ok:
        raise HTTPException(status_code=400, detail="Validation impossible (statut incompatible ou id inconnu)")
    return {"id": id_facture, "statut": "validee"}


@app.put("/factures/{id_facture}/rejeter")
def rejeter_facture(id_facture: int):
    conn = obtenir_connexion()
    ok = mettre_a_jour_statut(conn, id_facture, "rejetee")
    conn.close()
    if not ok:
        raise HTTPException(status_code=400, detail="Rejet impossible (statut incompatible ou id inconnu)")
    return {"id": id_facture, "statut": "rejetee"}
