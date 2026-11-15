# app.py - interface Streamlit de revue humaine des factures
#
# Lancement :
#   streamlit run interface/app.py
#
# Flux : upload → webhook n8n → API FastAPI → SQLite
# Streamlit lit et valide via l'API, ne traite jamais directement.

import base64
import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_URL         = os.getenv("API_URL",         "http://127.0.0.1:8000")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/facture")

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


def couleur_confiance(conf) -> str:
    if conf is None:
        return "#888888"
    if conf >= 0.90:
        return "#27ae60"
    if conf >= 0.70:
        return "#e67e22"
    return "#e74c3c"


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
    try:
        r = requests.put(f"{API_URL}/factures/{id_facture}/{action}", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def corriger_facture(id_facture: int, corrections: dict) -> bool:
    try:
        r = requests.put(
            f"{API_URL}/factures/{id_facture}/corriger",
            json=corrections,
            timeout=5,
        )
        return r.status_code == 200
    except Exception:
        return False


def get_fichier(id_facture: int) -> bytes | None:
    try:
        r = requests.get(f"{API_URL}/factures/{id_facture}/fichier", timeout=10)
        if r.status_code == 200:
            return r.content
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Affichage du fichier original (image ou PDF)
# ---------------------------------------------------------------------------

def afficher_fichier_original(id_facture: int, nom_fichier: str) -> None:
    contenu = get_fichier(id_facture)
    if contenu is None:
        st.caption("Fichier original non disponible.")
        return

    ext = Path(nom_fichier).suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif"):
        st.image(contenu, caption=nom_fichier, use_container_width=True)
    elif ext == ".pdf":
        b64 = base64.b64encode(contenu).decode()
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{b64}" '
            f'width="100%" height="500px" style="border:none;border-radius:4px"></iframe>',
            unsafe_allow_html=True,
        )
    else:
        st.download_button("Télécharger le fichier", contenu, file_name=nom_fichier)


# ---------------------------------------------------------------------------
# Bloc detail d'une facture
# ---------------------------------------------------------------------------

CHAMPS_LABELS = {
    "fournisseur":    "Fournisseur",
    "numero_facture": "Numéro de facture",
    "date":           "Date",
    "montant_ht":     "Montant HT",
    "tva":            "TVA",
    "montant_ttc":    "Montant TTC",
}

COLS_CHAMPS = ["fournisseur", "numero_facture", "date", "montant_ht", "tva", "montant_ttc"]
COLS_CONF   = ["conf_fournisseur", "conf_numero", "conf_date", "conf_ht", "conf_tva", "conf_ttc"]
COLS_SRC    = ["src_fournisseur",  "src_numero",  "src_date",  "src_ht",  "src_tva",  "src_ttc"]


def afficher_detail(f: dict) -> None:
    statut     = f.get("statut", "")
    id_facture = f["id"]
    nom        = f.get("fichier", "")

    # Pour a_verifier : image a gauche, champs a droite
    if statut == "a_verifier":
        col_img, col_champs = st.columns([1, 1])
        with col_img:
            st.markdown("**Document original**")
            afficher_fichier_original(id_facture, nom)
    else:
        col_champs = st.container()

    with col_champs:
        col1, col2 = st.columns([2, 1])

        with col1:
            st.markdown("**Champs extraits**")
            lignes = []
            for champ, conf_col, src_col in zip(COLS_CHAMPS, COLS_CONF, COLS_SRC):
                valeur = f.get(champ, "—") or "—"
                conf   = f.get(conf_col)
                src    = f.get(src_col, "")
                couleur = couleur_confiance(conf)
                lignes.append({
                    "Champ":     CHAMPS_LABELS[champ],
                    "Valeur":    str(valeur),
                    "Confiance": f"{conf:.2f}" if conf is not None else "—",
                    "Source":    src or "—",
                })
            st.table(lignes)

        with col2:
            st.markdown("**Controles métier**")
            st.write(f"Arithmétique : {icone_bool(bool(f.get('ctrl_arithmetique')))}")
            st.write(f"Date valide  : {icone_bool(bool(f.get('ctrl_date_valide')))}")
            st.write(f"Doublon      : {'OUI' if f.get('ctrl_doublon') else 'non'}")
            st.markdown("---")
            st.write(f"Confiance OCR : **{f.get('conf_ocr', 0):.2f}**")
            st.write(f"Divergences   : {f.get('nb_divergences', 0)}")

        # Formulaire de correction (uniquement pour a_verifier)
        if statut == "a_verifier":
            with st.expander("Corriger un champ avant validation"):
                with st.form(key=f"form_corr_{id_facture}"):
                    champ_a_corriger = st.selectbox(
                        "Champ à corriger",
                        options=COLS_CHAMPS,
                        format_func=lambda c: CHAMPS_LABELS[c],
                        key=f"sel_{id_facture}",
                    )
                    valeur_actuelle = f.get(champ_a_corriger, "")
                    nouvelle_valeur = st.text_input(
                        "Nouvelle valeur",
                        value=str(valeur_actuelle) if valeur_actuelle else "",
                        key=f"val_{id_facture}",
                    )
                    if st.form_submit_button("Appliquer la correction"):
                        # Conversion numérique si nécessaire
                        val_finale = nouvelle_valeur
                        if champ_a_corriger in ("montant_ht", "tva", "montant_ttc"):
                            try:
                                val_finale = float(nouvelle_valeur.replace(",", "."))
                            except ValueError:
                                st.error("Valeur numérique invalide.")
                                st.stop()
                        if corriger_facture(id_facture, {champ_a_corriger: val_finale}):
                            st.success(f"{CHAMPS_LABELS[champ_a_corriger]} corrigé.")
                            st.rerun()
                        else:
                            st.error("Échec de la correction.")

        # Boutons Valider / Rejeter
        if statut in ("prete", "a_verifier"):
            st.markdown("---")
            c1, c2, _ = st.columns([1, 1, 3])
            with c1:
                if st.button("Valider", key=f"btn_val_{id_facture}", type="primary"):
                    if action_facture(id_facture, "valider"):
                        st.success("Facture validée.")
                        st.rerun()
                    else:
                        st.error("Échec de la validation.")
            with c2:
                if st.button("Rejeter", key=f"btn_rej_{id_facture}"):
                    if action_facture(id_facture, "rejeter"):
                        st.warning("Facture rejetée.")
                        st.rerun()
                    else:
                        st.error("Échec du rejet.")


