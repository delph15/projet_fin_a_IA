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
# Constantes d'affichage
# ---------------------------------------------------------------------------

COULEUR_STATUT = {
    "recue":      ("#888888", "Reçue"),
    "extraite":   ("#4a90d9", "Extraite"),
    "a_verifier": ("#e67e22", "À vérifier"),
    "prete":      ("#27ae60", "Prête"),
    "validee":    ("#1abc9c", "Validée"),
    "rejetee":    ("#e74c3c", "Rejetée"),
    "doublon":    ("#9b59b6", "Doublon"),
}

SOURCE_LABELS = {
    "regex":  "Regex",
    "llm":    "IA",
    "humain": "Corrigé manuellement",
}

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

FILTRE_LABELS = {
    "(tous)":     "(tous)",
    "validee":    "Validée",
    "rejetee":    "Rejetée",
    "prete":      "Prête",
    "a_verifier": "À vérifier",
    "doublon":    "Doublon",
    "recue":      "Reçue",
}


# ---------------------------------------------------------------------------
# Utilitaires d'affichage
# ---------------------------------------------------------------------------

def couleur_confiance(conf) -> str:
    if conf is None:
        return "#888888"
    if conf >= 0.90:
        return "#27ae60"
    if conf >= 0.70:
        return "#e67e22"
    return "#e74c3c"


def badge_statut(statut: str) -> str:
    couleur, libelle = COULEUR_STATUT.get(statut, ("#888888", statut))
    return (
        f'<span style="background:{couleur};color:white;padding:2px 10px;'
        f'border-radius:12px;font-size:0.8em;font-weight:600">{libelle}</span>'
    )


def badge_confiance(conf) -> str:
    if conf is None:
        return "—"
    pct     = int(conf * 100)
    couleur = couleur_confiance(conf)
    return f'<span style="color:{couleur};font-weight:600">{pct} %</span>'


