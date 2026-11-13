# generateur.py — génère les 35 factures fictives + leur vérité terrain JSON
#
# Usage :
#   python generateur/generateur.py
#
# Sorties :
#   donnees/dev/           10 PDF (modèles A, B, C)
#   donnees/test/          20 PDF + 5 doublons (modèles A, B, C, D)
#   donnees/verite_terrain/ 35 fichiers JSON
#
# La graine fixe (GRAINE = 42) garantit la reproductibilité.

import json
import os
import random
import shutil
from pathlib import Path

from faker import Faker
from PIL import Image, ImageFilter

from modeles import MODELES

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GRAINE = 42
TAUX_TVA = 0.20
DOSSIER_DEV  = Path("donnees/dev")
DOSSIER_TEST = Path("donnees/test")
DOSSIER_VT   = Path("donnees/verite_terrain")

# Répartition : 10 dev (A, B, C), 20 test (A, B, C, D), 5 doublons dans test
NB_DEV      = 10
NB_TEST_ORI = 20
NB_DOUBLONS = 5

# Un tiers des factures sera converti en image dégradée
RATIO_IMAGE = 1 / 3


# ---------------------------------------------------------------------------
# Génération des données Faker
# ---------------------------------------------------------------------------

def creer_faker_et_rng() -> tuple[Faker, random.Random]:
    """Retourne un Faker et un Random tous deux initialisés avec GRAINE."""
    fake = Faker("fr_FR")
    Faker.seed(GRAINE)
    rng = random.Random(GRAINE)
    return fake, rng


def generer_champs(fake: Faker, rng: random.Random, index: int) -> dict:
    """Produit les 6 champs d'une facture + données auxiliaires."""
    montant_ht = round(rng.uniform(100.0, 5000.0), 2)
    tva        = round(montant_ht * TAUX_TVA, 2)
    montant_ttc = round(montant_ht + tva, 2)

    # Numéro de facture : format FAC-AAAA-NNNN
    annee  = rng.randint(2024, 2026)
    numero = f"FAC-{annee}-{index:04d}"

    # Date au format ISO
    date_obj = fake.date_between(start_date="-2y", end_date="today")
    date_iso  = date_obj.isoformat()

    return {
        "fournisseur":    fake.company(),
        "numero_facture": numero,
        "date":           date_iso,
        "montant_ht":     montant_ht,
        "tva":            tva,
        "montant_ttc":    montant_ttc,
        "adresse":        fake.address().replace("\n", ", "),
    }


# ---------------------------------------------------------------------------
# Dégradation image (simulation de scan)
# ---------------------------------------------------------------------------

