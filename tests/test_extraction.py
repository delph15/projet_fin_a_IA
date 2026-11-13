# test_extraction.py - tests unitaires des modules extraction et controles
#
# Lancement :
#   pytest tests/ -v
#
# Ce fichier teste sans OCR ni Ollama : les fonctions recevant du texte brut.

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

from controles import verifier_arithmetique, verifier_date
from extraction import (
    _extraire_date,
    _extraire_fournisseur,
    _extraire_montants,
    _extraire_numero,
    extraire_par_regex,
    normaliser_nombre,
)
from fusion import _fusionner_champ, fusionner


# ---------------------------------------------------------------------------
# normaliser_nombre
# ---------------------------------------------------------------------------

class TestNormaliserNombre:
    def test_point_decimal(self):
        assert normaliser_nombre("1193.73") == 1193.73

    def test_virgule_decimal(self):
        assert normaliser_nombre("1193,73") == 1193.73

    def test_espace_milliers_virgule(self):
        assert normaliser_nombre("1 193,73") == 1193.73

    def test_format_euro_complet(self):
        assert normaliser_nombre("3 233,19") == 3233.19

    def test_point_milliers_virgule_decimal(self):
        assert normaliser_nombre("3.233,19") == 3233.19

    def test_ocr_sans_decimale(self):
        # OCR lit "119373" au lieu de "1193.73"
        assert normaliser_nombre("119373") == 1193.73

    def test_entier_petit(self):
        # Entier <= 999 : pas d'heuristique centimes
        assert normaliser_nombre("100") == 100.0

    def test_vide(self):
        assert normaliser_nombre("") is None

    def test_non_numerique(self):
        assert normaliser_nombre("abc") is None


# ---------------------------------------------------------------------------
# Extraction du numero de facture
# ---------------------------------------------------------------------------

class TestExtraireNumero:
    def test_format_standard(self):
        texte = "Ref. facture : FAC-2024-0001"
        r = _extraire_numero(texte)
        assert r["valeur"] == "FAC-2024-0001"
        assert r["confiance"] > 0.9

    def test_minuscule(self):
        texte = "fac-2026-0042"
        r = _extraire_numero(texte)
        assert r["valeur"] == "FAC-2026-0042"

    def test_absent(self):
        r = _extraire_numero("aucun numero ici")
        assert r["valeur"] is None
        assert r["confiance"] == 0.0


# ---------------------------------------------------------------------------
# Extraction de la date
# ---------------------------------------------------------------------------

class TestExtraireDate:
    def test_date_iso(self):
        r = _extraire_date("Date : 2026-10-14")
        assert r["valeur"] == "2026-10-14"

    def test_date_invalide_ignoree(self):
        # 2026-13-01 : mois 13 inexistant
        texte = "Date : 2026-13-01\nAutre date : 2025-05-20"
        r = _extraire_date(texte)
        assert r["valeur"] == "2025-05-20"

    def test_absente(self):
        r = _extraire_date("Pas de date ici")
        assert r["valeur"] is None


# ---------------------------------------------------------------------------
# Extraction des montants (approche par ligne)
# ---------------------------------------------------------------------------

TEXTE_MODELE_A = """\
FACTURE
Durand SARL
Numero : FAC-2025-0007
Date : 2025-06-15
Montant HT  : 1000.00 EUR
TVA (20 %)  : 200.00 EUR
Total TTC   : 1200.00 EUR
"""

TEXTE_MODELE_B = """\
Durand SARL
Ref. facture : FAC-2025-0007
Emise le 2025-06-15
Montant hors taxe | 1000.00
TVA 20 %          | 200.00
Total TTC         | 1200.00
"""

TEXTE_MODELE_C = """\
N FAC-2025-0007 2025-06-15
Durand SARL
HT    1000.00 EUR
TVA   200.00 EUR
TTC   1200.00 EUR
"""

TEXTE_MODELE_D = """\
Durand SARL
Facture n 2025-0007
Date d emission : 2025-06-15
Base HT         1000.00 EUR
TVA (taux 20 %) 200.00 EUR
Net a payer     1200.00 EUR
"""


