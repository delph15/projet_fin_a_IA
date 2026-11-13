"""
Test du jour 0 — Projet 2 : Automatisation intelligente du traitement des factures

Ce script vérifie que l'ordinateur est prêt pour le projet :
  1. configuration de la machine (système, processeur, RAM)
  2. version de Python
  3. Docker installé
  4. Tesseract installé, avec le pack de langue français (fra)
  5. Ollama joignable et modèles téléchargés
  6. temps de réponse du LLM sur une extraction de facture réelle

Utilisation :
    python test_jour0.py
    python test_jour0.py --modele qwen2.5:7b
    python test_jour0.py --modele qwen2.5:3b --cpu   (processeur uniquement)

Aucune bibliothèque à installer : uniquement la bibliothèque standard de Python.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434"

FACTURE_EXEMPLE = """
SARL Informatique Plus
12 rue des Lilas, 75011 Paris
SIRET 123 456 789 00012

FACTURE N° FAC-2026-0147
Date : 14/10/2026

Client : Boulangerie Martin

Désignation                     Qté   Prix unitaire   Total
Maintenance serveur              1        450,00      450,00
Licence antivirus (12 mois)      3         35,00      105,00

Total HT                                              555,00 €
TVA 20 %                                              111,00 €
Total TTC                                             666,00 €
"""

RESULTAT_ATTENDU = {
    "fournisseur": "SARL Informatique Plus",
    "numero_facture": "FAC-2026-0147",
    "date": "2026-10-14",
    "montant_ht": 555.00,
    "tva": 111.00,
    "montant_ttc": 666.00,
}

PROMPT = """Tu es un assistant qui extrait les informations d'une facture.
Réponds UNIQUEMENT avec un objet JSON contenant exactement ces clés :
"fournisseur", "numero_facture", "date" (format AAAA-MM-JJ),
"montant_ht", "tva", "montant_ttc" (nombres, point décimal).
Si une information est absente du texte, mets null. N'invente rien.

Texte de la facture :
{texte}
"""

resultats = []


def afficher_titre(titre):
    print()
    print("=" * 60)
    print(titre)
    print("=" * 60)


def noter(etape, ok, detail):
    symbole = "OK " if ok else "KO "
    print(f"[{symbole}] {etape} : {detail}")
    resultats.append((etape, ok, detail))


def ram_totale_go():
    """Retourne la RAM totale en Go, selon le système d'exploitation."""
    systeme = platform.system()
    try:
        if systeme == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            etat = MEMORYSTATUSEX()
            etat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(etat))
            return etat.ullTotalPhys / (1024 ** 3)
        if systeme == "Linux":
            with open("/proc/meminfo", encoding="utf-8") as f:
                for ligne in f:
                    if ligne.startswith("MemTotal"):
                        return int(ligne.split()[1]) / (1024 ** 2)
        if systeme == "Darwin":
            sortie = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            return int(sortie.strip()) / (1024 ** 3)
    except Exception:
        return None
    return None


def etape_machine():
    afficher_titre("1. Configuration de la machine")
    print(f"Système      : {platform.system()} {platform.release()}")
    print(f"Processeur   : {platform.processor() or platform.machine()}")
    print(f"Cœurs        : {os.cpu_count()}")
    ram = ram_totale_go()
    if ram is None:
        noter("RAM", False, "impossible de lire la RAM, vérifie-la à la main")
        return
    if ram >= 15:
        noter("RAM", True, f"{ram:.1f} Go : modèle 7B possible (qwen2.5:7b)")
    elif ram >= 7.5:
        noter("RAM", True, f"{ram:.1f} Go : utiliser un modèle 3B (qwen2.5:3b)")
    else:
        noter("RAM", False, f"{ram:.1f} Go : insuffisant, prévoir gemma2:2b et fermer les autres applications")


def etape_python():
    afficher_titre("2. Python")
    version = sys.version_info
    texte = f"{version.major}.{version.minor}.{version.micro}"
    noter("Python", version >= (3, 11), f"version {texte} (3.11 ou plus récent conseillé)")


def etape_docker():
    afficher_titre("3. Docker")
    if shutil.which("docker") is None:
        noter("Docker", False, "commande 'docker' introuvable : installer Docker Desktop")
        return
    try:
        sortie = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=30)
        if sortie.returncode == 0:
            noter("Docker", True, "installé et démarré")
        else:
            noter("Docker", False, "installé mais pas démarré : lancer Docker Desktop")
    except Exception as erreur:
        noter("Docker", False, f"erreur : {erreur}")


def trouver_tesseract():
    chemin = shutil.which("tesseract")
    if chemin:
        return chemin
    candidat = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(candidat):
        return candidat
    return None


def etape_tesseract():
    afficher_titre("4. Tesseract (OCR)")
    chemin = trouver_tesseract()
    if chemin is None:
        noter("Tesseract", False, "introuvable : l'installer et l'ajouter au PATH")
        return
    try:
        version = subprocess.run([chemin, "--version"], capture_output=True, text=True, timeout=30)
        premiere_ligne = (version.stdout or version.stderr).splitlines()[0]
        noter("Tesseract", True, premiere_ligne)
        langues = subprocess.run([chemin, "--list-langs"], capture_output=True, text=True, timeout=30)
        liste = (langues.stdout + langues.stderr).split()
        if "fra" in liste:
            noter("Langue française", True, "pack 'fra' présent")
        else:
            noter("Langue française", False, "pack 'fra' absent : le cocher à l'installation de Tesseract")
    except Exception as erreur:
        noter("Tesseract", False, f"erreur : {erreur}")