def degrader_en_image(chemin_pdf: Path, chemin_image: Path, rng: random.Random) -> None:
    """
    Convertit la première page du PDF en PNG dégradé via PyMuPDF (fitz).
    PyMuPDF fonctionne sur Windows sans Poppler.
    Dégradations appliquées : flou, rotation légère (±3°), réduction de résolution.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(str(chemin_pdf))
    page = doc[0]
    # Rendu à 150 dpi (facteur 150/72 ≈ 2.08)
    mat = fitz.Matrix(150 / 72, 150 / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()

    # Flou
    img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.5, 1.2)))

    # Rotation légère
    angle = rng.uniform(-3.0, 3.0)
    img = img.rotate(angle, expand=False, fillcolor=(255, 255, 255))

    # Bruit : réduction + agrandissement de résolution (effet pixelisé)
    w, h = img.size
    img = img.resize((w // 2, h // 2), Image.BILINEAR)
    img = img.resize((w, h), Image.BILINEAR)

    img.save(str(chemin_image))


# ---------------------------------------------------------------------------
# Écriture du JSON de vérité terrain
# ---------------------------------------------------------------------------

def ecrire_verite(champs: dict, nom_fichier: str, modele: str) -> None:
    """Enregistre le JSON de vérité terrain pour une facture."""
    vt = {
        "fichier": nom_fichier,
        "modele":  modele,
        "fournisseur":    champs["fournisseur"],
        "numero_facture": champs["numero_facture"],
        "date":           champs["date"],
        "montant_ht":     champs["montant_ht"],
        "tva":            champs["tva"],
        "montant_ttc":    champs["montant_ttc"],
    }
    nom_json = Path(nom_fichier).stem + ".json"
    chemin   = DOSSIER_VT / nom_json
    chemin.write_text(json.dumps(vt, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Génération d'une facture (PDF + éventuellement image)
# ---------------------------------------------------------------------------

def generer_facture(
    champs: dict,
    modele: str,
    dossier: Path,
    nom_base: str,
    rng: random.Random,
    faire_image: bool,
) -> str:
    """
    Génère le PDF et, si faire_image est True, le remplace par une image PNG.
    Retourne le nom du fichier final (PDF ou PNG).
    """
    chemin_pdf = dossier / f"{nom_base}.pdf"
    pdf = MODELES[modele](champs)
    pdf.output(str(chemin_pdf))

    if faire_image:
        chemin_image = dossier / f"{nom_base}.png"
        degrader_en_image(chemin_pdf, chemin_image, rng)
        chemin_pdf.unlink()  # on ne garde que l'image
        return f"{nom_base}.png"

    return f"{nom_base}.pdf"


# ---------------------------------------------------------------------------
# Création des doublons
# ---------------------------------------------------------------------------

def creer_doublons(fichiers_originaux: list[tuple[str, Path]], rng: random.Random) -> None:
    """
    Choisit NB_DOUBLONS fichiers parmi les originaux du jeu test et en fait
    une copie exacte (même contenu, nom différent → doublon SHA-256).
    La vérité terrain du doublon pointe vers le fichier original.
    """
    choix = rng.sample(fichiers_originaux, NB_DOUBLONS)
    for i, (nom_original, chemin_original) in enumerate(choix, start=1):
        nom_doublon = f"doublon_{i:02d}{Path(nom_original).suffix}"
        chemin_doublon = DOSSIER_TEST / nom_doublon
        shutil.copy2(str(chemin_original), str(chemin_doublon))

        # Vérité terrain du doublon : même champs, doublon signalé
        vt_original = json.loads(
            (DOSSIER_VT / (Path(nom_original).stem + ".json")).read_text(encoding="utf-8")
        )
        vt_doublon = dict(vt_original)
        vt_doublon["fichier"]  = nom_doublon
        vt_doublon["doublon_de"] = nom_original
        nom_json = Path(nom_doublon).stem + ".json"
        (DOSSIER_VT / nom_json).write_text(
            json.dumps(vt_doublon, ensure_ascii=False, indent=2), encoding="utf-8"
        )


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main() -> None:
    # Création des dossiers de sortie
    for d in (DOSSIER_DEV, DOSSIER_TEST, DOSSIER_VT):
        d.mkdir(parents=True, exist_ok=True)

    fake, rng = creer_faker_et_rng()

    # --- Jeu de développement : 10 factures, modèles A B C ---
    modeles_dev = ["A", "B", "C"]
    for i in range(1, NB_DEV + 1):
        modele  = modeles_dev[(i - 1) % len(modeles_dev)]
        champs  = generer_champs(fake, rng, i)
        nom_base = f"facture_{i:03d}"
        faire_image = (i % round(1 / RATIO_IMAGE) == 0)  # 1 sur 3
        nom_fichier = generer_facture(champs, modele, DOSSIER_DEV, nom_base, rng, faire_image)
        ecrire_verite(champs, nom_fichier, modele)
        print(f"[dev]  {nom_fichier}  (modèle {modele})")

    # --- Jeu de test : 20 factures, modèles A B C D ---
    modeles_test = ["A", "B", "C", "D"]
    fichiers_test = []  # pour choisir les doublons ensuite
    for i in range(NB_DEV + 1, NB_DEV + NB_TEST_ORI + 1):
        modele   = modeles_test[(i - NB_DEV - 1) % len(modeles_test)]
        champs   = generer_champs(fake, rng, i)
        nom_base = f"facture_{i:03d}"
        faire_image = ((i - NB_DEV) % round(1 / RATIO_IMAGE) == 0)
        nom_fichier = generer_facture(champs, modele, DOSSIER_TEST, nom_base, rng, faire_image)
        ecrire_verite(champs, nom_fichier, modele)
        fichiers_test.append((nom_fichier, DOSSIER_TEST / nom_fichier))
        print(f"[test] {nom_fichier}  (modèle {modele})")

    # --- Doublons ---
    creer_doublons(fichiers_test, rng)
    for i in range(1, NB_DOUBLONS + 1):
        print(f"[test] doublon_{i:02d}  (copie exacte)")

    print(f"\nTerminé : {NB_DEV} fichiers dans dev/, "
          f"{NB_TEST_ORI + NB_DOUBLONS} dans test/, "
          f"{NB_DEV + NB_TEST_ORI + NB_DOUBLONS} JSON dans verite_terrain/")


if __name__ == "__main__":
    # Se placer à la racine du projet pour que les chemins relatifs fonctionnent
    racine = Path(__file__).resolve().parent.parent
    os.chdir(racine)
    main()