class TestExtraireMontants:
    @pytest.mark.parametrize("texte,ht,tva,ttc", [
        (TEXTE_MODELE_A, 1000.00, 200.00, 1200.00),
        (TEXTE_MODELE_B, 1000.00, 200.00, 1200.00),
        (TEXTE_MODELE_C, 1000.00, 200.00, 1200.00),
        (TEXTE_MODELE_D, 1000.00, 200.00, 1200.00),
    ])
    def test_montants_par_modele(self, texte, ht, tva, ttc):
        ht_r, tva_r, ttc_r = _extraire_montants(texte)
        assert ht_r["valeur"] == ht,  f"HT attendu {ht}, obtenu {ht_r['valeur']}"
        assert tva_r["valeur"] == tva, f"TVA attendue {tva}, obtenu {tva_r['valeur']}"
        assert ttc_r["valeur"] == ttc, f"TTC attendu {ttc}, obtenu {ttc_r['valeur']}"

    def test_confiance_elevee_si_arithmetique_ok(self):
        ht, tva, ttc = _extraire_montants(TEXTE_MODELE_A)
        assert ht["confiance"] >= 0.95
        assert tva["confiance"] >= 0.95
        assert ttc["confiance"] >= 0.95

    def test_confiance_normale_si_arith_echoue(self):
        texte = "Montant HT  : 1000.00 EUR\nTVA (20 %) : 150.00 EUR\nTotal TTC : 1200.00 EUR"
        ht, tva, ttc = _extraire_montants(texte)
        # HT+TVA = 1150 != 1200 : pas de bonus
        assert ht["confiance"] < 0.95


# ---------------------------------------------------------------------------
# Extraction du fournisseur
# ---------------------------------------------------------------------------

class TestExtraireFournisseur:
    def test_apres_titre_facture(self):
        texte = "FACTURE\nDurand SARL\nNumero : FAC-2025-0007"
        r = _extraire_fournisseur(texte)
        assert r["valeur"] == "Durand SARL"
        assert r["confiance"] >= 0.80

    def test_premiere_ligne_valide(self):
        # Modele B : fournisseur en premiere ligne
        texte = "Durand SARL\nRef. facture : FAC-2025-0007\nEmise le 2025-06-15"
        r = _extraire_fournisseur(texte)
        assert r["valeur"] == "Durand SARL"

    def test_exclure_ligne_tva(self):
        texte = "TVA 20 %\nDurand SARL"
        r = _extraire_fournisseur(texte)
        assert r["valeur"] == "Durand SARL"


# ---------------------------------------------------------------------------
# extraire_par_regex : pipeline complet sur texte factice
# ---------------------------------------------------------------------------

class TestExtraireParRegex:
    def test_pipeline_complet_modele_a(self):
        r = extraire_par_regex(TEXTE_MODELE_A)
        assert r["numero_facture"]["valeur"] == "FAC-2025-0007"
        assert r["date"]["valeur"] == "2025-06-15"
        assert r["montant_ht"]["valeur"] == 1000.00
        assert r["tva"]["valeur"] == 200.00
        assert r["montant_ttc"]["valeur"] == 1200.00
        assert r["fournisseur"]["valeur"] == "Durand SARL"

    def test_texte_vide(self):
        r = extraire_par_regex("")
        for cle in ("fournisseur", "numero_facture", "date", "montant_ht", "tva", "montant_ttc"):
            assert r[cle]["valeur"] is None


# ---------------------------------------------------------------------------
# verifier_arithmetique
# ---------------------------------------------------------------------------

class TestVerifierArithmetique:
    def test_exact(self):
        assert verifier_arithmetique(1000.00, 200.00, 1200.00) is True

    def test_dans_tolerance(self):
        assert verifier_arithmetique(1000.00, 200.00, 1200.005) is True

    def test_hors_tolerance(self):
        assert verifier_arithmetique(1000.00, 150.00, 1200.00) is False

    def test_valeur_none(self):
        assert verifier_arithmetique(None, 200.00, 1200.00) is False


# ---------------------------------------------------------------------------
# verifier_date
# ---------------------------------------------------------------------------

