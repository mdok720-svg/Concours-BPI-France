"""
data_loader.py
==============

Chargement et nettoyage des données sources de l'enquête de conjoncture
Bpifrance (donnees.xlsx + info_donnees.xlsx).

Principes :
- 1 fonction de chargement par feuille -> on isole les particularités
  de format (en-tête à 2 lignes, structure transposée pour Diff_appro,
  colonnes vides parasites, etc.).
- Toutes les séries temporelles sont retournées avec un DatetimeIndex
  (clé naturelle pour shift(1) = semestre précédent, shift(2) = an
  précédent).
- Les colonnes sont renommées en snake_case court : on aplatit dès le
  chargement pour ne pas trimballer un MultiIndex pandas dans tout le
  reste du projet.
- Les lignes "futures" (date présente mais valeurs NaN, ex. S2 2026
  qui sera remplie plus tard par Bpifrance) sont automatiquement
  retirées par les loaders. La fonction last_observed_wave() permet
  de récupérer la dernière vague effectivement renseignée.
- Le point d'entrée pratique est load_all(data_dir) qui retourne un
  objet BpifranceData (dataclass) regroupant tout.

Auteur : projet challenge Bpifrance — phase 1 (data pipeline).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Noms exacts des feuilles dans donnees.xlsx (on les centralise pour ne pas
# les hardcoder dans plusieurs fonctions, et pour pouvoir les changer en
# un seul endroit si Bpifrance renomme une feuille).
SHEET_CA_EFF = "CA Eff N"
SHEET_CARNETS = "Carnets de commande"
SHEET_DIFF_APPRO = "Diff_appro"
SHEET_CA_SECTEURS = "CA N Secteurs"

# Pour Diff_appro : la dernière ligne est un agrégat ("Somme oui
# significativement") et la modalité "Non concerné" n'est pas une
# difficulté en tant que telle. On les garde mais on les flagge.
DIFF_APPRO_MODALITE_AGREGEE = "Somme oui significativement"
DIFF_APPRO_MODALITE_NON_CONCERNE = "Non concerné"


# ---------------------------------------------------------------------------
# Conteneur final
# ---------------------------------------------------------------------------

@dataclass
class BpifranceData:
    """
    Regroupe l'ensemble des DataFrames chargés. Sert de "single source of
    truth" pour les modules en aval (indicators.py, charts.py, etc.).

    Toutes les séries temporelles ont un DatetimeIndex sémestriel
    (mois 5 = vague S1, mois 11 = vague S2) trié par ordre chronologique
    croissant.
    """
    info: pd.DataFrame                  # dictionnaire des indicateurs
    ca_eff: pd.DataFrame                # CA + effectifs (avec moyennes LT)
    carnets: pd.DataFrame               # carnets de commande passés/futurs (avec moy. LT)
    diff_appro: pd.DataFrame            # difficultés d'approvisionnement par modalité
    ca_secteurs: pd.DataFrame           # CA par secteur (sans moyenne LT)

    # Métadonnées calculées au chargement (pratique pour les commentaires).
    last_wave: pd.Timestamp = field(default=None)   # dernière vague observée (toutes feuilles confondues)


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _wave_label(date: pd.Timestamp) -> str:
    """
    Convertit une date semestrielle en libellé court 'S1 2026' / 'S2 2025'.
    Convention Bpifrance : mai = S1, novembre = S2.
    """
    semestre = "S1" if date.month <= 6 else "S2"
    return f"{semestre} {date.year}"


def _drop_empty_future_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Supprime les lignes 'futures' où la date est présente mais toutes
    les valeurs sont NaN (cas de la ligne S2 2026 dans plusieurs feuilles
    du fichier source).

    On utilise dropna(how='all') sur les colonnes de données uniquement,
    PAS sur l'index : on veut garder une ligne où il manquerait une seule
    valeur (rare, mais légitime).
    """
    return df.dropna(how="all")


# ---------------------------------------------------------------------------
# Loaders par feuille
# ---------------------------------------------------------------------------

