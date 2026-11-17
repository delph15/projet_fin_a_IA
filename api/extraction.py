# extraction.py - extraction des 6 champs par expressions regulieres
#
# Entree  : texte brut issu de ocr.extraire_texte()
# Sortie  : dict avec, pour chaque champ, {"valeur": ..., "confiance": float, "source": "regex"}
#           valeur = None si le champ n'a pas ete trouve (jamais invente)
#
# Champs  : fournisseur, numero_facture, date, montant_ht, tva, montant_ttc

import re
from datetime import date as _date_cls
from typing import Optional


# ---------------------------------------------------------------------------
# Normalisation des nombres
# ---------------------------------------------------------------------------

# Sequence "chiffres + separateurs" suivie de deux decimales
_RE_NOMBRE = re.compile(r"([\d\s\xa0]+[.,]\d{2}|\d+)")


def normaliser_nombre(texte: str) -> Optional[float]:
    """
    Convertit une chaine representant un montant en float.
    Gere :
      - separateur decimal virgule  : "1 193,73" -> 1193.73
      - separateur decimal point    : "1193.73"  -> 1193.73
      - absence de decimale (OCR)   : "119373"   -> 1193.73  (heuristique centimes)
      - espaces / nbsp comme milliers : "3 233,19"
    Retourne None si la conversion echoue.
    """
    if not texte:
        return None

    # Supprimer les espaces inSecables et espaces comme separateurs de milliers
    propre = texte.replace("\xa0", "").replace(" ", "")

    # Virgule -> point decimal
    if "," in propre and "." not in propre:
        propre = propre.replace(",", ".")
    elif "," in propre and "." in propre:
        # Format "1.193,73" : le point est le separateur de milliers
        propre = propre.replace(".", "").replace(",", ".")

    try:
        valeur = float(propre)
    except ValueError:
        return None

    # Heuristique centimes : uniquement si la chaine SOURCE n'avait aucun separateur
    # decimal (virgule ou point). Ex. : OCR lit "119373" au lieu de "1193.73".
    # On n'applique PAS l'heuristique sur "1000.00" (a un point) ou "1 000,00".
    source_sans_separateur = "," not in texte and "." not in texte
    if source_sans_separateur and valeur == int(valeur) and valeur > 999:
        valeur_cents = valeur / 100
        if round(valeur_cents, 2) == valeur_cents:
            valeur = valeur_cents

    return round(valeur, 2)


# ---------------------------------------------------------------------------
# Numero de facture
# ---------------------------------------------------------------------------

# Pattern 1 : format interne FAC-AAAA-NNNN (avec espaces OCR tolerés autour des tirets)
_RE_NUMERO_FAC = re.compile(r"FAC\s*[-–]\s*\d{4}\s*[-–]\s*\d{3,6}", re.IGNORECASE)

# Pattern 2 : reference apres un label explicite (Réf., Référence, N°, Numéro, Facture n°…)
_RE_NUMERO_LABEL = re.compile(
    r"(?:r[eé]f(?:\.|\s+facture)?|r[eé]f[eé]rence|n[o°°]\s*(?:de\s+facture)?|num[eé]ro\s+(?:de\s+)?facture|facture\s+n[o°°])"
    r"\s*[:.\-]?\s*([A-Z0-9][-A-Z0-9/\s]{2,20})",
    re.IGNORECASE,
)


def _nettoyer_numero(valeur: str) -> str:
    """Supprime les espaces autour des tirets (artefacts OCR) et met en majuscules."""
    return re.sub(r"\s*[-–]\s*", "-", valeur).strip().upper()


def _extraire_numero(texte: str) -> dict:
    """Cherche le numéro de facture : d'abord le pattern interne FAC-AAAA-NNNN,
    puis tout identifiant après un label de référence."""
    m = _RE_NUMERO_FAC.search(texte)
    if m:
        return {"valeur": _nettoyer_numero(m.group(0)), "confiance": 0.98, "source": "regex"}

    m = _RE_NUMERO_LABEL.search(texte)
    if m:
        valeur = _nettoyer_numero(m.group(1).split()[0] if m.group(1) else "")
        if valeur:
            return {"valeur": valeur, "confiance": 0.85, "source": "regex"}

    return {"valeur": None, "confiance": 0.0, "source": "regex"}


# ---------------------------------------------------------------------------
# Date
# ---------------------------------------------------------------------------

# Format ISO : AAAA-MM-JJ (avec espaces OCR tolérés autour des tirets)
_RE_DATE_ISO = re.compile(r"\b(\d{4})\s*[-–]\s*(\d{2})\s*[-–]\s*(\d{2})\b")

# Format européen : JJ/MM/AAAA ou JJ-MM-AAAA
_RE_DATE_EU = re.compile(r"\b(\d{2})[/\-](\d{2})[/\-](\d{4})\b")

