# fusion.py - combine les resultats regex et LLM en un seul dict de champs
#
# Regles de fusion pour chaque champ :
#   - Les deux trouvent la meme valeur -> confiance elevee (accord)
#   - Un seul trouve une valeur        -> on l'utilise, confiance moderee
#   - Les deux trouvent des valeurs differentes -> a_verifier, on garde la plus confiante
#   - Personne ne trouve              -> valeur None

from typing import Optional

# Tolerance pour l'egalite de deux montants (erreurs d'arrondi)
_TOLERANCE_MONTANT = 0.02


# ---------------------------------------------------------------------------
# Comparaison de valeurs
# ---------------------------------------------------------------------------

def _valeurs_egales(v1, v2) -> bool:
    """
    Teste l'egalite entre deux valeurs extraites.
    Pour les float : tolerance de _TOLERANCE_MONTANT.
    Pour les str : comparaison insensible a la casse.
    """
    if v1 is None or v2 is None:
        return False
    if isinstance(v1, float) and isinstance(v2, float):
        return abs(v1 - v2) <= _TOLERANCE_MONTANT
    if isinstance(v1, str) and isinstance(v2, str):
        return v1.strip().lower() == v2.strip().lower()
    return v1 == v2


# ---------------------------------------------------------------------------
# Fusion d'un champ individuel
# ---------------------------------------------------------------------------

def _fusionner_champ(champ_regex: dict, champ_llm: dict) -> dict:
    """
    Fusionne un champ issu du regex et du LLM.

    Retourne un dict avec :
      valeur     : valeur retenue
      confiance  : float
      source     : "regex" | "llm" | "accord" | "a_verifier"
      divergence : True si les deux ont trouve des valeurs differentes
    """
    val_r = champ_regex.get("valeur")
    val_l = champ_llm.get("valeur")
    conf_r = champ_regex.get("confiance", 0.0)
    conf_l = champ_llm.get("confiance", 0.0)

    # Cas 1 : aucun ne trouve
    if val_r is None and val_l is None:
        return {"valeur": None, "confiance": 0.0, "source": "accord", "divergence": False}

    # Cas 2 : accord (meme valeur)
    if val_r is not None and val_l is not None and _valeurs_egales(val_r, val_l):
        valeur = val_r  # on prefere la valeur regex (mieux normalisee)
        confiance = min(1.0, max(conf_r, conf_l) + 0.05)  # bonus d'accord
        return {"valeur": valeur, "confiance": round(confiance, 3), "source": "accord", "divergence": False}

    # Cas 3 : un seul trouve
    if val_r is not None and val_l is None:
        return {"valeur": val_r, "confiance": conf_r, "source": "regex", "divergence": False}

    if val_l is not None and val_r is None:
        return {"valeur": val_l, "confiance": conf_l, "source": "llm", "divergence": False}

    # Cas 4 : desaccord (les deux trouvent des valeurs differentes)
    # On garde la valeur la plus confiante mais on signale la divergence
    if conf_r >= conf_l:
        valeur, confiance, source = val_r, conf_r, "regex"
    else:
        valeur, confiance, source = val_l, conf_l, "llm"

    # On penalise la confiance en cas de desaccord
    confiance = round(max(0.0, confiance - 0.15), 3)
    return {"valeur": valeur, "confiance": confiance, "source": source, "divergence": True}


# ---------------------------------------------------------------------------
# Fusion complete
# ---------------------------------------------------------------------------

def fusionner(resultats_regex: dict, resultats_llm: dict, confiance_ocr: float) -> dict:
    """
    Fusionne les resultats regex et LLM pour produire le dict final des champs.

    Parametres
    ----------
    resultats_regex  : sortie de extraire_par_regex()
    resultats_llm    : sortie de extraire_par_llm()
    confiance_ocr    : float 0-1, issu de ocr.extraire_texte()

    Retour
    ------
    dict avec les 6 champs fusionnes + meta-informations :
      {
        "fournisseur":    {"valeur": ..., "confiance": ..., "source": ..., "divergence": ...},
        ...
        "meta": {
          "confiance_ocr": float,
          "nb_divergences": int,
          "signaler_verification": bool  # True si OCR faible OU au moins une divergence
        }
      }
    """
    champs = ["fournisseur", "numero_facture", "date", "montant_ht", "tva", "montant_ttc"]
    fusionne = {}
    nb_divergences = 0

    for champ in champs:
        r = resultats_regex.get(champ, {"valeur": None, "confiance": 0.0, "source": "regex"})
        l = resultats_llm.get(champ,   {"valeur": None, "confiance": 0.0, "source": "llm"})
        resultat = _fusionner_champ(r, l)
        if resultat["divergence"]:
            nb_divergences += 1
        fusionne[champ] = resultat

    # Reduire toutes les confiances si l'OCR est de mauvaise qualite
    if confiance_ocr < 0.70:
        for champ in champs:
            fusionne[champ]["confiance"] = round(
                fusionne[champ]["confiance"] * confiance_ocr, 3
            )

    signaler = confiance_ocr < 0.70 or nb_divergences > 0

    fusionne["meta"] = {
        "confiance_ocr":         round(confiance_ocr, 3),
        "nb_divergences":        nb_divergences,
        "signaler_verification": signaler,
    }

    return fusionne
