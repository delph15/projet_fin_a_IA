# modeles.py — quatre gabarits visuels de facture (A, B, C, D)
# Chaque modèle dispose d'une mise en page différente afin que le système
# d'extraction ne puisse pas s'appuyer sur une position fixe des champs.

from fpdf import FPDF


def _entete_commun(pdf: FPDF, fournisseur: str, numero: str, date: str) -> None:
    """Remplit les champs identiques dans tous les modèles."""
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, fournisseur, ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, f"Numéro : {numero}", ln=True)
    pdf.cell(0, 6, f"Date : {date}", ln=True)
    pdf.ln(4)


def _ligne_montants(pdf: FPDF, montant_ht: float, tva: float, montant_ttc: float) -> None:
    """Bloc montants partagé par les modèles A et B."""
    pdf.cell(0, 6, f"Montant HT  : {montant_ht:.2f} EUR", ln=True)
    pdf.cell(0, 6, f"TVA (20 %)  : {tva:.2f} EUR", ln=True)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, f"Total TTC   : {montant_ttc:.2f} EUR", ln=True)


# ---------------------------------------------------------------------------
# Modèle A — mise en page simple, étiquettes en français courant
# ---------------------------------------------------------------------------

def generer_modele_a(champs: dict) -> FPDF:
    """
    En-tête fournisseur en haut, bloc adresse fictif, puis tableau montants.
    Étiquettes : « Montant HT », « TVA (20 %) », « Total TTC ».
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(20, 20, 20)

    # Titre
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "FACTURE", ln=True, align="C")
    pdf.ln(4)

    _entete_commun(pdf, champs["fournisseur"], champs["numero_facture"], champs["date"])

    # Adresse fictive (non extraite)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, champs.get("adresse", ""), ln=True)
    pdf.ln(6)

    # Montants
    pdf.set_font("Helvetica", "", 11)
    _ligne_montants(pdf, champs["montant_ht"], champs["tva"], champs["montant_ttc"])

    # Pied de page
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 5, "Merci de votre confiance.", ln=True)

    return pdf


# ---------------------------------------------------------------------------
# Modèle B — bloc fournisseur à droite, montants dans un tableau centré
# ---------------------------------------------------------------------------

def generer_modele_b(champs: dict) -> FPDF:
    """
    Fournisseur aligné à droite, numéro et date à gauche,
    montants dans un tableau avec bordures.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(20, 20, 20)

    # Fournisseur à droite
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, champs["fournisseur"], ln=True, align="R")
    pdf.ln(2)

    # Référence et date à gauche
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, f"Réf. facture : {champs['numero_facture']}", ln=True)
    pdf.cell(0, 6, f"Émise le {champs['date']}", ln=True)
    pdf.ln(6)

    # Tableau montants avec bordures
    col_w = 90
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(col_w, 8, "Désignation", border=1)
    pdf.cell(col_w, 8, "Montant (EUR)", border=1, ln=True)

    pdf.set_font("Helvetica", "", 11)
    lignes = [
        ("Montant hors taxe", f"{champs['montant_ht']:.2f}"),
        ("TVA 20 %",          f"{champs['tva']:.2f}"),
        ("Total TTC",         f"{champs['montant_ttc']:.2f}"),
    ]
    for libelle, valeur in lignes:
        pdf.cell(col_w, 7, libelle, border=1)
        pdf.cell(col_w, 7, valeur,  border=1, align="R", ln=True)

    return pdf


# ---------------------------------------------------------------------------
# Modèle C — style « bon de commande », libellés abrégés
# ---------------------------------------------------------------------------

def generer_modele_c(champs: dict) -> FPDF:
    """
    Numéro et date en première ligne, fournisseur en dessous en petit,
    montants avec libellés courts (HT, TVA, TTC).
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(20, 20, 20)

    # Ligne référence + date
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(95, 7, f"N° {champs['numero_facture']}")
    pdf.cell(95, 7, champs["date"], ln=True, align="R")
    pdf.ln(2)

    # Fournisseur
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 7, champs["fournisseur"], ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, champs.get("adresse", ""), ln=True)
    pdf.ln(8)

    # Montants avec libellés courts
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, f"HT    {champs['montant_ht']:.2f} EUR", ln=True)
    pdf.cell(0, 6, f"TVA   {champs['tva']:.2f} EUR", ln=True)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, f"TTC   {champs['montant_ttc']:.2f} EUR", ln=True)

    return pdf


# ---------------------------------------------------------------------------
# Modèle D — format « facture pro », jamais vu en développement
# ---------------------------------------------------------------------------

def generer_modele_d(champs: dict) -> FPDF:
    """
    En-tête avec bandeau gris, fournisseur en blanc sur fond gris,
    tableau montants en bas de page.
    Utilisé uniquement dans le jeu de test → ne jamais servir au réglage
    des regex ou du prompt.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(20, 20, 20)

    # Bandeau gris
    pdf.set_fill_color(80, 80, 80)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 12, f"  {champs['fournisseur']}", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # Numéro et date sur deux colonnes
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(95, 6, f"Facture n° {champs['numero_facture']}")
    pdf.cell(95, 6, f"Date d'émission : {champs['date']}", ln=True)
    pdf.ln(10)

    # Tableau récapitulatif
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Récapitulatif", ln=True, fill=True)

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(130, 7, "Base HT")
    pdf.cell(50,  7, f"{champs['montant_ht']:.2f} EUR", align="R", ln=True)
    pdf.cell(130, 7, "TVA (taux 20 %)")
    pdf.cell(50,  7, f"{champs['tva']:.2f} EUR", align="R", ln=True)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(130, 7, "Net a payer")
    pdf.cell(50,  7, f"{champs['montant_ttc']:.2f} EUR", align="R", ln=True)

    return pdf


# Registre des fonctions de génération, indexé par lettre
MODELES = {
    "A": generer_modele_a,
    "B": generer_modele_b,
    "C": generer_modele_c,
    "D": generer_modele_d,
}