def load_info(path: str | Path) -> pd.DataFrame:
    """
    Charge le dictionnaire des indicateurs (info_donnees.xlsx).

    Colonnes : onglet, indicateur, question, unite, commentaire.
    Sert à nourrir les prompts Gemini avec le contexte métier
    (libellé de la question posée au dirigeant, unité de mesure).
    """
    df = pd.read_excel(path)
    # Normalisation des noms de colonnes (sans accents pour le code).
    df = df.rename(columns={"unité": "unite"})
    df.attrs["source"] = str(path)
    return df


def load_ca_eff(path: str | Path) -> pd.DataFrame:
    """
    Charge la feuille 'CA Eff N' :
    - Solde d'opinion semestriel sur l'évolution du CA et des effectifs.
    - Inclut les moyennes long terme 2000-2024 (constantes répétées
      ligne par ligne dans le fichier source).

    En-tête sur 2 lignes :
        L0 : (None, 'Evolution du CA', None, 'Evolution des effectifs', None, ...)
        L1 : (None, "Chiffre d'affaires", 'Moyenne 2000-2024', 'Effectifs', 'Moyenne 2000-2024', ...)

    Les colonnes 5-6 sont vides (artefact du fichier Excel) -> on les drop.

    Retourne un DataFrame indexé par la date, avec colonnes :
        ca, ca_moy_lt, eff, eff_moy_lt
    """
    # On lit avec header=[0,1] -> on récupère un MultiIndex de colonnes.
    raw = pd.read_excel(path, sheet_name=SHEET_CA_EFF, header=[0, 1])

    # On reconstruit des noms simples. La 1re colonne (date) a un MultiIndex
    # bizarre du type (NaN, NaN) ou ('Unnamed: 0_level_0', 'Unnamed: 0_level_1').
    # On utilise plutôt iloc pour piocher les colonnes par position : c'est
    # plus robuste que de matcher des noms qui peuvent varier.
    df = pd.DataFrame({
        "date":       raw.iloc[:, 0],
        "ca":         raw.iloc[:, 1],
        "ca_moy_lt":  raw.iloc[:, 2],
        "eff":        raw.iloc[:, 3],
        "eff_moy_lt": raw.iloc[:, 4],
    })

    # Index = date (DatetimeIndex). On force le typage au cas où.
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    df = _drop_empty_future_rows(df)
    df.attrs["source"] = f"{path}#{SHEET_CA_EFF}"
    return df


def load_carnets(path: str | Path) -> pd.DataFrame:
    """
    Charge la feuille 'Carnets de commande' :
    - Solde d'opinion sur le niveau des carnets sur les 6 derniers mois
      ("passés") et l'évolution attendue sur les 6 prochains ("futurs").
    - Avec moyennes long terme 2000-2024 pour chaque.

    Note sur les données : la 1re ligne (S1 1998) contient une moyenne LT
    légèrement différente du reste de la série (-7.449 vs -6.889). C'est
    une anomalie du fichier source. Dans la suite du pipeline, on
    utilisera la moyenne LT de la dernière ligne disponible plutôt que
    la valeur ligne-par-ligne, pour être robuste à ce type d'incohérence.

    Retourne un DataFrame indexé par la date, avec colonnes :
        carnets_passes, carnets_passes_moy_lt,
        carnets_futurs, carnets_futurs_moy_lt
    """
    raw = pd.read_excel(path, sheet_name=SHEET_CARNETS, header=[0, 1])

    df = pd.DataFrame({
        "date":                   raw.iloc[:, 0],
        "carnets_passes":         raw.iloc[:, 1],
        "carnets_passes_moy_lt":  raw.iloc[:, 2],
        "carnets_futurs":         raw.iloc[:, 3],
        "carnets_futurs_moy_lt":  raw.iloc[:, 4],
    })
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    df = _drop_empty_future_rows(df)
    df.attrs["source"] = f"{path}#{SHEET_CARNETS}"
    return df