class TestVerifierDate:
    def test_date_valide(self):
        assert verifier_date("2026-10-14") is True

    def test_mois_invalide(self):
        assert verifier_date("2026-13-01") is False

    def test_jour_invalide(self):
        assert verifier_date("2026-02-30") is False

    def test_none(self):
        assert verifier_date(None) is False

    def test_format_incorrect(self):
        assert verifier_date("14/10/2026") is False


# ---------------------------------------------------------------------------
# _fusionner_champ
# ---------------------------------------------------------------------------

class TestFusionnerChamp:
    def _c(self, valeur, confiance, source):
        return {"valeur": valeur, "confiance": confiance, "source": source}

    def test_accord_float(self):
        r = self._c(1000.00, 0.97, "regex")
        l = self._c(1000.00, 0.90, "llm")
        f = _fusionner_champ(r, l)
        assert f["valeur"] == 1000.00
        assert f["source"] == "accord"
        assert f["divergence"] is False
        assert f["confiance"] > 0.97  # bonus accord

    def test_accord_str(self):
        r = self._c("Durand SARL", 0.85, "regex")
        l = self._c("Durand SARL", 0.88, "llm")
        f = _fusionner_champ(r, l)
        assert f["source"] == "accord"

    def test_desaccord(self):
        r = self._c(1000.00, 0.97, "regex")
        l = self._c(1500.00, 0.85, "llm")
        f = _fusionner_champ(r, l)
        assert f["valeur"] == 1000.00  # regex plus confiante
        assert f["divergence"] is True
        assert f["confiance"] < 0.97  # penalite

    def test_seul_regex(self):
        r = self._c("FAC-2025-0001", 0.98, "regex")
        l = self._c(None, 0.0, "llm")
        f = _fusionner_champ(r, l)
        assert f["valeur"] == "FAC-2025-0001"
        assert f["source"] == "regex"
        assert f["divergence"] is False

    def test_seul_llm(self):
        r = self._c(None, 0.0, "regex")
        l = self._c("Durand SARL", 0.88, "llm")
        f = _fusionner_champ(r, l)
        assert f["valeur"] == "Durand SARL"
        assert f["source"] == "llm"

    def test_aucun(self):
        r = self._c(None, 0.0, "regex")
        l = self._c(None, 0.0, "llm")
        f = _fusionner_champ(r, l)
        assert f["valeur"] is None


# ---------------------------------------------------------------------------
# fusionner : signaler_verification
# ---------------------------------------------------------------------------

class TestFusionner:
    def _champ(self, v, c, s):
        return {"valeur": v, "confiance": c, "source": s}

    def _resultats(self, accord=True):
        val = 1000.0
        return {
            "fournisseur":    self._champ("Durand SARL", 0.90, "regex"),
            "numero_facture": self._champ("FAC-2025-0001", 0.98, "regex"),
            "date":           self._champ("2025-06-15", 0.98, "regex"),
            "montant_ht":     self._champ(val, 0.97, "regex"),
            "tva":            self._champ(200.0, 0.97, "regex"),
            "montant_ttc":    self._champ(1200.0, 0.97, "regex"),
        }

    def test_pas_de_signalement_si_accord_ocr_bon(self):
        r = self._resultats()
        l = {k: {"valeur": r[k]["valeur"], "confiance": 0.90, "source": "llm"} for k in r}
        f = fusionner(r, l, confiance_ocr=1.0)
        assert f["meta"]["signaler_verification"] is False
        assert f["meta"]["nb_divergences"] == 0

    def test_signalement_si_ocr_faible(self):
        r = self._resultats()
        l = {k: {"valeur": r[k]["valeur"], "confiance": 0.90, "source": "llm"} for k in r}
        f = fusionner(r, l, confiance_ocr=0.50)
        assert f["meta"]["signaler_verification"] is True

    def test_signalement_si_divergence(self):
        r = self._resultats()
        l = {k: {"valeur": r[k]["valeur"], "confiance": 0.90, "source": "llm"} for k in r}
        l["montant_ht"] = {"valeur": 999.0, "confiance": 0.85, "source": "llm"}
        f = fusionner(r, l, confiance_ocr=1.0)
        assert f["meta"]["signaler_verification"] is True
        assert f["meta"]["nb_divergences"] >= 1
