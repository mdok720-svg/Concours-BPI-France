"""
main_phase4.py
==============

Point d'entrée pour la phase 4 : assemblage final du rapport PowerPoint.

Orchestre la chaîne complète phase 1 -> 4 :
1. Chargement des données (data_loader)
2. Calcul des indicateurs (indicators)
3. Génération des graphiques PNG (charts)
4. Génération des commentaires LLM (commentary)
5. Assemblage du PPTX final (report_builder)

Usage :
    python main_phase4.py                    # Gemini flash + assemblage
    python main_phase4.py --pro              # Gemini 2.5 pro
    python main_phase4.py --mock             # commentaires mock (offline)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.data_loader import load_all
from src.indicators import compute_full_report
from src.charts import render_all_charts
from src.commentary import generate_full_commentary
from src.report_builder import build_report


# N de la dernière vague Bpifrance (métadonnée hors donnees.xlsx).
# À mettre à jour à chaque nouvelle vague — ou à rendre dynamique plus
# tard si Bpifrance le fournit dans info_donnees.xlsx.
N_REPONDANTS = 4722

TEMPLATE_PATH = "presentation.pptx"
OUTPUT_PPTX = "output/rapport_conjoncture.pptx"


def main():
    parser = argparse.ArgumentParser(
        description="Construit le rapport PowerPoint complet.")
    parser.add_argument("--mock", action="store_true",
                        help="Commentaires mock (offline, pas d'appel Gemini).")
    parser.add_argument("--pro", action="store_true",
                        help="Utilise gemini-2.5-pro au lieu de flash.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--template", default=TEMPLATE_PATH)
    parser.add_argument("--output", default=OUTPUT_PPTX)
    args = parser.parse_args()

    mode = "mock" if args.mock else "gemini"
    model = "gemini-2.5-pro" if args.pro else "gemini-2.5-flash"

    print("=" * 60)
    print("Phase 1 — Chargement + indicateurs")
    print("=" * 60)
    data = load_all(args.data_dir)
    report = compute_full_report(data)
    print(f"  ✓ vague analysée : {report.derniere_vague}")

    print("\n" + "=" * 60)
    print("Phase 2 — Graphiques")
    print("=" * 60)
    # On désactive la source sur les PNGs : le template PPTX a déjà
    # ses propres mentions "Champ : Total ; Source : ..." bien placées
    # avec la police Bpifrance. Éviter la duplication visuelle.
    charts = render_all_charts(report, n_repondants=N_REPONDANTS,
                               show_source=False)
    for name, path in charts.items():
        print(f"  ✓ {name:12s} -> {path}")

    print("\n" + "=" * 60)
    print(f"Phase 3 — Commentaires (mode={mode}, model={model})")
    print("=" * 60)
    commentary = generate_full_commentary(report, mode=mode, model=model)
    if commentary.hallucination_warnings:
        print(f"  ⚠ {len(commentary.hallucination_warnings)} warnings anti-hallucination :")
        for w in commentary.hallucination_warnings:
            print(f"     - {w}")
    else:
        print("  ✓ aucun chiffre suspect détecté")

    print("\n" + "=" * 60)
    print("Phase 4 — Assemblage PPTX")
    print("=" * 60)
    out = build_report(
        report=report,
        commentary=commentary,
        charts=charts,
        template_path=args.template,
        output_path=args.output,
        n_repondants=N_REPONDANTS,
    )

    print("\n" + "=" * 60)
    print(f"✓ Rapport final généré : {out.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
