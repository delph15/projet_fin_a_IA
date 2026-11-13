# extraction_llm.py - extraction des 6 champs via Ollama (qwen2.5:7b)
#
# Contrat : ne leve jamais d'exception vers l'appelant.
# Si Ollama est indisponible ou repond mal -> valeurs None, source "llm".
# L'appelant positionnera le statut "a_verifier".

import json
import os
import re
from typing import Optional

import requests

from extraction import normaliser_nombre

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434")
_MODELE       = os.getenv("OLLAMA_MODELE", "qwen2.5:7b")
_TIMEOUT      = 120  # secondes

# Options CPU uniquement (GPU fait planter Ollama sur cette machine)
_OPTIONS_CPU = {"num_gpu": 0, "temperature": 0}

_PROMPT_SYSTEME = """\
Tu analyses le texte brut d'une facture française et tu extrais exactement 6 champs.
Reponds UNIQUEMENT avec un objet JSON valide, sans texte autour, avec cette structure :
{
  "fournisseur": "...",
  "numero_facture": "...",
  "date": "AAAA-MM-JJ",
  "montant_ht": 0.00,
  "tva": 0.00,
  "montant_ttc": 0.00
}
Regles :
- date obligatoirement au format ISO AAAA-MM-JJ
- montant_ht, tva, montant_ttc : nombres decimaux (point decimal, pas de symbole monetaire)
- Si un champ est absent du texte : null
- Ne jamais inventer une valeur qui n'apparait pas dans le texte\
"""


# ---------------------------------------------------------------------------
# Appel Ollama
# ---------------------------------------------------------------------------

