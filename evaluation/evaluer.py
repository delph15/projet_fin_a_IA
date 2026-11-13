# evaluer.py - mesure les performances du systeme sur le jeu de test
#
# Usage (depuis la racine du projet) :
#   python evaluation/evaluer.py                    # config "complet" uniquement
#   python evaluation/evaluer.py --config tout       # 3 configs (long : ~20 min)
#   python evaluation/evaluer.py --config regex      # regex seules (rapide)
#   python evaluation/evaluer.py --modele qwen2.5:3b # comparaison de modele
#
# Sorties :
#   evaluation/resultats/details_<config>.json   - resultats par fichier
#   evaluation/resultats/resume.csv              - tableau de synthese
#
# IMPORTANT : ne jamais utiliser ce script pour regler les regex ou le prompt.
# Le jeu de test est reserve a l'evaluation finale.

import argparse
import csv
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

from controles import appliquer_controles, calculer_empreinte
from extraction import extraire_par_regex
from extraction_llm import extraire_par_llm
from fusion import fusionner
from ocr import extraire_texte

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DOSSIER_TEST = Path("donnees/test")
DOSSIER_VT   = Path("donnees/verite_terrain")
DOSSIER_RES  = Path("evaluation/resultats")

CHAMPS_NUMERIQUES = {"montant_ht", "tva", "montant_ttc"}
CHAMPS = ["fournisseur", "numero_facture", "date", "montant_ht", "tva", "montant_ttc"]
TOLERANCE_MONTANT = 0.02


# ---------------------------------------------------------------------------
# Chargement de la verite terrain
# ---------------------------------------------------------------------------

def charger_verite_terrain() -> dict:
    """Charge tous les JSON de verite terrain dans un dict {fichier: vt}."""
    vt_dict = {}
    for chemin in DOSSIER_VT.glob("*.json"):
        vt = json.loads(chemin.read_text(encoding="utf-8"))
        vt_dict[vt["fichier"]] = vt
    return vt_dict


# ---------------------------------------------------------------------------
# Comparaison d'un champ extrait a la verite terrain
# ---------------------------------------------------------------------------

def champ_correct(valeur_extraite, valeur_vt, champ: str) -> bool:
    """
    Retourne True si la valeur extraite correspond a la verite terrain.
    Tolerance de TOLERANCE_MONTANT pour les montants.
    """
    if valeur_extraite is None or valeur_vt is None:
        return valeur_extraite == valeur_vt
    if champ in CHAMPS_NUMERIQUES:
        try:
            return abs(float(valeur_extraite) - float(valeur_vt)) <= TOLERANCE_MONTANT
        except (TypeError, ValueError):
            return False
    return str(valeur_extraite).strip() == str(valeur_vt).strip()


# ---------------------------------------------------------------------------
# Evaluation d'un fichier selon une configuration
# ---------------------------------------------------------------------------

def evaluer_fichier_regex(chemin: Path) -> tuple[dict, float]:
    """Config 'regex seules' : OCR + extraction regex, sans LLM ni fusion."""
    debut = time.perf_counter()
    texte, conf_ocr = extraire_texte(chemin)
    champs = extraire_par_regex(texte)
    duree = time.perf_counter() - debut
    return {c: champs[c]["valeur"] for c in CHAMPS}, duree


def evaluer_fichier_llm(chemin: Path) -> tuple[dict, float]:
    """Config 'LLM seul' : OCR + extraction LLM, sans regex ni fusion."""
    debut = time.perf_counter()
    texte, conf_ocr = extraire_texte(chemin)
    champs = extraire_par_llm(texte)
    duree = time.perf_counter() - debut
    return {c: champs[c]["valeur"] for c in CHAMPS}, duree


def evaluer_fichier_complet(chemin: Path, conn: sqlite3.Connection) -> tuple[dict, str, float]:
    """
    Config 'systeme complet' : OCR + regex + LLM + fusion + controles + insertion DB.
    L'insertion est necessaire pour que la detection de doublons fonctionne
    sur les fichiers suivants (l'original doit etre en base avant son doublon).
    Retourne (valeurs extraites, statut, duree).
    """
    import base as base_mod

    debut = time.perf_counter()
    texte, conf_ocr = extraire_texte(chemin)
    res_regex = extraire_par_regex(texte)
    res_llm   = extraire_par_llm(texte)
    fusionne  = fusionner(res_regex, res_llm, conf_ocr)
    ctrl      = appliquer_controles(fusionne, chemin, conn)

    # Insertion en base pour que les doublons suivants soient detectables
    facture = {
        "fichier":   chemin.name,
        "empreinte": ctrl["empreinte"],
        "statut":    ctrl["statut"],
        "champs":    fusionne,
        "controles": ctrl["controles"],
    }
    base_mod.inserer_facture(conn, facture)

    duree   = time.perf_counter() - debut
    valeurs = {c: fusionne[c]["valeur"] for c in CHAMPS}
    return valeurs, ctrl["statut"], duree