# ---------------------------------------------------------------------------
# Tableau de bord
# ---------------------------------------------------------------------------

def afficher_tableau_de_bord(toutes: list[dict]) -> None:
    compteurs = {}
    for f in toutes:
        s = f.get("statut", "inconnu")
        compteurs[s] = compteurs.get(s, 0) + 1

    ordre = ["prete", "a_verifier", "validee", "rejetee", "doublon", "recue"]
    cols  = st.columns(len(ordre))
    for col, statut in zip(cols, ordre):
        n = compteurs.get(statut, 0)
        _, libelle = COULEUR_STATUT.get(statut, ("#888", statut))
        col.metric(libelle, n)


# ---------------------------------------------------------------------------
# Helpers d'envoi : n8n (chemin principal) et API directe (secours)
# ---------------------------------------------------------------------------

def envoyer_via_n8n(nom_fichier: str) -> tuple[str | None, str, str]:
    """Envoie le chemin du fichier au webhook n8n.

    Retourne (statut, source, message_erreur).
    statut vaut None si n8n est inaccessible — déclenche le mode secours.
    """
    try:
        r = requests.post(
            N8N_WEBHOOK_URL,
            json={
                "filename": nom_fichier,
                "chemin":   f"/data/factures/entrant/{nom_fichier}",
            },
            timeout=120,
        )
        if r.status_code in (200, 201):
            data = r.json()
            return data.get("statut", "?"), "n8n", ""
        return None, "—", f"n8n a répondu {r.status_code} : {r.text[:200]}"
    except requests.exceptions.ConnectionError:
        return None, "—", ""   # n8n hors ligne → mode secours
    except Exception as e:
        return None, "—", str(e)


def envoyer_via_api(nom_fichier: str, contenu: bytes) -> tuple[str | None, str, str]:
    """Mode secours : envoi multipart direct à l'API FastAPI.

    Utilisé uniquement si n8n est indisponible.
    Retourne (statut, source, message_erreur).
    """
    try:
        r = requests.post(
            f"{API_URL}/factures/",
            files={"fichier": (nom_fichier, contenu)},
            timeout=120,
        )
        if r.status_code in (200, 201):
            data = r.json()
            return data.get("statut", "?"), "api_direct", ""
        return "erreur", "api_direct", f"Erreur API ({r.status_code}) : {r.text[:200]}"
    except Exception as e:
        return "erreur", "api_direct", str(e)


# ---------------------------------------------------------------------------
# Section upload (jusqu'à 10 fichiers, barre de progression, mode secours)
# ---------------------------------------------------------------------------

