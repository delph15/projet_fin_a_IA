# app.py - interface Streamlit de revue humaine des factures
#
# Lancement (depuis la racine du projet) :
#   streamlit run interface/app.py
#
# Prerequis : l'API FastAPI doit etre demarree sur le port 8000.

import os

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="Traitement des factures",
    page_icon=":page_facing_up:",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Utilitaires d'affichage
# ---------------------------------------------------------------------------

COULEUR_STATUT = {
    "recue":      ("#888888", "Recue"),
    "extraite":   ("#4a90d9", "Extraite"),
    "a_verifier": ("#e67e22", "A verifier"),
    "prete":      ("#27ae60", "Prete"),
    "validee":    ("#1abc9c", "Validee"),
    "rejetee":    ("#e74c3c", "Rejetee"),
    "doublon":    ("#9b59b6", "Doublon"),
}


def badge_statut(statut: str) -> str:
    couleur, libelle = COULEUR_STATUT.get(statut, ("#888888", statut))
    return f'<span style="background:{couleur};color:white;padding:2px 10px;border-radius:12px;font-size:0.85em">{libelle}</span>'


def couleur_confiance(conf: float) -> str:
    if conf is None:
        return "#888888"
    if conf >= 0.90:
        return "#27ae60"
    if conf >= 0.70:
        return "#e67e22"
    return "#e74c3c"


def afficher_confiance(conf) -> str:
    if conf is None:
        return "—"
    couleur = couleur_confiance(conf)
    return f'<span style="color:{couleur};font-weight:bold">{conf:.2f}</span>'


def icone_bool(valeur: bool) -> str:
    return "OK" if valeur else "ECHEC"


# ---------------------------------------------------------------------------
# Appels API
# ---------------------------------------------------------------------------