# ---------------------------------------------------------------------------
# Calcul des metriques agregees
# ---------------------------------------------------------------------------

def calculer_metriques(resultats: list[dict]) -> dict:
    """
    Calcule les metriques a partir de la liste des resultats par fichier.
    Ne prend en compte que les originaux (non-doublons) pour la precision des champs.
    """
    originaux  = [r for r in resultats if not r["est_doublon"]]
    doublons   = [r for r in resultats if r["est_doublon"]]

    nb_orig = len(originaux)
    if nb_orig == 0:
        return {}

    # Precision par champ
    prec_champs = {}
    for c in CHAMPS:
        corrects = sum(1 for r in originaux if r["champs_ok"].get(c, False))
        prec_champs[c] = round(corrects / nb_orig, 3)

    # Factures entierement correctes
    tout_ok = sum(1 for r in originaux if all(r["champs_ok"].values()))
    prec_totale = round(tout_ok / nb_orig, 3)

    # Temps moyen (originaux seulement)
    temps_moy = round(sum(r["duree"] for r in originaux) / nb_orig, 2)

    # PDF vs images
    pdfs   = [r for r in originaux if r["type_fichier"] == "pdf"]
    images = [r for r in originaux if r["type_fichier"] == "image"]
    acc_pdf   = round(sum(all(r["champs_ok"].values()) for r in pdfs)   / max(len(pdfs), 1), 3)
    acc_image = round(sum(all(r["champs_ok"].values()) for r in images) / max(len(images), 1), 3)

    # Modele A/B/C vs D
    abc = [r for r in originaux if r.get("modele") in ("A", "B", "C")]
    d   = [r for r in originaux if r.get("modele") == "D"]
    acc_abc = round(sum(all(r["champs_ok"].values()) for r in abc) / max(len(abc), 1), 3)
    acc_d   = round(sum(all(r["champs_ok"].values()) for r in d)   / max(len(d), 1), 3)

    # Detection des doublons (config complet uniquement)
    nb_vrais_doublons = len(doublons)
    nb_detectes = sum(1 for r in doublons if r.get("statut") == "doublon")
    rappel_doublon = round(nb_detectes / max(nb_vrais_doublons, 1), 3)

    # Faux positifs doublons (originaux incorrectement marques doublon)
    faux_positifs = sum(1 for r in originaux if r.get("statut") == "doublon")
    prec_doublon = round(
        nb_detectes / max(nb_detectes + faux_positifs, 1), 3
    )

    # Taux de signalement des erreurs (a_verifier pour les factures incorrectes)
    # Uniquement disponible pour la config complet
    incorrectes = [r for r in originaux if not all(r["champs_ok"].values())]
    nb_signalees = sum(
        1 for r in incorrectes
        if r.get("statut") in ("a_verifier",)
    )
    taux_signalement = round(
        nb_signalees / max(len(incorrectes), 1), 3
    )

    return {
        "nb_originaux":        nb_orig,
        "precision_champs":    prec_champs,
        "precision_totale":    prec_totale,
        "factures_tout_ok":    tout_ok,
        "temps_moyen_s":       temps_moy,
        "acc_pdf":             acc_pdf,
        "acc_image":           acc_image,
        "nb_pdfs":             len(pdfs),
        "nb_images":           len(images),
        "acc_modeles_abc":     acc_abc,
        "acc_modele_d":        acc_d,
        "nb_modeles_abc":      len(abc),
        "nb_modele_d":         len(d),
        "nb_vrais_doublons":   nb_vrais_doublons,
        "doublons_detectes":   nb_detectes,
        "rappel_doublon":      rappel_doublon,
        "precision_doublon":   prec_doublon,
        "taux_signalement_erreurs": taux_signalement,
    }


# ---------------------------------------------------------------------------
# Affichage tableau console
# ---------------------------------------------------------------------------