def verifier_api() -> bool:
    try:
        r = requests.get(f"{API_URL}/factures/", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


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
# Bloc détail d'une facture
# ---------------------------------------------------------------------------

def afficher_champs(f: dict) -> None:
    """Champs extraits avec badges de confiance colorés."""
    lignes_html = []
    for champ, conf_col, src_col in zip(COLS_CHAMPS, COLS_CONF, COLS_SRC):
        valeur  = f.get(champ) or "—"
        conf    = f.get(conf_col)
        src     = f.get(src_col, "")
        src_lib = SOURCE_LABELS.get(src, src or "—")
        lignes_html.append(
            "<tr>"
            f"<td style='padding:5px 8px;color:#555;font-size:0.88em'>{CHAMPS_LABELS[champ]}</td>"
            f"<td style='padding:5px 8px;font-weight:600'>{valeur}</td>"
            f"<td style='padding:5px 8px;text-align:center'>{badge_confiance(conf)}</td>"
            f"<td style='padding:5px 8px;color:#999;font-size:0.82em'>{src_lib}</td>"
            "</tr>"
        )
    html = (
        "<table style='width:100%;border-collapse:collapse'>"
        "<thead><tr style='border-bottom:1px solid #eee'>"
        "<th style='padding:4px 8px;text-align:left;color:#aaa;font-weight:500;font-size:0.82em'>Champ</th>"
        "<th style='padding:4px 8px;text-align:left;color:#aaa;font-weight:500;font-size:0.82em'>Valeur</th>"
        "<th style='padding:4px 8px;text-align:center;color:#aaa;font-weight:500;font-size:0.82em'>Confiance</th>"
        "<th style='padding:4px 8px;text-align:left;color:#aaa;font-weight:500;font-size:0.82em'>Source</th>"
        "</tr></thead>"
        "<tbody>" + "".join(lignes_html) + "</tbody>"
        "</table>"
    )
    st.markdown(html, unsafe_allow_html=True)


def afficher_controles(f: dict) -> None:
    """Contrôles métier avec indicateurs colorés."""
    arith   = bool(f.get("ctrl_arithmetique"))
    date_ok = bool(f.get("ctrl_date_valide"))
    doublon = bool(f.get("ctrl_doublon"))

    def indicateur(ok: bool, label_ok: str, label_ko: str) -> str:
        if ok:
            return f'<div style="color:#27ae60;margin:3px 0">● {label_ok}</div>'
        return f'<div style="color:#e74c3c;margin:3px 0">● {label_ko}</div>'

    html = (
        indicateur(arith,   "HT + TVA = TTC valide", "HT + TVA ≠ TTC")
        + indicateur(date_ok, "Date valide",            "Date invalide")
    )
    if doublon:
        html += '<div style="color:#9b59b6;margin:3px 0">● Doublon détecté</div>'

    conf_ocr = f.get("conf_ocr") or 0
    nb_div   = f.get("nb_divergences") or 0
    html += f"<div style='margin-top:8px'>Confiance OCR : {badge_confiance(conf_ocr)}</div>"
    if nb_div > 0:
        html += f'<div style="color:#e67e22;margin-top:4px">⚠ {nb_div} divergence(s) regex / IA</div>'

    st.markdown(html, unsafe_allow_html=True)


def afficher_detail(f: dict) -> None:
    statut     = f.get("statut", "")
    id_facture = f["id"]
    nom        = f.get("fichier", "")

    if statut == "a_verifier":
        col_img, col_droite = st.columns([1, 1])
        with col_img:
            st.caption("Document original")
            afficher_fichier_original(id_facture, nom)
    else:
        col_droite = st.container()

    with col_droite:
        col_champs, col_ctrl = st.columns([3, 2])
        with col_champs:
            st.caption("Champs extraits")
            afficher_champs(f)
        with col_ctrl:
            st.caption("Contrôles métier")
            afficher_controles(f)

        # Correction directement visible pour a_verifier
        if statut == "a_verifier":
            st.markdown("---")
            st.caption("Corriger un champ")
            with st.form(key=f"form_corr_{id_facture}"):
                col_sel, col_val = st.columns([1, 2])
                with col_sel:
                    champ_a_corriger = st.selectbox(
                        "Champ",
                        options=COLS_CHAMPS,
                        format_func=lambda c: CHAMPS_LABELS[c],
                        key=f"sel_{id_facture}",
                        label_visibility="collapsed",
                    )
                with col_val:
                    valeur_actuelle = f.get(champ_a_corriger, "")
                    nouvelle_valeur = st.text_input(
                        "Nouvelle valeur",
                        value=str(valeur_actuelle) if valeur_actuelle else "",
                        key=f"val_{id_facture}",
                        label_visibility="collapsed",
                        placeholder="Nouvelle valeur...",
                    )
                if st.form_submit_button("Appliquer"):
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
            c1, c2, _ = st.columns([1, 1, 4])
            with c1:
                if st.button("Valider", key=f"btn_val_{id_facture}", type="primary"):
                    if action_facture(id_facture, "valider"):
                        st.session_state[f"msg_{id_facture}"] = ("success", "Facture validée.")
                        st.rerun()
                    else:
                        st.error("Échec de la validation.")
            with c2:
                if st.button("Rejeter", key=f"btn_rej_{id_facture}"):
                    if action_facture(id_facture, "rejeter"):
                        st.session_state[f"msg_{id_facture}"] = ("warning", "Facture rejetée.")
                        st.rerun()
                    else:
                        st.error("Échec du rejet.")

        # Message post-action persistant (session_state, affiché une fois puis effacé)
        cle_msg = f"msg_{id_facture}"
        if cle_msg in st.session_state:
            niveau, texte = st.session_state.pop(cle_msg)
            if niveau == "success":
                st.success(texte)
            else:
                st.warning(texte)


# ---------------------------------------------------------------------------
# Tableau de bord
# ---------------------------------------------------------------------------

def afficher_tableau_de_bord(toutes: list[dict]) -> None:
    compteurs = {}
    for f in toutes:
        s = f.get("statut", "inconnu")
        compteurs[s] = compteurs.get(s, 0) + 1

    ordre = ["a_verifier", "prete", "validee", "rejetee", "doublon", "recue"]
    cols  = st.columns(len(ordre))
    for col, statut in zip(cols, ordre):
        n                 = compteurs.get(statut, 0)
        couleur, libelle  = COULEUR_STATUT.get(statut, ("#888", statut))
        col.markdown(
            f'<div style="text-align:center;padding:8px 4px">'
            f'<div style="font-size:1.6em;font-weight:700;color:{couleur}">{n}</div>'
            f'<div style="font-size:0.8em;color:#777">{libelle}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Helpers d'envoi : n8n (chemin principal) et API directe (secours)
# ---------------------------------------------------------------------------

def envoyer_via_n8n(nom_fichier: str) -> tuple[str | None, str, str]:
    """Envoie le chemin du fichier au webhook n8n.
    Retourne (statut, source, erreur). statut=None déclenche le mode secours.
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
        return None, "—", ""
    except Exception as e:
        return None, "—", str(e)


def envoyer_via_api(nom_fichier: str, contenu: bytes) -> tuple[str | None, str, str]:
    """Mode secours : envoi multipart direct à l'API FastAPI.
    Utilisé uniquement si n8n est indisponible.
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
# Section upload
# ---------------------------------------------------------------------------

def section_upload() -> None:
    # Résultats du dernier envoi — persistent via session_state, survivent au rerun
    if st.session_state.get("upload_resultats"):
        resultats = st.session_state.upload_resultats
        nb_ok  = sum(1 for r in resultats if not r["erreur"])
        nb_err = len(resultats) - nb_ok

        if nb_err == 0:
            st.success(f"{nb_ok} facture(s) envoyée(s) avec succès.")
        elif nb_ok == 0:
            st.error(f"{nb_err} erreur(s) — aucune facture traitée.")
        else:
            st.warning(f"{nb_ok} réussite(s), {nb_err} erreur(s).")

        for r in resultats:
            _, libelle = COULEUR_STATUT.get(r["statut"], ("#888", r["statut"]))
            if r["erreur"]:
                st.caption(f"  {r['fichier']} — Erreur : {r['erreur']}")
            elif r["source"] == "api_direct":
                st.caption(f"  {r['fichier']} — {libelle}  (n8n indisponible, traitement direct)")
            else:
                st.caption(f"  {r['fichier']} — {libelle}")

        if st.button("Effacer ce résumé", key="effacer_resultats"):
            st.session_state.upload_resultats = []
            st.rerun()

        st.markdown("---")

    # Clé dynamique : changer sa valeur vide le file_uploader après traitement
    if "upload_compteur" not in st.session_state:
        st.session_state.upload_compteur = 0

    deja_envoye = bool(st.session_state.get("upload_resultats"))
    with st.expander("Déposer des factures", expanded=not deja_envoye):
        st.caption("Jusqu'à 10 fichiers PDF ou images.")

        fichiers = st.file_uploader(
            "Sélectionner des fichiers",
            type=["pdf", "png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key=f"upload_factures_{st.session_state.upload_compteur}",
            label_visibility="collapsed",
        )

        if fichiers:
            if len(fichiers) > 10:
                st.warning(f"{len(fichiers)} fichiers détectés — seuls les 10 premiers seront traités.")
                fichiers = fichiers[:10]
            st.caption(f"{len(fichiers)} fichier(s) sélectionné(s).")

            if st.button("Envoyer pour traitement", type="primary"):
                entrant_dir = Path("donnees/entrant")
                entrant_dir.mkdir(parents=True, exist_ok=True)

                barre     = st.progress(0, text="Préparation...")
                resultats = []

                for i, fichier in enumerate(fichiers):
                    barre.progress(
                        i / len(fichiers),
                        text=f"Envoi {i + 1}/{len(fichiers)} : {fichier.name}",
                    )
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

                barre.progress(1.0, text="Terminé.")
                st.session_state.upload_resultats = resultats
                st.session_state.upload_compteur += 1  # vide le file_uploader
                st.rerun()


# ---------------------------------------------------------------------------
# Page : file d'attente
# ---------------------------------------------------------------------------

def page_file_attente() -> None:
    section_upload()

    prete      = get_factures("prete")
    a_verifier = get_factures("a_verifier")
    doublons   = get_factures("doublon")

    if not prete and not a_verifier and not doublons:
        st.info("Aucune facture en attente de traitement.")
        return

    ong_verif, ong_prete, ong_doublons = st.tabs([
        f"À vérifier ({len(a_verifier)})",
        f"Prêtes à valider ({len(prete)})",
        f"Doublons ({len(doublons)})",
    ])

    with ong_verif:
        if not a_verifier:
            st.info("Aucune facture à vérifier.")
        else:
            st.caption("Divergence détectée, contrôle échoué ou OCR de faible qualité — vérification humaine requise.")
            for f in a_verifier:
                fournisseur = f.get("fournisseur") or "Fournisseur inconnu"
                ttc         = f.get("montant_ttc")
                ttc_str     = f"{ttc:,.2f} €" if ttc else "—"
                numero      = f.get("numero_facture") or "—"
                with st.expander(f"{fournisseur}  ·  {ttc_str}  ·  {numero}"):
                    afficher_detail(f)

    with ong_prete:
        if not prete:
            st.info("Aucune facture prête à valider.")
        else:
            for f in prete:
                fournisseur = f.get("fournisseur") or "Fournisseur inconnu"
                ttc         = f.get("montant_ttc")
                ttc_str     = f"{ttc:,.2f} €" if ttc else "—"
                date        = f.get("date") or "—"
                with st.expander(f"{fournisseur}  ·  {ttc_str}  ·  {date}"):
                    afficher_detail(f)

    with ong_doublons:
        if not doublons:
            st.info("Aucun doublon détecté.")
        else:
            st.caption("Rejetées automatiquement — même empreinte ou même référence qu'une facture existante.")
            for f in doublons:
                fournisseur = f.get("fournisseur") or "—"
                st.markdown(
                    f"**{fournisseur}** — {f.get('numero_facture') or '—'} "
                    f"— {f.get('fichier', '?')}",
                )


# ---------------------------------------------------------------------------
# Page : historique
# ---------------------------------------------------------------------------

def page_historique() -> None:
    st.header("Historique")

    choix = st.selectbox(
        "Filtrer par statut",
        options=list(FILTRE_LABELS.keys()),
        format_func=lambda k: FILTRE_LABELS[k],
    )
    filtre   = None if choix == "(tous)" else choix
    factures = get_factures(filtre)

    if not factures:
        st.info("Aucune facture trouvée.")
        return

    lignes = []
    for f in factures:
        _, lib_statut = COULEUR_STATUT.get(f.get("statut", ""), ("#888", f.get("statut", "")))
        conf_ocr      = f.get("conf_ocr")
        lignes.append({
            "ID":          f["id"],
            "Fichier":     f.get("fichier", ""),
            "Statut":      lib_statut,
            "Fournisseur": f.get("fournisseur", ""),
            "Numéro":      f.get("numero_facture", ""),
            "Date":        f.get("date", ""),
            "TTC (EUR)":   f.get("montant_ttc", ""),
            "Conf. OCR":   f"{int(conf_ocr * 100)} %" if conf_ocr is not None else "—",
        })
    st.dataframe(lignes, use_container_width=True)


# ---------------------------------------------------------------------------
# Navigation principale
# ---------------------------------------------------------------------------

def main() -> None:
    api_ok     = verifier_api()
    statut_api = (
        '<span style="color:#27ae60;font-size:0.85em">● API connectée</span>'
        if api_ok else
        '<span style="color:#e74c3c;font-size:0.85em">● API hors ligne</span>'
    )

    col_titre, col_statut = st.columns([5, 1])
    with col_titre:
        st.title("Traitement automatisé des factures")
    with col_statut:
        st.markdown("<div style='padding-top:18px'>" + statut_api + "</div>", unsafe_allow_html=True)

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