def _appeler_ollama(texte: str) -> Optional[dict]:
    """
    Envoie le texte a Ollama et retourne le dict JSON parse.
    Retourne None si l'appel echoue ou si la reponse n'est pas du JSON valide.
    """
    prompt = f"{_PROMPT_SYSTEME}\n\nTexte de la facture :\n{texte}"
    payload = {
        "model":      _MODELE,
        "prompt":     prompt,
        "format":     "json",
        "stream":     False,
        "keep_alive": "10m",
        "options":    _OPTIONS_CPU,
    }
    try:
        reponse = requests.post(
            f"{_OLLAMA_URL}/api/generate",
            json=payload,
            timeout=_TIMEOUT,
        )
        reponse.raise_for_status()
        texte_llm = reponse.json().get("response", "")
        return json.loads(texte_llm)
    except (requests.RequestException, json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Normalisation de la reponse LLM
# ---------------------------------------------------------------------------

_RE_DATE_ISO  = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_DATE_FR   = re.compile(r"^(\d{2})[/\-](\d{2})[/\-](\d{4})$")
_RE_NUMERO_FAC = re.compile(r"FAC-\d{4}-\d{4}", re.IGNORECASE)


def _normaliser_date(valeur) -> Optional[str]:
    """Convertit une date LLM en ISO AAAA-MM-JJ. Retourne None si invalide."""
    if not valeur or not isinstance(valeur, str):
        return None
    valeur = valeur.strip()
    if _RE_DATE_ISO.match(valeur):
        return valeur
    # Format JJ/MM/AAAA ou JJ-MM-AAAA
    m = _RE_DATE_FR.match(valeur)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


def _normaliser_numero(valeur) -> Optional[str]:
    """Extrait et normalise un numero de facture FAC-AAAA-NNNN."""
    if not valeur or not isinstance(valeur, str):
        return None
    m = _RE_NUMERO_FAC.search(valeur)
    return m.group(0).upper() if m else None


def _normaliser_montant(valeur) -> Optional[float]:
    """Convertit un montant LLM (float, int ou str) en float normalise."""
    if valeur is None:
        return None
    if isinstance(valeur, (int, float)):
        return round(float(valeur), 2)
    if isinstance(valeur, str):
        return normaliser_nombre(valeur)
    return None


def _normaliser_fournisseur(valeur) -> Optional[str]:
    """Nettoie le nom du fournisseur."""
    if not valeur or not isinstance(valeur, str):
        return None
    # Supprimer les prefixes parasites type "Fournisseur : "
    propre = re.sub(r"^[^:]+:\s*", "", valeur).strip()
    return propre if propre else None


# ---------------------------------------------------------------------------
# Verification anti-hallucination
# ---------------------------------------------------------------------------

def _valeur_dans_texte(valeur, texte_ocr: str) -> bool:
    """
    Verifie qu'une valeur extraite par le LLM apparait dans le texte OCR.
    Evite les inventions : une valeur absente du texte source est suspecte.
    """
    if valeur is None:
        return False
    texte_min = texte_ocr.lower()

    if isinstance(valeur, float):
        # Chercher le nombre avec point ou virgule comme decimale
        repr_point  = f"{valeur:.2f}"
        repr_virgule = repr_point.replace(".", ",")
        # Aussi sans decimales pour les OCR qui les omettent
        repr_entier = str(int(valeur * 100))
        return (
            repr_point  in texte_min
            or repr_virgule in texte_min
            or repr_entier  in texte_min
        )

    if isinstance(valeur, str):
        return valeur.lower() in texte_min

    return False


# ---------------------------------------------------------------------------
# Construction du dict de champ
# ---------------------------------------------------------------------------

def _champ(valeur, texte_ocr: str, confiance_base: float) -> dict:
    """
    Construit un dict {"valeur", "confiance", "source"} pour un champ LLM.
    La confiance est reduite si la valeur n'apparait pas dans le texte OCR.
    """
    if valeur is None:
        return {"valeur": None, "confiance": 0.0, "source": "llm"}

    present = _valeur_dans_texte(valeur, texte_ocr)
    confiance = confiance_base if present else max(confiance_base - 0.25, 0.0)

    return {"valeur": valeur, "confiance": round(confiance, 3), "source": "llm"}


# ---------------------------------------------------------------------------
# Point d'entree principal
# ---------------------------------------------------------------------------

def extraire_par_llm(texte: str) -> dict:
    """
    Extrait les 6 champs d'une facture via Ollama.

    Parametre
    ---------
    texte : texte brut issu de l'OCR ou de pdfplumber

    Retour
    ------
    dict avec les cles : fournisseur, numero_facture, date,
                         montant_ht, tva, montant_ttc
    Chaque valeur est {"valeur": ..., "confiance": float, "source": "llm"}.
    valeur = None si non trouve ou si Ollama est indisponible.
    """
    champ_vide = {"valeur": None, "confiance": 0.0, "source": "llm"}

    if not texte:
        return {k: dict(champ_vide) for k in
                ("fournisseur", "numero_facture", "date", "montant_ht", "tva", "montant_ttc")}

    brut = _appeler_ollama(texte)
    if brut is None:
        return {k: dict(champ_vide) for k in
                ("fournisseur", "numero_facture", "date", "montant_ht", "tva", "montant_ttc")}

    # Normalisation
    fournisseur    = _normaliser_fournisseur(brut.get("fournisseur"))
    numero_facture = _normaliser_numero(brut.get("numero_facture"))
    date           = _normaliser_date(brut.get("date"))
    montant_ht     = _normaliser_montant(brut.get("montant_ht"))
    tva            = _normaliser_montant(brut.get("tva"))
    montant_ttc    = _normaliser_montant(brut.get("montant_ttc"))

    # Confiance de base LLM : legrement inferieure au regex sur un texte propre,
    # mais meilleure pour les champs ambigus comme le fournisseur
    conf_fournisseur = 0.88
    conf_numero      = 0.90
    conf_date        = 0.90
    conf_montant     = 0.88

    # Bonus arithmetique
    if montant_ht is not None and tva is not None and montant_ttc is not None:
        if abs((montant_ht + tva) - montant_ttc) <= 0.01:
            conf_montant = 0.95

    return {
        "fournisseur":    _champ(fournisseur,    texte, conf_fournisseur),
        "numero_facture": _champ(numero_facture, texte, conf_numero),
        "date":           _champ(date,           texte, conf_date),
        "montant_ht":     _champ(montant_ht,     texte, conf_montant),
        "tva":            _champ(tva,            texte, conf_montant),
        "montant_ttc":    _champ(montant_ttc,    texte, conf_montant),
    }