def afficher_tableau(resultats_configs: dict) -> None:
    print("\n" + "=" * 70)
    print("RESULTATS SUR LE JEU DE TEST")
    print("=" * 70)

    entetes = ["Configuration", "Tout_ok", "HT", "TVA", "TTC", "Num", "Date", "Fourn", "Tps(s)"]
    largeur = [20, 8, 6, 6, 6, 6, 6, 6, 7]
    ligne_en = "  ".join(f"{h:<{w}}" for h, w in zip(entetes, largeur))
    print(ligne_en)
    print("-" * 70)

    for config, m in resultats_configs.items():
        if not m:
            continue
        pc = m.get("precision_champs", {})
        valeurs = [
            config,
            f"{m['precision_totale']:.0%}",
            f"{pc.get('montant_ht', 0):.0%}",
            f"{pc.get('tva', 0):.0%}",
            f"{pc.get('montant_ttc', 0):.0%}",
            f"{pc.get('numero_facture', 0):.0%}",
            f"{pc.get('date', 0):.0%}",
            f"{pc.get('fournisseur', 0):.0%}",
            f"{m.get('temps_moyen_s', 0):.1f}",
        ]
        print("  ".join(f"{v:<{w}}" for v, w in zip(valeurs, largeur)))

    print("=" * 70)
    print("\nAnalyse PDF vs Images :")
    for config, m in resultats_configs.items():
        if not m:
            continue
        print(f"  {config:<20s}  PDF={m.get('acc_pdf', 0):.0%} ({m.get('nb_pdfs', 0)})"
              f"   Images={m.get('acc_image', 0):.0%} ({m.get('nb_images', 0)})")

    print("\nAnalyse modeles A/B/C vs D :")
    for config, m in resultats_configs.items():
        if not m:
            continue
        print(f"  {config:<20s}  A/B/C={m.get('acc_modeles_abc', 0):.0%} ({m.get('nb_modeles_abc', 0)})"
              f"   D={m.get('acc_modele_d', 0):.0%} ({m.get('nb_modele_d', 0)})")

    if any(m.get("nb_vrais_doublons", 0) > 0 for m in resultats_configs.values()):
        print("\nDetection des doublons :")
        for config, m in resultats_configs.items():
            if not m or m.get("nb_vrais_doublons", 0) == 0:
                continue
            print(f"  {config:<20s}  Rappel={m['rappel_doublon']:.0%}"
                  f"  Precision={m['precision_doublon']:.0%}"
                  f"  ({m['doublons_detectes']}/{m['nb_vrais_doublons']} detectes)")


# ---------------------------------------------------------------------------
# Sauvegarde CSV
# ---------------------------------------------------------------------------

def sauvegarder_csv(resultats_configs: dict, chemin: Path) -> None:
    entetes = [
        "configuration", "precision_totale",
        "prec_montant_ht", "prec_tva", "prec_montant_ttc",
        "prec_numero_facture", "prec_date", "prec_fournisseur",
        "temps_moyen_s", "acc_pdf", "acc_image",
        "acc_modeles_abc", "acc_modele_d",
        "rappel_doublon", "precision_doublon",
        "taux_signalement_erreurs",
    ]
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=entetes)
        w.writeheader()
        for config, m in resultats_configs.items():
            if not m:
                continue
            pc = m.get("precision_champs", {})
            w.writerow({
                "configuration":       config,
                "precision_totale":    m.get("precision_totale", ""),
                "prec_montant_ht":     pc.get("montant_ht", ""),
                "prec_tva":            pc.get("tva", ""),
                "prec_montant_ttc":    pc.get("montant_ttc", ""),
                "prec_numero_facture": pc.get("numero_facture", ""),
                "prec_date":           pc.get("date", ""),
                "prec_fournisseur":    pc.get("fournisseur", ""),
                "temps_moyen_s":       m.get("temps_moyen_s", ""),
                "acc_pdf":             m.get("acc_pdf", ""),
                "acc_image":           m.get("acc_image", ""),
                "acc_modeles_abc":     m.get("acc_modeles_abc", ""),
                "acc_modele_d":        m.get("acc_modele_d", ""),
                "rappel_doublon":      m.get("rappel_doublon", ""),
                "precision_doublon":   m.get("precision_doublon", ""),
                "taux_signalement_erreurs": m.get("taux_signalement_erreurs", ""),
            })


# ---------------------------------------------------------------------------
# Execution d'une configuration
# ---------------------------------------------------------------------------