def load_diff_appro(path: str | Path) -> pd.DataFrame:
    """
    Charge la feuille 'Diff_appro'.

    Spécificité : cette feuille est TRANSPOSÉE par rapport aux autres.
    - lignes = modalités de réponse (7 modalités, dont 'Non concerné'
      et l'agrégat 'Somme oui significativement')
    - colonnes = enquêtes successives, avec libellés de la forme
      'Enquête PME (15 mai - 9 juin 2026)'

    On la transpose pour obtenir le même format que les autres feuilles :
    - index = date d'enquête (DatetimeIndex)
    - colonnes = modalités

    Les valeurs sont en proportion (0-1) dans le fichier source, on les
    convertit en pourcentages (0-100) pour cohérence avec les soldes
    d'opinion (% des autres feuilles).

    À noter : une des colonnes est libellée 'Baromètre (14-26 avril, 2022)'
    et non 'Enquête PME (...)'. C'est un point hors-cycle qu'on garde mais
    qu'on flagge dans une colonne booléenne 'is_barometre'.
    """
    raw = pd.read_excel(path, sheet_name=SHEET_DIFF_APPRO)

    # 1re colonne = libellés de modalités. Les autres = enquêtes.
    modalites = raw.iloc[:, 0].tolist()
    enquetes_labels = raw.columns[1:].tolist()

    # Parser chaque libellé d'enquête pour en extraire (date, type d'enquête).
    parsed = [_parse_enquete_label(lbl) for lbl in enquetes_labels]

    # Construire le DataFrame transposé : index = date, colonnes = modalités.
    # On boucle plutôt qu'on utilise .T parce qu'on veut au passage ajouter
    # la colonne is_barometre.
    rows = []
    for col_idx, (label, (date, is_barometre)) in enumerate(
        zip(enquetes_labels, parsed), start=1
    ):
        row = {mod: raw.iloc[i, col_idx] for i, mod in enumerate(modalites)}
        row["date"] = date
        row["is_barometre"] = is_barometre
        row["label_origine"] = label
        rows.append(row)

    df = pd.DataFrame(rows).set_index("date").sort_index()

    # Conversion proportions -> pourcentages sur les colonnes numériques.
    # On exclut explicitement is_barometre et label_origine.
    cols_pct = [c for c in df.columns if c not in ("is_barometre", "label_origine")]
    df[cols_pct] = df[cols_pct] * 100

    df.attrs["source"] = f"{path}#{SHEET_DIFF_APPRO}"
    df.attrs["agregat"] = DIFF_APPRO_MODALITE_AGREGEE
    df.attrs["non_concerne"] = DIFF_APPRO_MODALITE_NON_CONCERNE
    return df


def _parse_enquete_label(label: str) -> tuple[pd.Timestamp, bool]:
    """
    Extrait une date semestrielle depuis un libellé du type :
        'Enquête PME (15 mai - 9 juin 2026)'  -> 2026-05-01, False
        'Enquête PME (5 nov. - 2 déc. 2025)'  -> 2025-11-01, False
        'Baromètre (14-26 avril, 2022)'       -> 2022-05-01, True (assimilé S1)

    Stratégie : on cherche le 1er token de mois trouvé + l'année (4 chiffres
    en fin de chaîne). C'est suffisamment robuste pour tous les libellés
    observés dans le fichier de référence d'avril 2026.
    """
    is_barometre = label.lower().startswith("baromètre") or label.lower().startswith("barometre")

    # Année : 4 chiffres (les libellés finissent toujours par "... AAAA)" ou similaire).
    annee_match = re.search(r"(\d{4})", label)
    if annee_match is None:
        raise ValueError(f"Année introuvable dans le libellé d'enquête : {label!r}")
    annee = int(annee_match.group(1))

    # Mois : on prend le 1er mois rencontré dans le libellé.
    mois_fr_to_num = {
        "janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avril": 4, "avr": 4,
        "mai": 5, "juin": 6, "juil": 7, "août": 8, "aout": 8, "sept": 9,
        "oct": 10, "nov": 11, "déc": 12, "dec": 12,
    }
    label_lower = label.lower()
    mois = None
    for token, num in mois_fr_to_num.items():
        if token in label_lower:
            mois = num
            break
    if mois is None:
        raise ValueError(f"Mois introuvable dans le libellé d'enquête : {label!r}")

    # Convention Bpifrance : on aligne sur le 1er du mois représentatif
    # de la vague (mai pour S1, novembre pour S2). Les enquêtes mai-juin
    # sont rangées au 1er mai, les nov-déc au 1er novembre. Le baromètre
    # d'avril 2022 est assimilé à S1 2022 (mai).
    if 4 <= mois <= 6:
        date = pd.Timestamp(year=annee, month=5, day=1)
    elif 10 <= mois <= 12:
        date = pd.Timestamp(year=annee, month=11, day=1)
    else:
        # Cas non vu pour l'instant ; on stocke la vraie date au 1er du mois.
        date = pd.Timestamp(year=annee, month=mois, day=1)

    return date, is_barometre


