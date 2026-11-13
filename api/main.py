# main.py - API FastAPI : reception d'une facture et pipeline complet
#
# Lancement :
#   uvicorn api.main:app --reload --port 8000
#
# Endpoints :
#   POST /factures/           soumettre un fichier (PDF ou image)
#   GET  /factures/           lister toutes les factures (filtre ?statut=...)
#   GET  /factures/{id}       detail d'une facture
#   PUT  /factures/{id}/valider  action humaine : valider
#   PUT  /factures/{id}/rejeter  action humaine : rejeter

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from base import initialiser_base, inserer_facture, lister_factures, mettre_a_jour_statut, obtenir_connexion, obtenir_facture
from controles import appliquer_controles
from extraction import extraire_par_regex
from extraction_llm import extraire_par_llm
from fusion import fusionner
from ocr import extraire_texte

app = FastAPI(
    title="API Traitement de Factures",
    description="Pipeline OCR → extraction → controles → validation humaine",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Initialisation de la base au demarrage
# ---------------------------------------------------------------------------

@app.on_event("startup")
def demarrage():
    conn = obtenir_connexion()
    initialiser_base(conn)
    conn.close()


# ---------------------------------------------------------------------------
# Utilitaire : assemblage du dict complet d'une facture
# ---------------------------------------------------------------------------

def assembler_facture(nom_fichier: str, champs: dict, resultats_controles: dict) -> dict:
    """Construit le dict pret a etre insere en base et retourne a l'appelant."""
    return {
        "fichier":    nom_fichier,
        "empreinte":  resultats_controles["empreinte"],
        "statut":     resultats_controles["statut"],
        "champs":     champs,
        "controles":  resultats_controles["controles"],
    }


# ---------------------------------------------------------------------------
# POST /factures/ - soumettre un fichier
# ---------------------------------------------------------------------------

@app.post("/factures/", status_code=201)
async def soumettre_facture(fichier: UploadFile = File(...)):
    """
    Recoit un fichier PDF ou image, applique le pipeline complet et
    enregistre le resultat en base.
    """
    extensions_acceptees = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}
    suffixe = Path(fichier.filename).suffix.lower()
    if suffixe not in extensions_acceptees:
        raise HTTPException(status_code=400, detail=f"Format non supporte : {suffixe}")

    # Sauvegarde temporaire du fichier uploade
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffixe) as tmp:
        shutil.copyfileobj(fichier.file, tmp)
        chemin_tmp = Path(tmp.name)

    try:
        # 1. OCR
        texte, conf_ocr = extraire_texte(chemin_tmp)

        # 2. Extraction
        res_regex = extraire_par_regex(texte)
        res_llm   = extraire_par_llm(texte)

        # 3. Fusion
        champs = fusionner(res_regex, res_llm, conf_ocr)

        # 4. Controles metier + statut
        conn = obtenir_connexion()
        initialiser_base(conn)
        resultats_ctrl = appliquer_controles(champs, chemin_tmp, conn)

        # 5. Insertion en base
        facture = assembler_facture(fichier.filename, champs, resultats_ctrl)
        id_facture = inserer_facture(conn, facture)
        conn.close()

    finally:
        chemin_tmp.unlink(missing_ok=True)

    return {
        "id":       id_facture,
        "fichier":  fichier.filename,
        "statut":   resultats_ctrl["statut"],
        "champs":   {
            cle: {
                "valeur":    champs[cle]["valeur"],
                "confiance": champs[cle]["confiance"],
                "source":    champs[cle]["source"],
            }
            for cle in ("fournisseur", "numero_facture", "date", "montant_ht", "tva", "montant_ttc")
        },
        "controles":  resultats_ctrl["controles"],
        "meta":       champs.get("meta", {}),
    }


# ---------------------------------------------------------------------------
# GET /factures/ - lister
# ---------------------------------------------------------------------------

@app.get("/factures/")
def lister(statut: str = Query(default=None, description="Filtrer par statut")):
    """Retourne la liste des factures, avec filtre optionnel sur le statut."""
    conn = obtenir_connexion()
    rows = lister_factures(conn, statut)
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# GET /factures/{id} - detail
# ---------------------------------------------------------------------------

@app.get("/factures/{id_facture}")
def detail_facture(id_facture: int):
    """Retourne le detail complet d'une facture."""
    conn = obtenir_connexion()
    facture = obtenir_facture(conn, id_facture)
    conn.close()
    if facture is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    return facture


# ---------------------------------------------------------------------------
# PUT /factures/{id}/valider et /rejeter - actions humaines
# ---------------------------------------------------------------------------

@app.put("/factures/{id_facture}/valider")
def valider_facture(id_facture: int):
    """
    Valide une facture (action humaine obligatoire).
    Impossible si deja validee ou rejetee.
    """
    conn = obtenir_connexion()
    ok = mettre_a_jour_statut(conn, id_facture, "validee")
    conn.close()
    if not ok:
        raise HTTPException(status_code=400, detail="Validation impossible (statut incompatible ou id inconnu)")
    return {"id": id_facture, "statut": "validee"}


@app.put("/factures/{id_facture}/rejeter")
def rejeter_facture(id_facture: int):
    """Rejette une facture (action humaine)."""
    conn = obtenir_connexion()
    ok = mettre_a_jour_statut(conn, id_facture, "rejetee")
    conn.close()
    if not ok:
        raise HTTPException(status_code=400, detail="Rejet impossible (statut incompatible ou id inconnu)")
    return {"id": id_facture, "statut": "rejetee"}