# Format après label : "Émise le", "Date", "Date d'émission", "Date de facturation"
_RE_DATE_LABEL = re.compile(
    r"(?:[eé]mise?\s+le|date\s+(?:d['’])?[eé]mission|date\s+de\s+facturation|date\s+[:.\-]?)",
    re.IGNORECASE,
)

def _valider_date(annee: int, mois: int, jour: int) -> bool:
    try:
        _date_cls(annee, mois, jour)
        return True
    except (ValueError, TypeError):
        return False


def _extraire_date(texte: str) -> dict:
    """Cherche une date dans le texte, en privilégiant les lignes après un label de date.
    Formats reconnus : AAAA-MM-JJ (ISO) et JJ/MM/AAAA (européen).
    """
    lignes = texte.splitlines()

    # Passe 1 : lignes contenant un label de date explicite
    for ligne in lignes:
        if _RE_DATE_LABEL.search(ligne):
            for m in _RE_DATE_ISO.finditer(ligne):
                a, mo, j = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if _valider_date(a, mo, j):
                    return {"valeur": f"{a:04d}-{mo:02d}-{j:02d}", "confiance": 0.98, "source": "regex"}
            for m in _RE_DATE_EU.finditer(ligne):
                j, mo, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if _valider_date(a, mo, j):
                    return {"valeur": f"{a:04d}-{mo:02d}-{j:02d}", "confiance": 0.95, "source": "regex"}

    # Passe 2 : première date ISO valide dans tout le texte
    for m in _RE_DATE_ISO.finditer(texte):
        a, mo, j = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valider_date(a, mo, j):
            return {"valeur": f"{a:04d}-{mo:02d}-{j:02d}", "confiance": 0.95, "source": "regex"}

    # Passe 3 : première date européenne valide dans tout le texte
    for m in _RE_DATE_EU.finditer(texte):
        j, mo, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valider_date(a, mo, j):
            return {"valeur": f"{a:04d}-{mo:02d}-{j:02d}", "confiance": 0.90, "source": "regex"}

    return {"valeur": None, "confiance": 0.0, "source": "regex"}


# ---------------------------------------------------------------------------
# Montants (HT, TVA, TTC) - approche par ligne
# ---------------------------------------------------------------------------

_RE_ETIQ_HT = re.compile(
    r"\b(?:montant\s+h[ot]|montant\s+hors\s+taxe|base\s+ht|^ht)\b",
    re.IGNORECASE,
)
_RE_ETIQ_TVA = re.compile(r"\btva\b", re.IGNORECASE)
_RE_ETIQ_TTC = re.compile(
    r"\b(?:total\s+ttc|net\s+[a\xe0]\s+payer|^ttc)\b",
    re.IGNORECASE,
)

# Supprime les pourcentages (ex. "20 %", "20%") pour ne pas les confondre avec un montant
_RE_POURCENTAGE = re.compile(r"\d+\s*%")


def _dernier_nombre_de_ligne(ligne: str, strip_pct: bool = False) -> Optional[float]:
    """Retourne le dernier nombre trouvé dans une ligne, normalisé.

    Si strip_pct=True, supprime d'abord les pourcentages (utile pour la ligne TVA
    qui contient "20 %" avant le montant réel).

    Heuristique OCR : si les deux derniers tokens sont un entier suivi de exactement
    2 chiffres sans séparateur (ex. "180" "13"), tente de les fusionner en "180.13"
    — artefact fréquent quand l'OCR lit le point décimal comme une espace.
    """
    if strip_pct:
        ligne = _RE_POURCENTAGE.sub("", ligne)

    nombres = _RE_NOMBRE.findall(ligne)
    if not nombres:
        return None

    # Heuristique : "180" + "13" → 180.13 (OCR a lu "." comme espace)
    if len(nombres) >= 2:
        dern  = nombres[-1].strip()
        avant = nombres[-2].strip()
        if (re.fullmatch(r"\d{2}", dern)
                and re.fullmatch(r"\d{2,6}", avant)):
            tente = normaliser_nombre(f"{avant}.{dern}")
            if tente is not None:
                return tente

    return normaliser_nombre(nombres[-1].strip())


def _montant_par_etiquette(
    etiquette: re.Pattern,
    texte: str,
    strip_pct: bool = False,
) -> Optional[float]:
    """Cherche la première ligne contenant l'étiquette et retourne son dernier nombre.

    Si aucun montant n'est trouvé sur la ligne de l'étiquette (cas des tableaux OCR
    où le montant est renvoyé à la ligne suivante), tente la ligne suivante.
    """
    lignes = texte.splitlines()
    for i, ligne in enumerate(lignes):
        if etiquette.search(ligne):
            valeur = _dernier_nombre_de_ligne(ligne, strip_pct=strip_pct)
            if valeur is not None and valeur > 0:
                return valeur
            # Montant peut être sur la ligne suivante (tableau OCR)
            if i + 1 < len(lignes):
                valeur = _dernier_nombre_de_ligne(lignes[i + 1], strip_pct=False)
                if valeur is not None and valeur > 0:
                    return valeur
    return None