def load_ca_secteurs(path: str | Path) -> pd.DataFrame:
    """
    Charge la feuille 'CA N Secteurs' :
    - Solde d'opinion sur l'évolution du CA, ventilé par secteur.
    - Pas de colonne 'Moyenne 2000-2024' dans cette feuille.

    Secteurs : Ensemble, Industrie, Commerce, Construction, Transports,
    Tourisme, Services. Le secteur Transports n'a pas de données pour
    les premières vagues (~1998-2007) -> les NaN sont conservés et
    seront gérés en aval.
    """
    raw = pd.read_excel(path, sheet_name=SHEET_CA_SECTEURS)

    # Renommage : 1re colonne = date, les autres ont déjà les bons noms.
    raw = raw.rename(columns={raw.columns[0]: "date"})
    # Normalisation snake_case + sans accents pour usage en code.
    rename_map = {
        "Ensemble": "ensemble",
        "Industrie": "industrie",
        "Commerce": "commerce",
        "Construction": "construction",
        "Transports": "transports",
        "Tourisme": "tourisme",
        "Services": "services",
    }
    raw = raw.rename(columns=rename_map)

    raw["date"] = pd.to_datetime(raw["date"])
    df = raw.set_index("date").sort_index()
    df = _drop_empty_future_rows(df)

    df.attrs["source"] = f"{path}#{SHEET_CA_SECTEURS}"
    df.attrs["secteurs"] = list(rename_map.values())
    return df


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def load_all(data_dir: str | Path = "data") -> BpifranceData:
    """
    Charge l'ensemble des données nécessaires au rapport.

    Args:
        data_dir : dossier contenant 'donnees.xlsx' et 'info_donnees.xlsx'.

    Returns:
        Un objet BpifranceData prêt à être consommé par indicators.py.

    Exemple :
        >>> data = load_all("data")
        >>> data.last_wave
        Timestamp('2026-05-01 00:00:00')
        >>> data.ca_eff.tail(2)
                          ca   ca_moy_lt    eff  eff_moy_lt
        date
        2025-11-01  -10.78    12.755...   -3.98   7.758...
        2026-05-01  -14.00    12.755...   -8.00   7.758...
    """
    data_dir = Path(data_dir)
    donnees = data_dir / "donnees.xlsx"
    info = data_dir / "info_donnees.xlsx"

    bpf = BpifranceData(
        info=load_info(info),
        ca_eff=load_ca_eff(donnees),
        carnets=load_carnets(donnees),
        diff_appro=load_diff_appro(donnees),
        ca_secteurs=load_ca_secteurs(donnees),
    )

    # On calcule la "dernière vague observée" globale = max des dernières
    # dates des séries temporelles principales. Sert d'horloge maîtresse
    # pour tout le rapport.
    candidate_dates = [
        bpf.ca_eff.index.max(),
        bpf.carnets.index.max(),
        bpf.diff_appro.index.max(),
        bpf.ca_secteurs.index.max(),
    ]
    bpf.last_wave = max(candidate_dates)
    return bpf


def last_observed_wave(df: pd.DataFrame) -> Optional[pd.Timestamp]:
    """
    Retourne la date de la dernière vague effectivement renseignée dans
    un DataFrame (toutes les colonnes ne sont pas forcément non-NaN, mais
    au moins une l'est). Utile si on veut interroger une feuille en
    particulier sans passer par BpifranceData.
    """
    if df.empty:
        return None
    return df.index.max()
