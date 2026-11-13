# ocr.py — lecture du texte d'une facture PDF ou image
#
# Deux chemins :
#   PDF natif  → pdfplumber (texte vectoriel, confiance = 1.0)
#   Image      → prétraitement Pillow + Tesseract langue "fra"
#
# Contrat : ne lève jamais d'exception vers l'appelant.
# Si le texte est vide ou si un outil est indisponible,
# retourne ("", 0.0) → l'appelant positionne le statut "a_verifier".

import os
from pathlib import Path

import pdfplumber
import pytesseract
from PIL import Image, ImageFilter, ImageOps

# Chemin Tesseract (lu depuis l'env, valeur par défaut Windows)
_TESSERACT_CMD = os.getenv(
    "TESSERACT_CMD",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
)
pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD

# Configuration Tesseract : mode page "bloc de texte uniforme", sortie brute
_CONFIG_TESS = "--oem 3 --psm 6 -l fra"

# Extensions reconnues comme images
_EXTENSIONS_IMAGE = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}


# ---------------------------------------------------------------------------
# Prétraitement image avant OCR
# ---------------------------------------------------------------------------

def _preparer_image(chemin: Path) -> Image.Image:
    """
    Prépare une image pour Tesseract :
    - conversion en niveaux de gris
    - agrandissement si l'image est petite (Tesseract préfère ≥ 300 dpi)
    - binarisation adaptative (seuil d'Otsu simulé via point())
    - léger filtre de netteté
    """
    img = Image.open(chemin).convert("L")  # niveaux de gris

    # Agrandir si trop petite
    largeur, hauteur = img.size
    if largeur < 1000:
        facteur = 1000 / largeur
        img = img.resize(
            (int(largeur * facteur), int(hauteur * facteur)),
            Image.LANCZOS,
        )

    # Binarisation simple : pixels < 150 → noir, autres → blanc
    img = img.point(lambda p: 0 if p < 150 else 255)

    # Netteté
    img = img.filter(ImageFilter.SHARPEN)

    return img


# ---------------------------------------------------------------------------
# Score de confiance moyen à partir des données Tesseract
# ---------------------------------------------------------------------------

def _confiance_tesseract(chemin: Path, image: Image.Image) -> float:
    """
    Retourne la confiance moyenne (0–1) calculée à partir des données
    mot par mot de Tesseract. Retourne 0.0 en cas d'erreur.
    """
    try:
        donnees = pytesseract.image_to_data(
            image,
            config=_CONFIG_TESS,
            output_type=pytesseract.Output.DICT,
        )
        confs = [
            int(c) for c in donnees["conf"]
            if str(c).lstrip("-").isdigit() and int(c) >= 0
        ]
        if not confs:
            return 0.0
        return round(sum(confs) / len(confs) / 100, 3)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Lecture d'un PDF natif
# ---------------------------------------------------------------------------

def lire_pdf(chemin: Path) -> tuple[str, float]:
    """
    Extrait le texte d'un PDF vectoriel via pdfplumber.
    Retourne (texte, confiance).
    La confiance est 1.0 si du texte est trouvé, 0.0 sinon.
    """
    try:
        texte_pages = []
        with pdfplumber.open(str(chemin)) as pdf:
            for page in pdf.pages:
                contenu = page.extract_text()
                if contenu:
                    texte_pages.append(contenu)
        texte = "\n".join(texte_pages).strip()
        return (texte, 1.0) if texte else ("", 0.0)
    except Exception:
        return "", 0.0


# ---------------------------------------------------------------------------
# OCR d'une image
# ---------------------------------------------------------------------------

def lire_image(chemin: Path) -> tuple[str, float]:
    """
    Applique le prétraitement puis Tesseract sur une image.
    Retourne (texte, confiance_moyenne).
    """
    try:
        image = _preparer_image(chemin)
        texte = pytesseract.image_to_string(image, config=_CONFIG_TESS).strip()
        confiance = _confiance_tesseract(chemin, image) if texte else 0.0
        return texte, confiance
    except Exception:
        return "", 0.0


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def extraire_texte(chemin_fichier: str | Path) -> tuple[str, float]:
    """
    Choisit automatiquement entre lecture PDF et OCR image.

    Paramètre
    ---------
    chemin_fichier : chemin vers le fichier (PDF ou image)

    Retour
    ------
    (texte, confiance)
        texte      : texte brut extrait, chaîne vide si rien trouvé
        confiance  : float entre 0.0 et 1.0
    """
    chemin = Path(chemin_fichier)

    if not chemin.exists():
        return "", 0.0

    extension = chemin.suffix.lower()

    if extension == ".pdf":
        texte, confiance = lire_pdf(chemin)
        # Fallback : si le PDF est une image scannée sans texte vectoriel
        if not texte:
            return "", 0.0
        return texte, confiance

    if extension in _EXTENSIONS_IMAGE:
        return lire_image(chemin)

    # Format non reconnu
    return "", 0.0