def section_upload() -> None:
    st.markdown("### Déposer des factures")
    st.caption(
        "Jusqu'à 10 fichiers PDF ou images. "
        "Chaque fichier est envoyé au webhook n8n — "
        "si n8n est indisponible, le traitement passe directement par l'API."
    )

    fichiers = st.file_uploader(
        "Sélectionner des fichiers PDF ou images",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="upload_factures",
    )

    if fichiers:
        if len(fichiers) > 10:
            st.warning(f"{len(fichiers)} fichiers sélectionnés — seuls les 10 premiers seront traités.")
            fichiers = fichiers[:10]

        st.caption(f"{len(fichiers)} fichier(s) sélectionné(s).")

        if st.button("Envoyer pour traitement", type="primary"):
            entrant_dir = Path("donnees/entrant")
            entrant_dir.mkdir(parents=True, exist_ok=True)

            barre     = st.progress(0, text="Préparation...")
            resultats = []

            for i, fichier in enumerate(fichiers):
                barre.progress(i / len(fichiers), text=f"Envoi {i + 1}/{len(fichiers)} : {fichier.name}")

                contenu = fichier.getvalue()
                (entrant_dir / fichier.name).write_bytes(contenu)

                statut, source, erreur = envoyer_via_n8n(fichier.name)
                if statut is None:
                    statut, source, erreur = envoyer_via_api(fichier.name, contenu)

                resultats.append({
                    "fichier": fichier.name,
                    "statut":  statut or "erreur",
                    "source":  source,
                    "erreur":  erreur,
                })

            barre.progress(1.0, text=f"Terminé — {len(resultats)} fichier(s) traité(s).")

            nb_ok  = sum(1 for r in resultats if not r["erreur"])
            nb_err = len(resultats) - nb_ok
            st.write(f"**{nb_ok} réussi(s), {nb_err} erreur(s)**")

            for r in resultats:
                _, libelle = COULEUR_STATUT.get(r["statut"], ("#888", r["statut"]))
                if r["erreur"]:
                    st.error(f"{r['fichier']} — {r['erreur']}")
                elif r["source"] == "api_direct":
                    st.warning(f"{r['fichier']} — {libelle}  (n8n indisponible, traitement direct)")
                else:
                    st.success(f"{r['fichier']} — {libelle}")

            if nb_ok > 0:
                st.rerun()

    st.markdown("---")


# ---------------------------------------------------------------------------
# Page : file d'attente
# ---------------------------------------------------------------------------

def page_file_attente() -> None:
    section_upload()

    prete      = get_factures("prete")
    a_verifier = get_factures("a_verifier")
    doublons   = get_factures("doublon")

    if not prete and not a_verifier and not doublons:
        st.info("Aucune facture en attente.")
        return

    if prete:
        st.subheader(f"Prêtes à valider ({len(prete)})")
        for f in prete:
            with st.expander(
                f"[{f['id']}] {f.get('fichier','?')}  —  "
                f"{f.get('fournisseur','?')}  |  {f.get('numero_facture','?')}  |  "
                f"{f.get('date','?')}  |  TTC {f.get('montant_ttc','?')} EUR"
            ):
                afficher_detail(f)

    if a_verifier:
        st.subheader(f"À vérifier ({len(a_verifier)})")
        st.caption("Divergence, contrôle échoué ou OCR de faible qualité.")
        for f in a_verifier:
            with st.expander(
                f"[{f['id']}] {f.get('fichier','?')}  —  "
                f"{f.get('fournisseur','?')}  |  {f.get('numero_facture','?')}"
            ):
                afficher_detail(f)

    if doublons:
        st.subheader(f"Doublons détectés ({len(doublons)})")
        st.caption("Refusés automatiquement (même empreinte ou même référence).")
        for f in doublons:
            st.write(
                f"[{f['id']}] {f.get('fichier','?')} — "
                f"{f.get('fournisseur','?')} / {f.get('numero_facture','?')}"
            )


# ---------------------------------------------------------------------------
# Page : historique
# ---------------------------------------------------------------------------

def page_historique() -> None:
    st.header("Historique")

    statuts = ["(tous)", "validee", "rejetee", "prete", "a_verifier", "doublon", "recue"]
    choix   = st.selectbox("Filtrer par statut", statuts)
    filtre  = None if choix == "(tous)" else choix

    factures = get_factures(filtre)
    if not factures:
        st.info("Aucune facture trouvée.")
        return

    lignes = []
    for f in factures:
        lignes.append({
            "ID":          f["id"],
            "Fichier":     f.get("fichier", ""),
            "Statut":      f.get("statut", ""),
            "Fournisseur": f.get("fournisseur", ""),
            "Numéro":      f.get("numero_facture", ""),
            "Date":        f.get("date", ""),
            "TTC (EUR)":   f.get("montant_ttc", ""),
            "Conf. OCR":   f"{f.get('conf_ocr', 0):.2f}" if f.get("conf_ocr") is not None else "—",
        })
    st.dataframe(lignes, use_container_width=True)


# ---------------------------------------------------------------------------
# Navigation principale
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("Traitement automatisé des factures")

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
