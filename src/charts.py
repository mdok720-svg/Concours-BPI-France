"""
charts.py
=========

Génération des graphiques de l'enquête de conjoncture, au format PNG,
prêts à être insérés dans le rapport PowerPoint.

Toutes les fonctions :
- prennent en entrée un FullReport (cf. indicators.py)
- appliquent la charte Bpifrance via style.apply_bpifrance_style()
- sauvegardent le graphique dans un dossier (par défaut output/charts/)
- retournent le chemin du fichier généré

Graphiques produits :
1. plot_ca_eff               -> CA + Effectifs + leurs moyennes LT (slide 1)
2. plot_carnets_passes       -> Carnets passés + moyenne LT (slide 1)
3. plot_secteurs             -> CA par secteur, 7 courbes (slide 2)
4. plot_diff_appro_stacked   -> Bonus : barres empilées des modalités d'appro

Auteur : projet challenge Bpifrance — phase 2 (graphiques).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from .indicators import FullReport
from .style import (
    COLORS,
    SECTOR_COLORS,
    SECTOR_LABELS,
    FONT_SIZES,
    FIGSIZE_DEFAULT,
    DPI,
    source_text,
    apply_bpifrance_style,
)


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _format_axes_dates(ax, serie_index: pd.DatetimeIndex) -> None:
    """
    Formate l'axe des x : ticks tous les 2 ans, format AAAA, horizontal.
    Reproduit le style Bpifrance (2000, 2002, 2004, ...).
    """
    # On force les bornes pour que la dernière année soit visible.
    ax.set_xlim(serie_index.min(), serie_index.max())
    # Locator : tous les 2 ans en mai (pour aligner sur les vagues S1).
    ax.xaxis.set_major_locator(mdates.YearLocator(base=2, month=5))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center")


def _annotate_last_value(ax, x, y, color: str, *, offset_x: int = 8,
                         offset_y: int = 0, fmt: str = "{:.0f}") -> None:
    """
    Annote la dernière valeur d'une courbe à droite, dans la couleur de
    la série. Convention visuelle Bpifrance.
    """
    if pd.isna(y):
        return
    ax.annotate(
        fmt.format(y),
        xy=(x, y),
        xytext=(offset_x, offset_y),
        textcoords="offset points",
        color=color,
        fontsize=FONT_SIZES["label"],
        fontweight="bold",
        va="center",
    )


def _add_source(fig, n_repondants: Optional[int] = None) -> None:
    """Mention 'Champ ; Source' en bas à gauche de la figure."""
    fig.text(
        0.01, 0.005,
        source_text(n_repondants),
        fontsize=FONT_SIZES["source"],
        color=COLORS["gris_texte"],
        style="italic",
        ha="left",
        va="bottom",
    )


def _add_title(ax, title: str, subtitle: str) -> None:
    """
    Titre principal en gras + sous-titre (unité) plus discret en dessous.
    Reproduit la convention Bpifrance vue dans presentation.pptx.
    """
    ax.set_title(title, loc="left", fontsize=FONT_SIZES["title"],
                 fontweight="bold", color=COLORS["gris_texte"], pad=22)
    # Sous-titre : on l'ajoute via ax.text dans les coordonnées axes,
    # juste sous le titre (y > 1 = au-dessus de l'axe).
    ax.text(0, 1.02, subtitle,
            transform=ax.transAxes,
            fontsize=FONT_SIZES["subtitle"],
            color=COLORS["gris_texte"],
            ha="left", va="bottom",
            style="italic")


def _ensure_outdir(out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


# ---------------------------------------------------------------------------
# Graphique 1 — CA + Effectifs (slide 1, gauche)
# ---------------------------------------------------------------------------

def plot_ca_eff(report: FullReport,
                out_dir: str | Path = "output/charts",
                n_repondants: Optional[int] = None,
                      show_source: bool = True) -> Path:
    """
    Reproduit le graphique 'Évolution de l'activité et des effectifs pour
    l'année en cours (solde d'opinion en %)' de la slide 1.

    4 séries :
        - Chiffre d'affaires (vert plein)
        - Moyenne LT du CA (vert pointillé)
        - Effectifs (orange plein)
        - Moyenne LT des Effectifs (orange pointillé)
    """
    apply_bpifrance_style()
    out_dir = _ensure_outdir(out_dir)

    ca_serie = report.ca.serie
    eff_serie = report.eff.serie
    ca_moy = report.ca.moyenne_lt
    eff_moy = report.eff.moyenne_lt

    fig, ax = plt.subplots(figsize=FIGSIZE_DEFAULT, dpi=DPI)

    # Courbes principales
    ax.plot(ca_serie.index, ca_serie.values,
            color=COLORS["vert_bpi"], linewidth=2.0, label="Chiffre d'affaires")
    ax.plot(eff_serie.index, eff_serie.values,
            color=COLORS["orange_bpi"], linewidth=2.0, label="Effectifs")

    # Moyennes long terme — lignes horizontales pointillées
    ax.axhline(ca_moy, color=COLORS["vert_bpi"], linestyle=":",
               linewidth=1.5, label="Moyenne 2000-2024")
    ax.axhline(eff_moy, color=COLORS["orange_bpi"], linestyle=":",
               linewidth=1.5, label="Moyenne 2000-2024")

    # Ligne 0 (visuellement utile vu qu'on est dans le négatif)
    ax.axhline(0, color=COLORS["gris_texte"], linewidth=0.6, alpha=0.5)

    # Dernières valeurs annotées
    last_date = ca_serie.index.max()
    _annotate_last_value(ax, last_date, ca_serie.iloc[-1],
                         COLORS["vert_bpi"])
    _annotate_last_value(ax, last_date, eff_serie.iloc[-1],
                         COLORS["orange_bpi"])

    _format_axes_dates(ax, ca_serie.index)
    _add_title(ax,
               "Évolution de l'activité et des effectifs pour l'année en cours",
               "(solde d'opinion en %)")

    # Légende en bas, sur 2 colonnes (CA / Eff)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12),
              ncol=2, frameon=False)

    if show_source:
        _add_source(fig, n_repondants)
    out_path = out_dir / "01_ca_eff.png"
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# Graphique 2 — Carnets de commande passés (slide 1, droite)
# ---------------------------------------------------------------------------

def plot_carnets_passes(report: FullReport,
                        out_dir: str | Path = "output/charts",
                        n_repondants: Optional[int] = None,
                      show_source: bool = True) -> Path:
    """
    Reproduit le graphique 'Jugement sur l'état des carnets de commandes
    passés (solde d'opinion en %)' de la slide 1.

    2 séries :
        - 6 derniers mois (vert plein)
        - Moyenne LT (vert pointillé horizontal)
    """
    apply_bpifrance_style()
    out_dir = _ensure_outdir(out_dir)

    serie = report.carnets_passes.serie
    moy = report.carnets_passes.moyenne_lt

    fig, ax = plt.subplots(figsize=FIGSIZE_DEFAULT, dpi=DPI)

    ax.plot(serie.index, serie.values,
            color=COLORS["vert_bpi"], linewidth=2.0, label="6 derniers mois")
    ax.axhline(moy, color=COLORS["vert_bpi"], linestyle=":",
               linewidth=1.5, label="Moyenne 2000-2024")
    ax.axhline(0, color=COLORS["gris_texte"], linewidth=0.6, alpha=0.5)

    _annotate_last_value(ax, serie.index.max(), serie.iloc[-1],
                         COLORS["vert_bpi"])

    _format_axes_dates(ax, serie.index)
    _add_title(ax,
               "Jugement sur l'état des carnets de commandes passés",
               "(solde d'opinion en %)")

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12),
              ncol=2, frameon=False)

    if show_source:
        _add_source(fig, n_repondants)
    out_path = out_dir / "02_carnets_passes.png"
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# Graphique 3 — CA par secteur (slide 2)
# ---------------------------------------------------------------------------

def plot_secteurs(report: FullReport,
                  out_dir: str | Path = "output/charts",
                  n_repondants: Optional[int] = None,
                  start_year: int = 2006,
                      show_source: bool = True) -> Path:
    """
    Reproduit le graphique 'Évolution de l'activité pour l'année en cours,
    par branche d'activité (solde d'opinion en %)' de la slide 2.

    7 séries (Ensemble + 6 secteurs).

    Améliorations vs le PPTX original :
    - Pas d'étiquettes de points sur toutes les valeurs (illisible dans
      l'original) : seules les VALEURS DE LA DERNIÈRE VAGUE sont annotées.
    - 'Ensemble' tracée en pointillé noir épais pour ressortir.
    - Démarrage en 2006 par défaut (les premières années 1998-2005 ont
      un secteur Transports vide, ça crée une discontinuité visuelle).
    """
    apply_bpifrance_style()
    out_dir = _ensure_outdir(out_dir)

    df = report.secteurs.historique.copy()
    df = df[df.index.year >= start_year]

    fig, ax = plt.subplots(figsize=(9.5, 5.0), dpi=DPI)   # un peu plus large

    # Ordre de tracé : on trace 'ensemble' EN DERNIER pour qu'il passe
    # devant les autres courbes (lisibilité).
    secteurs_ordre = [s for s in SECTOR_COLORS if s != "ensemble"] + ["ensemble"]

    for sect in secteurs_ordre:
        if sect not in df.columns:
            continue
        is_ensemble = (sect == "ensemble")
        ax.plot(df.index, df[sect],
                color=SECTOR_COLORS[sect],
                linewidth=2.2 if is_ensemble else 1.6,
                linestyle="--" if is_ensemble else "-",
                label=SECTOR_LABELS[sect])

    ax.axhline(0, color=COLORS["gris_texte"], linewidth=0.6, alpha=0.5)

    # Annoter UNIQUEMENT les valeurs finales (corrige le défaut du PPTX original).
    # Algorithme de répulsion verticale : quand 5+ secteurs ont des valeurs
    # finales très proches (cas S1 2026 : -1, -11, -14, -15, -16, -17, -19),
    # un simple offset binaire ne suffit pas. On calcule des positions
    # d'affichage en cascade, en garantissant un écart vertical minimum.
    last_date = df.index.max()
    final_vals = [(sect, df.loc[last_date, sect])
                  for sect in df.columns if pd.notna(df.loc[last_date, sect])]
    # Tri décroissant : du plus haut au plus bas en y.
    final_vals.sort(key=lambda kv: kv[1], reverse=True)

    # On calcule un min_gap proportionnel à l'amplitude affichée pour que
    # ça reste lisible quel que soit le zoom de l'axe.
    y_min, y_max = ax.get_ylim()
    min_gap = (y_max - y_min) * 0.035   # ~3.5 % de la hauteur d'axe

    # Cascade : chaque label est placé soit à sa vraie valeur, soit
    # min_gap en dessous du précédent (vu qu'on parcourt du haut vers le bas).
    display_positions: list[tuple[str, float, float]] = []  # (sect, y_reel, y_affiche)
    last_display_y = None
    for sect, val in final_vals:
        if last_display_y is None:
            y_disp = val
        else:
            y_disp = min(val, last_display_y - min_gap)
        display_positions.append((sect, val, y_disp))
        last_display_y = y_disp

    # On rend les labels via ax.text directement, en coordonnées data,
    # à droite de la dernière date (offset horizontal en points).
    for sect, val, y_disp in display_positions:
        ax.annotate(
            f"{val:.0f}",
            xy=(last_date, y_disp),
            xytext=(8, 0),
            textcoords="offset points",
            color=SECTOR_COLORS[sect],
            fontsize=FONT_SIZES["label"],
            fontweight="bold",
            va="center",
        )

    _format_axes_dates(ax, df.index)
    _add_title(ax,
               "Évolution de l'activité pour l'année en cours, par branche d'activité",
               "(solde d'opinion en %)")

    # Légende en bas, sur 4 colonnes (7 entrées => 2 lignes équilibrées)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13),
              ncol=4, frameon=False)

    if show_source:
        _add_source(fig, n_repondants)
    out_path = out_dir / "03_secteurs.png"
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# Graphique 4 (bonus) — Difficultés d'approvisionnement empilées
# ---------------------------------------------------------------------------

def plot_diff_appro_stacked(report: FullReport,
                            out_dir: str | Path = "output/charts",
                            n_repondants: Optional[int] = None,
                      show_source: bool = True) -> Path:
    """
    Bonus : barres empilées 100% des modalités de difficultés
    d'approvisionnement, vague par vague.

    Pas dans le PPTX original (qui se contentait de mentionner le chiffre
    dans le commentaire), mais c'est un graphique standard des notes de
    conjoncture Bpifrance qui enrichit le rapport.

    L'agrégat 'Somme oui significativement' n'est PAS empilé (ce serait
    du double-comptage), il est seulement listé.
    """
    apply_bpifrance_style()
    out_dir = _ensure_outdir(out_dir)

    df = report.diff_appro.historique_modalites.copy()

    # historique_modalites est déjà filtré sur is_barometre==False (cf.
    # build_diff_appro_report), mais par sécurité on dédoublonne au cas où
    # plusieurs lignes coexisteraient pour la même date.
    df = df[~df.index.duplicated(keep="first")]

    # Modalités à empiler dans un ordre signifiant : "limitant fortement"
    # en bas (zone de risque), "non concerné" en haut.
    ordre = [
        "Oui, limitant fortement la production / l'activité",
        "Oui, limitant modérément la production / l'activité",
        "Oui, limitant faiblement la production / l'activité",
        "Oui, ne limitant pas la production / l'activité",
        "Non, aucune",
        "Non concerné",
    ]
    # On n'empile que les modalités présentes dans le DF
    ordre = [m for m in ordre if m in df.columns]

    # Palette dégradée : du rouge (limitant fortement) au gris (non concerné).
    palette = [
        COLORS["rouge_bpi"],     # fortement -> rouge
        COLORS["orange_bpi"],    # modérément -> orange
        COLORS["jaune_bpi"],     # faiblement -> jaune
        "#A8D8B0",               # ne limitant pas -> vert pâle
        COLORS["vert_bpi"],      # aucune -> vert plein
        COLORS["gris_grille"],   # non concerné -> gris
    ]

    fig, ax = plt.subplots(figsize=(8.5, 5.0), dpi=DPI)

    # Libellés d'axe X = vagues sous forme courte (S1 2024, S2 2024, ...)
    x_labels = [f"{'S1' if d.month <= 6 else 'S2'} {d.year}" for d in df.index]
    x_pos = range(len(df.index))

    bottom = [0.0] * len(df.index)
    for mod, color in zip(ordre, palette):
        vals = df[mod].fillna(0).values
        ax.bar(x_pos, vals, bottom=bottom, color=color,
               label=mod, edgecolor="white", linewidth=0.5)
        bottom = [b + v for b, v in zip(bottom, vals)]

    ax.set_xticks(list(x_pos))
    ax.set_xticklabels(x_labels, rotation=45, ha="right")
    ax.set_ylim(0, 100)
    ax.set_ylabel("% des répondants")

    _add_title(ax,
               "Difficultés d'approvisionnement déclarées par les TPE-PME",
               "(% des répondants, par vague d'enquête)")

    # Légende compacte juste sous les ticks rotatés (et avant la source).
    # On sort manuellement le layout pour avoir la main sur les marges :
    # - les ticks rotatés à 45° prennent de la place verticale
    # - la légende doit être collée au graphique sans chevaucher les ticks
    # - la source doit rester tout en bas de la figure
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22),
              ncol=2, frameon=False, fontsize=FONT_SIZES["legend"] - 1)

    # On augmente la marge basse pour laisser place aux ticks + légende + source.
    fig.subplots_adjust(bottom=0.32, top=0.88, left=0.08, right=0.97)

    if show_source:
        _add_source(fig, n_repondants)
    out_path = out_dir / "04_diff_appro.png"
    # bbox_inches=None pour respecter notre subplots_adjust manuel
    fig.savefig(out_path, bbox_inches=None)
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# Orchestrateur
# ---------------------------------------------------------------------------

def render_all_charts(report: FullReport,
                      out_dir: str | Path = "output/charts",
                      n_repondants: Optional[int] = None,
                      show_source: bool = True) -> dict[str, Path]:
    """
    Génère tous les graphiques du rapport et retourne un dict
    {nom_logique: chemin_png} consommable par report_builder.py.
    """
    kw = dict(n_repondants=n_repondants, show_source=show_source)
    return {
        "ca_eff":       plot_ca_eff(report, out_dir, **kw),
        "carnets":      plot_carnets_passes(report, out_dir, **kw),
        "secteurs":     plot_secteurs(report, out_dir, **kw),
        "diff_appro":   plot_diff_appro_stacked(report, out_dir, **kw),
    }