def get_factures(statut: str = None) -> list[dict]:
    params = {"statut": statut} if statut else {}
    try:
        r = requests.get(f"{API_URL}/factures/", params=params, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Impossible de joindre l'API : {e}")
        return []


def get_facture(id_facture: int) -> dict | None:
    try:
        r = requests.get(f"{API_URL}/factures/{id_facture}", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def action_facture(id_facture: int, action: str) -> bool:
    """action : 'valider' ou 'rejeter'"""
    try:
        r = requests.put(f"{API_URL}/factures/{id_facture}/{action}", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Bloc detail d'une facture
# ---------------------------------------------------------------------------

CHAMPS_LABELS = {
    "fournisseur":    "Fournisseur",
    "numero_facture": "Numero de facture",
    "date":           "Date",
    "montant_ht":     "Montant HT",
    "tva":            "TVA",
    "montant_ttc":    "Montant TTC",
}

COLS_CHAMPS = [
    "fournisseur", "numero_facture", "date",
    "montant_ht", "tva", "montant_ttc",
]

COLS_CONF = [
    "conf_fournisseur", "conf_numero", "conf_date",
    "conf_ht", "conf_tva", "conf_ttc",
]

COLS_SRC = [
    "src_fournisseur", "src_numero", "src_date",
    "src_ht", "src_tva", "src_ttc",
]


def afficher_detail(f: dict, dans_expander: bool = False) -> None:
    """Affiche les champs, confiances, controles et boutons d'action."""

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("**Champs extraits**")
        lignes = []
        for champ, conf_col, src_col in zip(COLS_CHAMPS, COLS_CONF, COLS_SRC):
            valeur = f.get(champ, "—") or "—"
            conf   = f.get(conf_col)
            src    = f.get(src_col, "")
            lignes.append({
                "Champ":    CHAMPS_LABELS[champ],
                "Valeur":   str(valeur),
                "Confiance": f"{conf:.2f}" if conf is not None else "—",
                "Source":   src or "—",
            })
        st.table(lignes)

    with col2:
        st.markdown("**Controles metier**")
        st.write(f"Arithmetique  : {icone_bool(bool(f.get('ctrl_arithmetique')))}")
        st.write(f"Date valide   : {icone_bool(bool(f.get('ctrl_date_valide')))}")
        st.write(f"Doublon       : {'OUI' if f.get('ctrl_doublon') else 'non'}")
        st.markdown("---")
        st.write(f"Confiance OCR : **{f.get('conf_ocr', 0):.2f}**")
        st.write(f"Divergences   : {f.get('nb_divergences', 0)}")

    # Boutons d'action (uniquement si la facture n'est pas finalisee)
    statut = f.get("statut", "")
    if statut in ("prete", "a_verifier"):
        st.markdown("---")
        c1, c2, _ = st.columns([1, 1, 3])
        with c1:
            if st.button("Valider", key=f"val_{f['id']}", type="primary"):
                if action_facture(f["id"], "valider"):
                    st.success("Facture validee.")
                    st.rerun()
                else:
                    st.error("Echec de la validation.")
        with c2:
            if st.button("Rejeter", key=f"rej_{f['id']}"):
                if action_facture(f["id"], "rejeter"):
                    st.warning("Facture rejetee.")
                    st.rerun()
                else:
                    st.error("Echec du rejet.")


# ---------------------------------------------------------------------------
# Tableau de bord (compteurs par statut)
# ---------------------------------------------------------------------------

def afficher_tableau_de_bord(toutes: list[dict]) -> None:
    compteurs = {}
    for f in toutes:
        s = f.get("statut", "inconnu")
        compteurs[s] = compteurs.get(s, 0) + 1

    ordre = ["prete", "a_verifier", "validee", "rejetee", "doublon", "recue"]
    cols = st.columns(len(ordre))
    for col, statut in zip(cols, ordre):
        n = compteurs.get(statut, 0)
        _, libelle = COULEUR_STATUT.get(statut, ("#888", statut))
        col.metric(libelle, n)


# ---------------------------------------------------------------------------
# Page : file d'attente (prete + a_verifier)
# ---------------------------------------------------------------------------

def page_file_attente() -> None:
    st.header("File d'attente")

    prete      = get_factures("prete")
    a_verifier = get_factures("a_verifier")
    doublons   = get_factures("doublon")

    if not prete and not a_verifier and not doublons:
        st.success("Aucune facture en attente.")
        return

    # Factures pretes (confiance elevee, pas de divergence)
    if prete:
        st.subheader(f"Pretes a valider ({len(prete)})")
        for f in prete:
            with st.expander(f"[{f['id']}] {f.get('fichier','?')}  —  {f.get('fournisseur','?')}  |  {f.get('numero_facture','?')}  |  {f.get('date','?')}  |  TTC {f.get('montant_ttc','?')} EUR"):
                afficher_detail(f)

    # Factures a verifier (divergence ou OCR faible)
    if a_verifier:
        st.subheader(f"A verifier ({len(a_verifier)})")
        st.caption("Ces factures presentent une divergence, un controle echoue ou une OCR de faible qualite.")
        for f in a_verifier:
            with st.expander(f"[{f['id']}] {f.get('fichier','?')}  —  {f.get('fournisseur','?')}  |  {f.get('numero_facture','?')}"):
                afficher_detail(f)

    # Doublons detectes
    if doublons:
        st.subheader(f"Doublons detectes ({len(doublons)})")
        st.caption("Ces factures ont ete refusees automatiquement (meme empreinte ou meme reference).")
        for f in doublons:
            st.write(f"[{f['id']}] {f.get('fichier','?')} — {f.get('fournisseur','?')} / {f.get('numero_facture','?')}")


# ---------------------------------------------------------------------------
# Page : historique
# ---------------------------------------------------------------------------

def page_historique() -> None:
    st.header("Historique")

    statuts = ["(tous)", "validee", "rejetee", "prete", "a_verifier", "doublon", "recue"]
    choix = st.selectbox("Filtrer par statut", statuts)
    filtre = None if choix == "(tous)" else choix

    factures = get_factures(filtre)

    if not factures:
        st.info("Aucune facture trouvee.")
        return

    # Tableau recapitulatif
    lignes = []
    for f in factures:
        lignes.append({
            "ID":        f["id"],
            "Fichier":   f.get("fichier", ""),
            "Statut":    f.get("statut", ""),
            "Fournisseur": f.get("fournisseur", ""),
            "Numero":    f.get("numero_facture", ""),
            "Date":      f.get("date", ""),
            "TTC (EUR)": f.get("montant_ttc", ""),
            "Conf. OCR": f"{f.get('conf_ocr', 0):.2f}" if f.get("conf_ocr") is not None else "—",
        })
    st.dataframe(lignes, use_container_width=True)


# ---------------------------------------------------------------------------
# Navigation principale
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("Traitement automatise des factures")

    toutes = get_factures()
    if toutes:
        afficher_tableau_de_bord(toutes)
        st.markdown("---")

    onglet1, onglet2 = st.tabs(["File d'attente", "Historique"])

    with onglet1:
        page_file_attente()

    with onglet2:
        page_historique()


if __name__ == "__main__":
    main()
