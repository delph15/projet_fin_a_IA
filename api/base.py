# base.py - acces SQLite : creation des tables, insertion, lecture, mise a jour
#
# Schema unique : table "factures"
# Pas d'ORM : sqlite3 standard suffit pour ce MVP.

import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

_DB_PATH = os.getenv("DB_PATH", "donnees/factures.db")


# ---------------------------------------------------------------------------
# Connexion et initialisation
# ---------------------------------------------------------------------------

def obtenir_connexion(chemin: str = _DB_PATH) -> sqlite3.Connection:
    """Ouvre (ou cree) la base de donnees et retourne la connexion."""
    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row  # acces par nom de colonne
    return conn


def initialiser_base(conn: sqlite3.Connection) -> None:
    """Cree la table factures si elle n'existe pas encore."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS factures (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            fichier          TEXT    NOT NULL,
            empreinte        TEXT,
            statut           TEXT    NOT NULL DEFAULT 'recue',
            source           TEXT    NOT NULL DEFAULT 'interface',

            -- Champs extraits
            fournisseur      TEXT,
            numero_facture   TEXT,
            date             TEXT,
            montant_ht       REAL,
            tva              REAL,
            montant_ttc      REAL,

            -- Confiances (arrondies a 3 decimales)
            conf_fournisseur REAL,
            conf_numero      REAL,
            conf_date        REAL,
            conf_ht          REAL,
            conf_tva         REAL,
            conf_ttc         REAL,

            -- Sources (regex / llm / accord)
            src_fournisseur  TEXT,
            src_numero       TEXT,
            src_date         TEXT,
            src_ht           TEXT,
            src_tva          TEXT,
            src_ttc          TEXT,

            -- Controles metier
            ctrl_arithmetique INTEGER,  -- 0 ou 1
            ctrl_date_valide  INTEGER,
            ctrl_doublon      INTEGER,

            -- Meta
            conf_ocr         REAL,
            nb_divergences   INTEGER,

            -- Fichier original conserve
            chemin_original  TEXT,

            -- Horodatage
            cree_le          TEXT DEFAULT (datetime('now')),
            mis_a_jour_le    TEXT DEFAULT (datetime('now'))
        )
    """)
    # Migration : ajouter chemin_original si la base existait avant
    try:
        conn.execute("ALTER TABLE factures ADD COLUMN chemin_original TEXT")
    except Exception:
        pass
    colonnes = {
        ligne["name"]
        for ligne in conn.execute("PRAGMA table_info(factures)").fetchall()
    }
    if "source" not in colonnes:
        conn.execute(
            "ALTER TABLE factures ADD COLUMN source TEXT NOT NULL DEFAULT 'interface'"
        )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications_email (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            cle_email             TEXT    NOT NULL,
            sujet                 TEXT    NOT NULL,
            nb_fichiers_recus     INTEGER NOT NULL,
            nb_fichiers_traites   INTEGER NOT NULL,
            fichiers_json         TEXT    NOT NULL,
            cree_le               TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Insertion
# ---------------------------------------------------------------------------

def inserer_facture(conn: sqlite3.Connection, facture: dict) -> int:
    """
    Insere une facture dans la base et retourne son id.

    Parametre
    ---------
    facture : dict construit par assembler_facture() dans main.py
    """
    champs = facture.get("champs", {})
    ctrl   = facture.get("controles", {})
    meta   = champs.get("meta", {})

    def v(cle):
        return champs.get(cle, {}).get("valeur")

    def c(cle):
        return champs.get(cle, {}).get("confiance")

    def s(cle):
        return champs.get(cle, {}).get("source")

    cur = conn.execute("""
        INSERT INTO factures (
            fichier, empreinte, statut, source, chemin_original,
            fournisseur, numero_facture, date, montant_ht, tva, montant_ttc,
            conf_fournisseur, conf_numero, conf_date, conf_ht, conf_tva, conf_ttc,
            src_fournisseur, src_numero, src_date, src_ht, src_tva, src_ttc,
            ctrl_arithmetique, ctrl_date_valide, ctrl_doublon,
            conf_ocr, nb_divergences
        ) VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?
        )
    """, (
        facture.get("fichier"), facture.get("empreinte"), facture.get("statut"),
        facture.get("source", "interface"),
        facture.get("chemin_original"),
        v("fournisseur"), v("numero_facture"), v("date"),
        v("montant_ht"), v("tva"), v("montant_ttc"),
        c("fournisseur"), c("numero_facture"), c("date"),
        c("montant_ht"), c("tva"), c("montant_ttc"),
        s("fournisseur"), s("numero_facture"), s("date"),
        s("montant_ht"), s("tva"), s("montant_ttc"),
        int(ctrl.get("arithmetique", False)),
        int(ctrl.get("date_valide",  False)),
        int(ctrl.get("doublon",      False)),
        meta.get("confiance_ocr", 0.0),
        meta.get("nb_divergences", 0),
    ))
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

def lister_factures(conn: sqlite3.Connection, statut: Optional[str] = None) -> list[dict]:
    """
    Retourne toutes les factures, ou seulement celles d'un statut donne.
    Chaque element est un dict (grace a row_factory = sqlite3.Row).
    """
    if statut:
        rows = conn.execute(
            "SELECT * FROM factures WHERE statut = ? ORDER BY cree_le DESC",
            (statut,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM factures ORDER BY cree_le DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def obtenir_facture(conn: sqlite3.Connection, id_facture: int) -> Optional[dict]:
    """Retourne une facture par son id, ou None si introuvable."""
    row = conn.execute(
        "SELECT * FROM factures WHERE id = ?", (id_facture,)
    ).fetchone()
    return dict(row) if row else None


def enregistrer_notification_email(conn: sqlite3.Connection, notification: dict) -> int:
    """Enregistre le bilan d'un courriel traité par n8n."""
    fichiers = notification["fichiers"]
    nb_fichiers_traites = sum(
        fichier.get("id_facture") is not None for fichier in fichiers
    )
    curseur = conn.execute(
        """
        INSERT INTO notifications_email (
            cle_email, sujet, nb_fichiers_recus, nb_fichiers_traites, fichiers_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            notification["cle_email"],
            notification["sujet"],
            notification["nb_fichiers_recus"],
            nb_fichiers_traites,
            json.dumps(fichiers, ensure_ascii=False),
        ),
    )
    conn.commit()
    return curseur.lastrowid


def lister_notifications_email(conn: sqlite3.Connection, limite: int = 5) -> list[dict]:
    """Retourne les notifications e-mail les plus récentes."""
    lignes = conn.execute(
        """
        SELECT id, cle_email, sujet, nb_fichiers_recus, nb_fichiers_traites,
               fichiers_json, cree_le
        FROM notifications_email
        ORDER BY id DESC
        LIMIT ?
        """,
        (limite,),
    ).fetchall()
    return [
        {
            "id": ligne["id"],
            "cle_email": ligne["cle_email"],
            "sujet": ligne["sujet"],
            "nb_fichiers_recus": ligne["nb_fichiers_recus"],
            "nb_fichiers_traites": ligne["nb_fichiers_traites"],
            "fichiers": json.loads(ligne["fichiers_json"]),
            "cree_le": ligne["cree_le"],
        }
        for ligne in lignes
    ]


# ---------------------------------------------------------------------------
# Correction manuelle des champs (action humaine)
# ---------------------------------------------------------------------------

_COLONNES_CHAMPS = {
    "fournisseur":    ("fournisseur",    "conf_fournisseur", "src_fournisseur"),
    "numero_facture": ("numero_facture", "conf_numero",      "src_numero"),
    "date":           ("date",           "conf_date",        "src_date"),
    "montant_ht":     ("montant_ht",     "conf_ht",          "src_ht"),
    "tva":            ("tva",            "conf_tva",         "src_tva"),
    "montant_ttc":    ("montant_ttc",    "conf_ttc",         "src_ttc"),
}


def corriger_champs(
    conn: sqlite3.Connection,
    id_facture: int,
    corrections: dict,
) -> bool:
    """
    Applique les corrections humaines sur les champs d'une facture.
    Chaque champ corrige recoit confiance=1.0 et source="humain".
    Retourne True si au moins une ligne a ete modifiee.
    """
    sets, params = [], []
    for champ, valeur in corrections.items():
        if champ not in _COLONNES_CHAMPS:
            continue
        col_val, col_conf, col_src = _COLONNES_CHAMPS[champ]
        sets  += [f"{col_val} = ?", f"{col_conf} = 1.0", f"{col_src} = 'humain'"]
        params.append(valeur)

    if not sets:
        return False

    params += [id_facture]
    sql = f"UPDATE factures SET {', '.join(sets)}, mis_a_jour_le = datetime('now') WHERE id = ?"
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Mise a jour du statut (action humaine)
# ---------------------------------------------------------------------------

def mettre_a_jour_statut(
    conn: sqlite3.Connection,
    id_facture: int,
    nouveau_statut: str,
) -> bool:
    """
    Change le statut d'une facture.
    Retourne True si une ligne a ete modifiee, False si l'id n'existe pas.

    Regles metier :
      - "validee" et "rejetee" ne sont accessibles que depuis "prete" ou "a_verifier"
      - On ne peut pas revalider une facture deja "validee" ou "rejetee"
    """
    statuts_valides = {"recue", "extraite", "a_verifier", "prete", "validee", "rejetee", "doublon"}
    if nouveau_statut not in statuts_valides:
        return False

    cur = conn.execute(
        """
        UPDATE factures
        SET statut = ?, mis_a_jour_le = datetime('now')
        WHERE id = ? AND statut NOT IN ('validee', 'rejetee')
        """,
        (nouveau_statut, id_facture),
    )
    conn.commit()
    return cur.rowcount > 0
