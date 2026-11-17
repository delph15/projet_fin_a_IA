import sys
import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

import main
from base import (
    initialiser_base,
    inserer_facture,
    obtenir_connexion,
)


@pytest.fixture
def base_temporaire(tmp_path):
    chemin = tmp_path / "factures.db"
    conn = obtenir_connexion(str(chemin))
    initialiser_base(conn)
    conn.close()
    return chemin


def test_migration_ajoute_source_a_une_base_existante(tmp_path):
    conn = sqlite3.connect(tmp_path / "ancienne.db")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE factures (id INTEGER PRIMARY KEY, fichier TEXT NOT NULL, "
        "empreinte TEXT, statut TEXT NOT NULL DEFAULT 'recue')"
    )
    conn.execute(
        "INSERT INTO factures (fichier, statut) VALUES ('ancienne.pdf', 'prete')"
    )

    initialiser_base(conn)

    ligne = conn.execute("SELECT source FROM factures").fetchone()
    assert ligne["source"] == "interface"
    conn.close()


def test_enregistrer_facture_conserve_sa_source(base_temporaire):
    conn = obtenir_connexion(str(base_temporaire))
    id_facture = inserer_facture(
        conn,
        {
            "fichier": "facture.pdf",
            "empreinte": "abc",
            "statut": "prete",
            "source": "email",
            "champs": {},
            "controles": {},
        },
    )

    ligne = conn.execute(
        "SELECT source FROM factures WHERE id = ?", (id_facture,)
    ).fetchone()
    assert ligne["source"] == "email"
    conn.close()


def test_notification_email_persiste_le_nombre_et_les_resultats(base_temporaire, monkeypatch):
    donnees = {
        "cle_email": "message-123",
        "sujet": "Factures de juin",
        "nb_fichiers_recus": 2,
        "fichiers": [
            {
                "fichier": "facture-a.pdf",
                "statut": "prete",
                "id_facture": 10,
                "erreur": None,
            },
            {
                "fichier": "facture-b.docx",
                "statut": "erreur",
                "id_facture": None,
                "erreur": "Format non supporte",
            },
        ],
    }

    monkeypatch.setattr(
        main,
        "obtenir_connexion",
        lambda: obtenir_connexion(str(base_temporaire)),
    )
    id_notification = main.creer_notification_email(
        main.NotificationEmail(**donnees)
    )["id"]
    lignes = main.lister_notifications_email(limite=5)
    assert id_notification == lignes[0]["id"]
    assert lignes[0]["nb_fichiers_recus"] == 2
    assert lignes[0]["nb_fichiers_traites"] == 1
    assert lignes[0]["fichiers"] == donnees["fichiers"]
    assert lignes[0]["sujet"] == "Factures de juin"


def test_route_notification_verifie_le_nombre_de_fichiers(base_temporaire, monkeypatch):
    monkeypatch.setattr(
        main,
        "obtenir_connexion",
        lambda: obtenir_connexion(str(base_temporaire)),
    )
    notification = main.NotificationEmail(
        cle_email="message-456",
        sujet="Facture",
        nb_fichiers_recus=2,
        fichiers=[
            main.ResultatFichierEmail(
                fichier="facture.pdf",
                statut="prete",
                id_facture=11,
            )
        ],
    )

    with pytest.raises(HTTPException) as erreur:
        main.creer_notification_email(notification)

    assert erreur.value.status_code == 400
