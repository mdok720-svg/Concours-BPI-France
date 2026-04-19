"""
indicators.py
=============

Calcul des métriques dérivées à partir des séries temporelles chargées par
data_loader.py.

Pour chaque indicateur "à série temporelle" (CA, Effectifs, Carnets passés,
Carnets futurs), on calcule :
    - la valeur de la dernière vague disponible
    - le delta semestriel (variation en points vs vague précédente)
    - le delta annuel (variation en points vs même vague N-1)
    - l'écart à la moyenne long terme 2000-2024
    - le rang historique de la valeur, EN EXCLUANT les périodes de crise
      (subprimes 2008-09 et Covid 2020-21), conformément à la convention
      Bpifrance.

Pour les secteurs (CA N Secteurs), on calcule :
    - la valeur par secteur à la dernière vague
    - le classement décroissant
    - les deltas semestriels et annuels par secteur

Pour les difficultés d'approvisionnement, on calcule :
    - la répartition actuelle des modalités (%)
    - l'évolution de la 'Somme oui significativement' (delta semestriel,
      delta annuel)
    - la série historique de l'agrégat

Sortie : un objet FullReport, sérialisable en dict (utile pour injection
dans les prompts Gemini et pour les modules de visualisation).

Auteur : projet challenge Bpifrance — phase 1 (indicateurs).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

import pandas as pd

from .data_loader import (
    BpifranceData,
    DIFF_APPRO_MODALITE_AGREGEE,
    DIFF_APPRO_MODALITE_NON_CONCERNE,
    _wave_label,
)


# ---------------------------------------------------------------------------
# Périodes de crise à exclure du calcul du rang historique.
# Convention Bpifrance : on parle de "rang hors crises" pour situer une
# valeur par rapport à la dynamique structurelle, pas par rapport aux
# années de choc exogène.
# ---------------------------------------------------------------------------

CRISIS_PERIODS: list[tuple[pd.Timestamp, pd.Timestamp]] = [
    # Crise financière mondiale (subprimes + récession).
    (pd.Timestamp("2008-05-01"), pd.Timestamp("2009-11-01")),
    # Covid + rebond atypique post-confinement (jusqu'à mi-2021 inclus).
    (pd.Timestamp("2020-05-01"), pd.Timestamp("2021-05-01")),
]


# ---------------------------------------------------------------------------
# Dataclasses de sortie
# ---------------------------------------------------------------------------

@dataclass
class TimeSeriesIndicator:
    """
    Rapport pour une série temporelle simple (CA, Eff, Carnets passés/futurs).
    Tout ce qu'il faut pour générer un commentaire et un graphique.
    """
    nom: str                            # libellé humain : "Chiffre d'affaires"
    cle: str                            # clé courte machine : "ca"
    unite: str                          # "Solde d'opinion (%)"
    derniere_vague: str                 # "S1 2026"
    valeur: float                       # ex. -14.0
    delta_semestriel: Optional[float]   # ex. -3.2 (en points)
    delta_annuel: Optional[float]       # ex. -9.6 (en points)
    moyenne_lt: Optional[float]         # ex. 12.76
    ecart_moyenne_lt: Optional[float]   # valeur - moyenne_lt
    rang_hors_crises: dict              # {'rang_croissant', 'sur', 'min', 'max', 'mediane'}

    # Série historique complète, utilisée par charts.py. Exclue de to_dict()
    # pour que la sortie JSON pour le LLM reste compacte.
    serie: pd.Series = field(default=None, repr=False)

    def to_dict(self) -> dict:
        """Sortie JSON-friendly (sans la série pandas)."""
        d = asdict(self)
        d.pop("serie", None)
        return d


@dataclass
class SectorialReport:
    """
    Rapport CA par secteur à la dernière vague.
    """
    derniere_vague: str
    ensemble: float                                 # CA agrégé tous secteurs
    valeurs: dict                                   # {secteur: valeur}
    classement_decroissant: list                    # [(secteur, valeur), ...]
    delta_semestriel: dict                          # {secteur: delta}
    delta_annuel: dict                              # {secteur: delta}
    secteur_le_plus_haut: tuple                     # (secteur, valeur)
    secteur_le_plus_bas: tuple                      # (secteur, valeur)

    # Série historique par secteur (DataFrame), pour charts.py.
    historique: pd.DataFrame = field(default=None, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("historique", None)
        return d


@dataclass
class DiffApproReport:
    """
    Rapport difficultés d'approvisionnement à la dernière vague.
    """
    derniere_vague: str
    repartition_actuelle: dict                      # {modalité: %}
    somme_oui_significativement: float              # % cumulé "oui significatif"
    delta_semestriel_somme_oui: Optional[float]
    delta_annuel_somme_oui: Optional[float]
    rang_hors_crises_somme_oui: dict                # même structure que TimeSeriesIndicator

    historique_somme_oui: pd.Series = field(default=None, repr=False)
    historique_modalites: pd.DataFrame = field(default=None, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("historique_somme_oui", None)
        d.pop("historique_modalites", None)
        return d


@dataclass
class FullReport:
    """
    Rapport complet, prêt à être consommé par charts.py + commentary.py.
    """
    derniere_vague: str
    ca: TimeSeriesIndicator
    eff: TimeSeriesIndicator
    carnets_passes: TimeSeriesIndicator
    carnets_futurs: TimeSeriesIndicator
    secteurs: SectorialReport
    diff_appro: DiffApproReport

    def to_dict(self) -> dict:
        return {
            "derniere_vague": self.derniere_vague,
            "ca": self.ca.to_dict(),
            "eff": self.eff.to_dict(),
            "carnets_passes": self.carnets_passes.to_dict(),
            "carnets_futurs": self.carnets_futurs.to_dict(),
            "secteurs": self.secteurs.to_dict(),
            "diff_appro": self.diff_appro.to_dict(),
        }


# ---------------------------------------------------------------------------
# Fonctions de calcul "pures" sur séries pandas
# ---------------------------------------------------------------------------

def filter_hors_crises(serie: pd.Series,
                       periods: list[tuple[pd.Timestamp, pd.Timestamp]] = CRISIS_PERIODS
                       ) -> pd.Series:
    """
    Retourne la série privée des points appartenant à une période de crise.

    Implémentation : on construit un masque booléen "appartient à au moins
    une crise" puis on inverse. Robuste à des périodes vides ou à un
    DatetimeIndex non trié.
    """
    if serie.empty:
        return serie
    in_crisis = pd.Series(False, index=serie.index)
    for start, end in periods:
        in_crisis |= (serie.index >= start) & (serie.index <= end)
    return serie[~in_crisis]


def delta_semestriel(serie: pd.Series, date: pd.Timestamp) -> Optional[float]:
    """
    Variation entre `date` et la vague précédente (en points).
    Retourne None si on n'a pas de vague antérieure.
    """
    serie_clean = serie.dropna().sort_index()
    if date not in serie_clean.index:
        return None
    pos = serie_clean.index.get_loc(date)
    if pos == 0:
        return None
    return float(serie_clean.iloc[pos] - serie_clean.iloc[pos - 1])


def delta_annuel(serie: pd.Series, date: pd.Timestamp) -> Optional[float]:
    """
    Variation entre `date` et la même vague N-1 (en points).
    Recherche la valeur exactement 1 an avant (même mois). Retourne None
    si elle n'existe pas dans la série.
    """
    serie_clean = serie.dropna().sort_index()
    target = pd.Timestamp(year=date.year - 1, month=date.month, day=date.day)
    if target not in serie_clean.index:
        return None
    return float(serie_clean.loc[date] - serie_clean.loc[target])


def rang_hors_crises(serie: pd.Series, date: pd.Timestamp) -> dict:
    """
    Calcule le rang croissant de la valeur de `date` dans la série
    privée des périodes de crise. Renvoie aussi min/max/médiane hors
    crises pour aider le LLM à contextualiser ("plus bas niveau depuis...").

    'rang_croissant' = 1 -> la plus basse valeur historique hors crises ;
    'sur' = nombre total de points hors crises (date incluse).
    """
    serie_clean = serie.dropna().sort_index()
    if date not in serie_clean.index:
        return {}
    valeur = serie_clean.loc[date]

    # On exclut les crises MAIS on garde la date courante même si elle
    # tombe hors période de crise — ce qui est notre cas en S1 2026.
    serie_hors_crises = filter_hors_crises(serie_clean)

    if date not in serie_hors_crises.index:
        # Cas où la date courante serait DANS une période de crise :
        # on la rajoute pour pouvoir la classer.
        serie_hors_crises = pd.concat([serie_hors_crises,
                                       pd.Series([valeur], index=[date])]).sort_index()

    rang = int((serie_hors_crises < valeur).sum() + 1)
    return {
        "rang_croissant": rang,
        "sur": int(len(serie_hors_crises)),
        "min": float(serie_hors_crises.min()),
        "max": float(serie_hors_crises.max()),
        "mediane": float(serie_hors_crises.median()),
        "date_min": serie_hors_crises.idxmin().strftime("%Y-%m"),
        "date_max": serie_hors_crises.idxmax().strftime("%Y-%m"),
    }


# ---------------------------------------------------------------------------
# Constructeurs de rapports par indicateur
# ---------------------------------------------------------------------------

def build_timeseries_indicator(
    nom: str,
    cle: str,
    unite: str,
    serie: pd.Series,
    moyenne_lt: Optional[float],
    date: pd.Timestamp,
) -> TimeSeriesIndicator:
    """
    Assemble un TimeSeriesIndicator pour une série + une date donnée.

    `moyenne_lt` est passée en paramètre (et pas calculée ici) parce que
    Bpifrance la fournit directement dans le fichier — on respecte leur
    valeur de référence plutôt que de la recalculer.
    """
    serie_clean = serie.dropna().sort_index()
    valeur = float(serie_clean.loc[date]) if date in serie_clean.index else float("nan")

    return TimeSeriesIndicator(
        nom=nom,
        cle=cle,
        unite=unite,
        derniere_vague=_wave_label(date),
        valeur=valeur,
        delta_semestriel=delta_semestriel(serie_clean, date),
        delta_annuel=delta_annuel(serie_clean, date),
        moyenne_lt=float(moyenne_lt) if moyenne_lt is not None else None,
        ecart_moyenne_lt=(valeur - float(moyenne_lt)) if moyenne_lt is not None else None,
        rang_hors_crises=rang_hors_crises(serie_clean, date),
        serie=serie_clean,
    )


def build_sectorial_report(
    df_secteurs: pd.DataFrame,
    date: pd.Timestamp,
) -> SectorialReport:
    """
    Construit le rapport CA par secteur pour la dernière vague.

    On exclut 'ensemble' du classement et des deltas par secteur (c'est
    l'agrégat global, on le rapporte séparément).
    """
    # Liste des secteurs (hors 'ensemble').
    secteurs = [c for c in df_secteurs.columns if c != "ensemble"]

    # Valeurs à la dernière vague.
    valeurs = {s: float(df_secteurs.loc[date, s])
               for s in secteurs
               if pd.notna(df_secteurs.loc[date, s])}
    ensemble = float(df_secteurs.loc[date, "ensemble"])

    # Classement décroissant : du secteur le plus haut au plus bas.
    classement = sorted(valeurs.items(), key=lambda kv: kv[1], reverse=True)

    # Deltas par secteur. Pour la robustesse, on utilise les fonctions
    # déjà écrites sur chaque colonne.
    deltas_sem = {}
    deltas_an = {}
    for s in secteurs:
        deltas_sem[s] = delta_semestriel(df_secteurs[s], date)
        deltas_an[s] = delta_annuel(df_secteurs[s], date)

    # Extrêmes (utiles pour le commentaire).
    secteur_haut = classement[0]
    secteur_bas = classement[-1]

    return SectorialReport(
        derniere_vague=_wave_label(date),
        ensemble=ensemble,
        valeurs=valeurs,
        classement_decroissant=classement,
        delta_semestriel=deltas_sem,
        delta_annuel=deltas_an,
        secteur_le_plus_haut=secteur_haut,
        secteur_le_plus_bas=secteur_bas,
        historique=df_secteurs,
    )


def build_diff_appro_report(
    df_diff: pd.DataFrame,
    date: pd.Timestamp,
) -> DiffApproReport:
    """
    Construit le rapport difficultés d'approvisionnement à la dernière vague.

    Subtilité : pour 2022-05, on a deux lignes (Enquête PME et Baromètre).
    On utilise la ligne is_barometre=False (l'enquête officielle) pour
    rester cohérent avec le reste du rapport.
    """
    # Si plusieurs lignes pour la même date, on garde celle de l'enquête PME.
    if isinstance(df_diff.loc[date], pd.DataFrame):
        slice_date = df_diff.loc[date].query("is_barometre == False").iloc[0]
    else:
        slice_date = df_diff.loc[date]

    # Modalités numériques uniquement.
    modalites_numeriques = [c for c in df_diff.columns
                            if c not in ("is_barometre", "label_origine")]

    repartition = {m: float(slice_date[m])
                   for m in modalites_numeriques
                   if m != DIFF_APPRO_MODALITE_AGREGEE}

    # Série historique de l'agrégat 'Somme oui significativement'.
    # On filtre aussi les baromètres pour avoir une série monotone.
    df_pme = df_diff[df_diff["is_barometre"] == False]
    serie_somme_oui = df_pme[DIFF_APPRO_MODALITE_AGREGEE].dropna().sort_index()
    valeur_somme_oui = float(slice_date[DIFF_APPRO_MODALITE_AGREGEE])

    return DiffApproReport(
        derniere_vague=_wave_label(date),
        repartition_actuelle=repartition,
        somme_oui_significativement=valeur_somme_oui,
        delta_semestriel_somme_oui=delta_semestriel(serie_somme_oui, date),
        delta_annuel_somme_oui=delta_annuel(serie_somme_oui, date),
        rang_hors_crises_somme_oui=rang_hors_crises(serie_somme_oui, date),
        historique_somme_oui=serie_somme_oui,
        historique_modalites=df_pme[modalites_numeriques],
    )


# ---------------------------------------------------------------------------
# Orchestrateur de haut niveau
# ---------------------------------------------------------------------------

def compute_full_report(data: BpifranceData,
                        date: Optional[pd.Timestamp] = None) -> FullReport:
    """
    Calcule l'ensemble des indicateurs à la date demandée (par défaut :
    la dernière vague observée).

    Cette fonction est le seul point d'entrée nécessaire pour les modules
    en aval (charts.py, commentary.py, report_builder.py).

    Args:
        data : objet BpifranceData chargé par data_loader.load_all()
        date : date de la vague à analyser. Si None, prend data.last_wave.

    Returns:
        FullReport contenant tous les sous-rapports.
    """
    if date is None:
        date = data.last_wave

    # Pour les moyennes LT : on prend la valeur observée à la dernière
    # vague (au cas où il y aurait une légère variation à 1 ou 2 lignes
    # sur la 1re vague de 1998 — cf. note dans data_loader.load_carnets).
    moy_lt_ca = float(data.ca_eff["ca_moy_lt"].dropna().iloc[-1])
    moy_lt_eff = float(data.ca_eff["eff_moy_lt"].dropna().iloc[-1])
    moy_lt_carn_p = float(data.carnets["carnets_passes_moy_lt"].dropna().iloc[-1])
    moy_lt_carn_f = float(data.carnets["carnets_futurs_moy_lt"].dropna().iloc[-1])

    return FullReport(
        derniere_vague=_wave_label(date),
        ca=build_timeseries_indicator(
            nom="Chiffre d'affaires",
            cle="ca",
            unite="Solde d'opinion (%)",
            serie=data.ca_eff["ca"],
            moyenne_lt=moy_lt_ca,
            date=date,
        ),
        eff=build_timeseries_indicator(
            nom="Effectifs",
            cle="eff",
            unite="Solde d'opinion (%)",
            serie=data.ca_eff["eff"],
            moyenne_lt=moy_lt_eff,
            date=date,
        ),
        carnets_passes=build_timeseries_indicator(
            nom="Carnets de commande passés (6 derniers mois)",
            cle="carnets_passes",
            unite="Solde d'opinion (%)",
            serie=data.carnets["carnets_passes"],
            moyenne_lt=moy_lt_carn_p,
            date=date,
        ),
        carnets_futurs=build_timeseries_indicator(
            nom="Carnets de commande futurs (6 prochains mois)",
            cle="carnets_futurs",
            unite="Solde d'opinion (%)",
            serie=data.carnets["carnets_futurs"],
            moyenne_lt=moy_lt_carn_f,
            date=date,
        ),
        secteurs=build_sectorial_report(data.ca_secteurs, date),
        diff_appro=build_diff_appro_report(data.diff_appro, date),
    )
