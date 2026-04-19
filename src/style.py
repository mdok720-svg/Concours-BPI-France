"""
style.py
========

Centralise la charte graphique Bpifrance pour tous les graphiques produits.

Les couleurs ont été extraites directement du fichier presentation.pptx
fourni par Bpifrance (theme1.xml + chart{1,2,3}.xml). Les noms de
clés correspondent à l'usage métier, pas aux noms internes du thème.

Si Bpifrance modifie sa charte un jour, c'est le seul fichier à éditer.
"""

from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# Palette Bpifrance — extraite du theme1.xml de presentation.pptx
# ---------------------------------------------------------------------------

COLORS = {
    # Couleurs principales du thème
    "vert_bpi":     "#69CD59",   # tx2 — couleur signature, courbes principales
    "orange_bpi":   "#EA7700",   # accent1 — courbe secondaire (Effectifs)
    "rouge_bpi":    "#AF282C",   # accent2 — Industrie
    "rose_bpi":     "#C83764",   # accent3 — Transports
    "cyan_bpi":     "#00A3E0",   # accent4 — Tourisme
    "bleu_bpi":     "#1D418A",   # accent5 — réserve
    "vert_fonce":   "#10833B",   # accent6 — réserve
    "jaune_bpi":    "#FFCD00",   # lt2 — Services
    "noir":         "#000000",   # Ensemble (pointillé)
    "gris_texte":   "#4B3C3C",   # dk1 — texte
    # Utilitaires
    "gris_grille":  "#D9D9D9",   # grille horizontale légère
    "blanc":        "#FFFFFF",
}


# Mapping sectoriel (CA N Secteurs) - ordre de tracé important pour la lisibilité.
# Clés = noms snake_case utilisés dans data_loader.load_ca_secteurs.
SECTOR_COLORS = {
    "ensemble":     COLORS["noir"],
    "industrie":    COLORS["rouge_bpi"],
    "commerce":     COLORS["orange_bpi"],
    "construction": COLORS["vert_bpi"],
    "tourisme":     COLORS["cyan_bpi"],
    "services":     COLORS["jaune_bpi"],
    "transports":   COLORS["rose_bpi"],
}

# Libellés "humains" pour les légendes (avec majuscules + accents).
SECTOR_LABELS = {
    "ensemble":     "Ensemble",
    "industrie":    "Industrie",
    "commerce":     "Commerce",
    "construction": "Construction",
    "tourisme":     "Tourisme",
    "services":     "Services",
    "transports":   "Transports",
}


# ---------------------------------------------------------------------------
# Typographie
# ---------------------------------------------------------------------------

FONT_FAMILY = "DejaVu Sans"   # Substitut libre de Calibri (évite warnings sur Linux)

FONT_SIZES = {
    "title":      14,    # titre du graphique (gras)
    "subtitle":   11,    # "(solde d'opinion en %)"
    "tick":       10,    # graduations des axes
    "legend":     10,    # entrées de légende
    "label":      10,    # labels de dernière valeur sur les courbes
    "source":     8,     # mention "Champ ; Source" en bas
}


# ---------------------------------------------------------------------------
# Dimensions des figures (en pouces, à 200 dpi -> 3200x1800 px max)
# Les graphiques sont insérés à env. 16 cm de large dans le PPTX.
# ---------------------------------------------------------------------------

FIGSIZE_DEFAULT = (8.0, 4.5)   # ratio 16:9 cohérent avec les slides
DPI = 200


# ---------------------------------------------------------------------------
# Texte de pied de page Bpifrance (paramétrable car N change à chaque vague)
# ---------------------------------------------------------------------------

def source_text(n_repondants: int | None = None) -> str:
    """Mention 'Champ ; Source' standardisée Bpifrance."""
    champ = f"Total (N = {n_repondants})" if n_repondants else "Total"
    return f"Champ : {champ} ; Source : Bpifrance Le Lab"


# ---------------------------------------------------------------------------
# Application du style global (à appeler une fois en début de session)
# ---------------------------------------------------------------------------

def apply_bpifrance_style() -> None:
    """
    Applique le style Bpifrance via matplotlib rcParams.

    Idempotent : peut être appelé plusieurs fois sans effet de bord.
    """
    mpl.rcParams.update({
        "font.family":          FONT_FAMILY,
        "font.size":            FONT_SIZES["tick"],
        "axes.titlesize":       FONT_SIZES["title"],
        "axes.titleweight":     "bold",
        "axes.titlelocation":   "left",
        "axes.titlepad":        12,
        "axes.labelsize":       FONT_SIZES["tick"],
        "axes.edgecolor":       COLORS["gris_grille"],
        "axes.linewidth":       0.8,
        "axes.spines.top":      False,
        "axes.spines.right":    False,
        "axes.spines.left":     False,    # pas de bord vertical (style Bpifrance)
        "axes.spines.bottom":   True,
        "axes.grid":            True,
        "grid.color":           COLORS["gris_grille"],
        "grid.linestyle":       "-",
        "grid.linewidth":       0.5,
        "grid.alpha":           0.7,
        "axes.axisbelow":       True,
        "xtick.major.size":     0,        # pas de tirets de graduation
        "ytick.major.size":     0,
        "xtick.color":          COLORS["gris_texte"],
        "ytick.color":          COLORS["gris_texte"],
        "legend.frameon":       False,
        "legend.fontsize":      FONT_SIZES["legend"],
        "figure.facecolor":     COLORS["blanc"],
        "axes.facecolor":       COLORS["blanc"],
        "savefig.facecolor":    COLORS["blanc"],
        "savefig.bbox":         "tight",
        "savefig.dpi":          DPI,
    })