def executer_config(config: str) -> tuple[list[dict], dict]:
    """
    Parcourt les fichiers du jeu de test et evalue la configuration donnee.
    Retourne (liste_details, metriques).
    """
    vt_dict = charger_verite_terrain()
    fichiers = sorted(DOSSIER_TEST.iterdir())
    fichiers = [f for f in fichiers if f.suffix.lower() in (".pdf", ".png", ".jpg") and f.name != ".gitkeep"]
    # Originaux en premier, doublons ensuite : la detection de doublon necessite
    # que les originaux soient deja en base avant de traiter leurs copies.
    fichiers = sorted(fichiers, key=lambda f: (1 if f.stem.startswith("doublon") else 0, f.name))

    # Base temporaire isolee pour le systeme complet
    if config == "complet":
        import base as base_mod
        tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp_db.close()
        conn = base_mod.obtenir_connexion(tmp_db.name)
        base_mod.initialiser_base(conn)
    else:
        conn = None

    resultats = []
    total = len(fichiers)

    for i, chemin in enumerate(fichiers, 1):
        nom = chemin.name
        vt  = vt_dict.get(nom, {})
        est_doublon = "doublon_de" in vt

        print(f"  [{i:2d}/{total}] {nom:<30s}", end="", flush=True)
        debut_total = time.perf_counter()

        if config == "regex":
            valeurs, duree = evaluer_fichier_regex(chemin)
            statut = None
        elif config == "llm":
            valeurs, duree = evaluer_fichier_llm(chemin)
            statut = None
        else:  # complet
            valeurs, statut, duree = evaluer_fichier_complet(chemin, conn)

        # Comparaison a la verite terrain (uniquement pour les originaux)
        champs_ok = {}
        if not est_doublon:
            for c in CHAMPS:
                champs_ok[c] = champ_correct(valeurs.get(c), vt.get(c), c)

        tout_ok = all(champs_ok.values()) if champs_ok else None
        print(f"  {'OK' if tout_ok else ('DOUBLON' if est_doublon else 'PARTIEL'):8s}  {duree:.1f}s")

        resultats.append({
            "fichier":      nom,
            "est_doublon":  est_doublon,
            "modele":       vt.get("modele"),
            "type_fichier": "pdf" if chemin.suffix.lower() == ".pdf" else "image",
            "valeurs":      valeurs,
            "verite":       {c: vt.get(c) for c in CHAMPS},
            "champs_ok":    champs_ok,
            "statut":       statut,
            "duree":        round(duree, 3),
        })

    if conn:
        conn.close()
        os.unlink(tmp_db.name)

    metriques = calculer_metriques(resultats)
    return resultats, metriques


# ---------------------------------------------------------------------------
# Point d'entree
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Evaluation du systeme de traitement des factures")
    parser.add_argument(
        "--config",
        choices=["regex", "llm", "complet", "tout"],
        default="complet",
        help="Configuration a evaluer (defaut: complet)",
    )
    parser.add_argument(
        "--modele",
        default=None,
        help="Modele Ollama a utiliser (ex. qwen2.5:3b)",
    )
    args = parser.parse_args()

    if args.modele:
        os.environ["OLLAMA_MODELE"] = args.modele
        print(f"Modele Ollama : {args.modele}")

    configs = ["regex", "llm", "complet"] if args.config == "tout" else [args.config]

    tous_resultats = {}
    toutes_metriques = {}

    for config in configs:
        print(f"\n--- Configuration : {config.upper()} ---")
        resultats, metriques = executer_config(config)
        tous_resultats[config]  = resultats
        toutes_metriques[config] = metriques

        # Sauvegarde JSON details
        chemin_json = DOSSIER_RES / f"details_{config}.json"
        chemin_json.parent.mkdir(parents=True, exist_ok=True)
        chemin_json.write_text(
            json.dumps({"config": config, "modele": args.modele or os.getenv("OLLAMA_MODELE", "qwen2.5:7b"),
                        "resultats": resultats, "metriques": metriques},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  Details sauvegardes : {chemin_json}")

    # Tableau console
    afficher_tableau(toutes_metriques)

    # CSV de synthese
    chemin_csv = DOSSIER_RES / "resume.csv"
    sauvegarder_csv(toutes_metriques, chemin_csv)
    print(f"\nTableau CSV : {chemin_csv}")

    # Parametres de reproduction (pour le rapport)
    print("\nParametres de reproduction :")
    import pytesseract
    try:
        tess_v = pytesseract.get_tesseract_version()
    except Exception:
        tess_v = "inconnue"
    print(f"  Tesseract : {tess_v}")
    print(f"  Modele Ollama : {os.getenv('OLLAMA_MODELE', 'qwen2.5:7b')}")
    print(f"  Temperature   : 0  (deterministe)")
    print(f"  Graine donnees : 42")


if __name__ == "__main__":
    main()