def _extraire_montants(texte: str) -> tuple:
    """Retourne (montant_ht, tva, montant_ttc) chacun sous forme de dict champ."""
    ht  = _montant_par_etiquette(_RE_ETIQ_HT,  texte)
    tva = _montant_par_etiquette(_RE_ETIQ_TVA, texte, strip_pct=True)
    ttc = _montant_par_etiquette(_RE_ETIQ_TTC, texte)

    conf_ht  = 0.90 if ht  is not None else 0.0
    conf_tva = 0.90 if tva is not None else 0.0
    conf_ttc = 0.90 if ttc is not None else 0.0

    # Bonus de confiance si le controle arithmetique passe (HT + TVA = TTC a 0.01 pres)
    if ht is not None and tva is not None and ttc is not None:
        if abs((ht + tva) - ttc) <= 0.01:
            conf_ht  = 0.97
            conf_tva = 0.97
            conf_ttc = 0.97

    return (
        {"valeur": ht,  "confiance": conf_ht,  "source": "regex"},
        {"valeur": tva, "confiance": conf_tva, "source": "regex"},
        {"valeur": ttc, "confiance": conf_ttc, "source": "regex"},
    )


# ---------------------------------------------------------------------------
# Fournisseur
# ---------------------------------------------------------------------------

_MOTS_EXCLUS = re.compile(
    r"^(?:facture|num[e\xe9]ro|r[e\xe9]f\.?|[e\xe9]mise?\s+le|date|hors\s+taxe|"
    r"montant|total|tva|merci|r[e\xe9]capitulatif|d[e\xe9]signation|"
    r"ht\b|ttc\b|net\s+[a\xe0]|base|taxe|bon\s+de)",
    re.IGNORECASE,
)

_RE_LIGNE_NOM = re.compile(r"[a-zA-Z\xc0-\xff]{2,}")


def _extraire_fournisseur(texte: str) -> dict:
    """
    Heuristique pour extraire le nom du fournisseur :
    1. Cherche la ligne qui suit immediatement le titre "FACTURE" (modele A).
    2. Sinon, cherche la premiere ligne qui ressemble a un nom d'entreprise
       (contient des lettres, ne commence pas par un mot-cle de facture).
    """
    lignes = [l.strip() for l in texte.splitlines() if l.strip()]

    # Strategie 1 : ligne apres "FACTURE"
    for i, ligne in enumerate(lignes):
        if ligne.upper() == "FACTURE" and i + 1 < len(lignes):
            candidat = lignes[i + 1]
            if _RE_LIGNE_NOM.search(candidat) and not _MOTS_EXCLUS.match(candidat):
                return {"valeur": candidat, "confiance": 0.85, "source": "regex"}

    # Strategie 2 : premiere ligne sans mot-cle de facture
    for ligne in lignes:
        if len(ligne) < 4:
            continue
        if _MOTS_EXCLUS.match(ligne):
            continue
        if re.match(r"^(FAC-|N[^\w]|N\s+FAC|\d{4}-\d{2})", ligne, re.IGNORECASE):
            continue
        if not _RE_LIGNE_NOM.search(ligne):
            continue
        if re.match(r"^\d+[,\s]", ligne):
            continue
        return {"valeur": ligne, "confiance": 0.75, "source": "regex"}

    return {"valeur": None, "confiance": 0.0, "source": "regex"}


# ---------------------------------------------------------------------------
# Point d'entree principal
# ---------------------------------------------------------------------------

def extraire_par_regex(texte: str) -> dict:
    """
    Extrait les 6 champs d'une facture par expressions regulieres.

    Parametre
    ---------
    texte : texte brut issu de l'OCR ou de pdfplumber

    Retour
    ------
    dict avec les cles : fournisseur, numero_facture, date,
                         montant_ht, tva, montant_ttc
    Chaque valeur est {"valeur": ..., "confiance": float, "source": "regex"}.
    valeur = None si le champ n'a pas ete trouve.
    """
    if not texte:
        champ_vide = {"valeur": None, "confiance": 0.0, "source": "regex"}
        return {
            "fournisseur":    dict(champ_vide),
            "numero_facture": dict(champ_vide),
            "date":           dict(champ_vide),
            "montant_ht":     dict(champ_vide),
            "tva":            dict(champ_vide),
            "montant_ttc":    dict(champ_vide),
        }

    ht, tva, ttc = _extraire_montants(texte)

    return {
        "fournisseur":    _extraire_fournisseur(texte),
        "numero_facture": _extraire_numero(texte),
        "date":           _extraire_date(texte),
        "montant_ht":     ht,
        "tva":            tva,
        "montant_ttc":    ttc,
    }