def appel_ollama(chemin, donnees=None, delai=300):
    url = OLLAMA_URL + chemin
    if donnees is None:
        requete = urllib.request.Request(url)
    else:
        corps = json.dumps(donnees).encode("utf-8")
        requete = urllib.request.Request(url, data=corps, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(requete, timeout=delai) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def etape_ollama(modele):
    afficher_titre("5. Ollama")
    try:
        modeles = appel_ollama("/api/tags", delai=10).get("models", [])
    except (urllib.error.URLError, OSError):
        noter("Ollama", False, f"injoignable sur {OLLAMA_URL} : lancer l'application Ollama")
        return False
    noms = [m.get("name", "") for m in modeles]
    noter("Ollama", True, "joignable")
    print(f"Modèles présents : {', '.join(noms) if noms else 'aucun'}")
    if modele not in noms:
        noter("Modèle", False, f"{modele} absent : lancer 'ollama pull {modele}'")
        return False
    noter("Modèle", True, f"{modele} téléchargé")
    return True


def comparer(extrait):
    corrects = 0
    for cle, attendu in RESULTAT_ATTENDU.items():
        valeur = extrait.get(cle)
        if isinstance(attendu, float):
            try:
                ok = abs(float(valeur) - attendu) < 0.01
            except (TypeError, ValueError):
                ok = False
        else:
            ok = str(valeur).strip().lower() == attendu.lower()
        corrects += ok
        print(f"   {'✓' if ok else '✗'} {cle:<15} obtenu = {valeur!r:<28} attendu = {attendu!r}")
    return corrects


def etape_llm(modele, cpu_seul=False):
    mode = "processeur uniquement" if cpu_seul else "réglage automatique"
    afficher_titre(f"6. Test d'extraction avec {modele} ({mode})")
    options = {"temperature": 0}
    if cpu_seul:
        options["num_gpu"] = 0
    donnees = {
        "model": modele,
        "prompt": PROMPT.format(texte=FACTURE_EXEMPLE),
        "format": "json",
        "stream": False,
        "options": options,
    }
    print("Premier appel (chargement du modèle en mémoire, plus lent)...")
    try:
        debut = time.perf_counter()
        appel_ollama("/api/generate", donnees)
        duree_froid = time.perf_counter() - debut
        print(f"   durée à froid : {duree_froid:.1f} s")

        print("Deuxième appel (modèle déjà chargé, durée représentative)...")
        debut = time.perf_counter()
        reponse = appel_ollama("/api/generate", donnees)
        duree = time.perf_counter() - debut
    except urllib.error.HTTPError as erreur:
        try:
            message = erreur.read().decode("utf-8", errors="replace")
        except Exception:
            message = ""
        noter("Extraction LLM", False, f"erreur HTTP {erreur.code}")
        print()
        print("Message renvoyé par Ollama (à m'envoyer) :")
        print(f"   {message.strip() or '(vide)'}")
        return
    except Exception as erreur:
        noter("Extraction LLM", False, f"erreur : {erreur}")
        return

    try:
        extrait = json.loads(reponse.get("response", "{}"))
    except json.JSONDecodeError:
        noter("Extraction LLM", False, "la réponse n'est pas un JSON valide")
        print(reponse.get("response"))
        return

    print()
    corrects = comparer(extrait)
    noter("Extraction LLM", corrects == 6, f"{corrects}/6 champs corrects")
    if duree <= 15:
        avis = "très bien"
    elif duree <= 30:
        avis = "acceptable (cible du cahier des charges : moins de 30 s)"
    else:
        avis = "trop lent : essayer un modèle plus petit"
    noter("Temps de réponse", duree <= 30, f"{duree:.1f} s par facture, {avis}")


def bilan():
    afficher_titre("BILAN — à copier et envoyer")
    print(f"Système : {platform.system()} {platform.release()} | Python {platform.python_version()}")
    ram = ram_totale_go()
    if ram is not None:
        print(f"RAM : {ram:.1f} Go | Cœurs : {os.cpu_count()}")
    for etape, ok, detail in resultats:
        print(f"[{'OK' if ok else 'KO'}] {etape} : {detail}")
    echecs = [r for r in resultats if not r[1]]
    print()
    if echecs:
        print(f"{len(echecs)} point(s) à corriger avant de commencer.")
    else:
        print("Tout est prêt : le jour 0 est validé.")


def main():
    analyseur = argparse.ArgumentParser(description="Test du jour 0 du Projet 2")
    analyseur.add_argument("--modele", default="qwen2.5:3b", help="modèle Ollama à tester")
    analyseur.add_argument("--cpu", action="store_true", help="forcer Ollama à n'utiliser que le processeur")
    arguments = analyseur.parse_args()

    etape_machine()
    etape_python()
    etape_docker()
    etape_tesseract()
    if etape_ollama(arguments.modele):
        etape_llm(arguments.modele, arguments.cpu)
    bilan()


if __name__ == "__main__":
    main()