# controles.py - regles metier non negociables (voir CLAUDE.md section 9)
#
# Controles appliques apres fusion regex/LLM :
#   - arithmetique : HT + TVA = TTC (tolerance 0.01 euro)
#   - date valide  : date ISO calendairement correcte
#   - doublon      : empreinte SHA-256 du fichier ET couple fournisseur+numero

import hashlib
import sqlite3
from datetime import date as Date
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Controle arithmetique
# ---------------------------------------------------------------------------

def verifier_arithmetique(ht: Optional[float], tva: Optional[float], ttc: Optional[float]) -> bool:
    """
    Retourne True si HT + TVA = TTC a 0.01 euro pres.
    Retourne False si l'un des montants est None ou si l'ecart depasse la tolerance.
    """
    if ht is None or tva is None or ttc is None:
        return False
    return abs((ht + tva) - ttc) <= 0.01


# ---------------------------------------------------------------------------
# Controle de date
# ---------------------------------------------------------------------------

def verifier_date(date_iso: Optional[str]) -> bool:
    """Retourne True si la date ISO est calendairement valide."""
    if not date_iso:
        return False
    try:
        annee, mois, jour = map(int, date_iso.split("-"))
        Date(annee, mois, jour)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Empreinte SHA-256
# ---------------------------------------------------------------------------

def calculer_empreinte(chemin: str | Path) -> Optional[str]:
    """
    Calcule le SHA-256 du fichier en lecture binaire.
    Retourne None si le fichier est illisible.
    """
    try:
        sha = hashlib.sha256()
        with open(chemin, "rb") as f:
            for bloc in iter(lambda: f.read(65536), b""):
                sha.update(bloc)
        return sha.hexdigest()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Detection de doublon
# ---------------------------------------------------------------------------

def est_doublon(
    conn: sqlite3.Connection,
    empreinte: Optional[str],
    fournisseur: Optional[str],
    numero_facture: Optional[str],
) -> bool:
    """
    Detecte un doublon selon deux criteres independants (CLAUDE.md section 9) :
      1. Meme empreinte SHA-256 (fichier identique ou rescan)
      2. Meme couple (fournisseur, numero_facture) toutes statuts confondus

    Retourne True si l'un des deux criteres est verifie.
    """
    cur = conn.cursor()

    # Critere 1 : empreinte
    if empreinte:
        cur.execute(
            "SELECT 1 FROM factures WHERE empreinte = ? LIMIT 1",
            (empreinte,),
        )
        if cur.fetchone():
            return True

    # Critere 2 : couple fournisseur + numero
    if fournisseur and numero_facture:
        cur.execute(
            "SELECT 1 FROM factures WHERE fournisseur = ? AND numero_facture = ? LIMIT 1",
            (fournisseur, numero_facture),
        )
        if cur.fetchone():
            return True

    return False


# ---------------------------------------------------------------------------
# Application de tous les controles et calcul du statut
# ---------------------------------------------------------------------------

def appliquer_controles(
    champs: dict,
    chemin_fichier: str | Path,
    conn: sqlite3.Connection,
) -> dict:
    """
    Applique les controles metier et determine le statut de la facture.

    Parametres
    ----------
    champs          : dict fusionne issu de fusion.fusionner()
    chemin_fichier  : chemin du fichier source (pour le SHA-256)
    conn            : connexion SQLite ouverte

    Retour
    ------
    {
      "controles": {
        "arithmetique": bool,
        "date_valide":  bool,
        "doublon":      bool,
      },
      "empreinte": str | None,
      "statut":    str  (voir CLAUDE.md section 8)
    }
    """
    # Extraire les valeurs brutes
    ht  = champs.get("montant_ht",  {}).get("valeur")
    tva = champs.get("tva",         {}).get("valeur")
    ttc = champs.get("montant_ttc", {}).get("valeur")
    date        = champs.get("date",           {}).get("valeur")
    fournisseur = champs.get("fournisseur",    {}).get("valeur")
    numero      = champs.get("numero_facture", {}).get("valeur")

    arith       = verifier_arithmetique(ht, tva, ttc)
    date_valide = verifier_date(date)
    empreinte   = calculer_empreinte(chemin_fichier)
    doublon     = est_doublon(conn, empreinte, fournisseur, numero)

    controles = {
        "arithmetique": arith,
        "date_valide":  date_valide,
        "doublon":      doublon,
    }

    # Determination du statut
    if doublon:
        statut = "doublon"
    elif (
        not arith
        or not date_valide
        or champs.get("meta", {}).get("signaler_verification", False)
    ):
        statut = "a_verifier"
    else:
        statut = "prete"

    return {
        "controles": controles,
        "empreinte": empreinte,
        "statut":    statut,
    }
