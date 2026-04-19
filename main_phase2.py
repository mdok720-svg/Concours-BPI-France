"""
main_phase2.py
==============

Point d'entrée pour la phase 2 (génération des graphiques).

Usage :
    python main_phase2.py
"""

from __future__ import annotations

from pathlib import Path

from src.data_loader import load_all
from src.indicators import compute_full_report
from src.charts import render_all_charts


# N de la dernière vague Bpifrance (à mettre à jour à chaque enquête).
# C'est une constante "métadonnée" qui n'est PAS dans donnees.xlsx.
N_REPONDANTS = 4722


def main(data_dir: str = "data") -> None:
    print(f"Chargement des données depuis {Path(data_dir).resolve()} ...")
    data = load_all(data_dir)
    print(f"OK — vague analysée : {data.last_wave.strftime('%Y-%m')}\n")

    print("Calcul des indicateurs ...")
    report = compute_full_report(data)
    print(f"OK — rapport pour {report.derniere_vague}\n")

    print("Génération des graphiques ...")
    charts = render_all_charts(report, n_repondants=N_REPONDANTS)
    for name, path in charts.items():
        print(f"  ✓ {name:12s} -> {path}")
    print(f"\nDossier de sortie : {Path('output/charts').resolve()}")


if __name__ == "__main__":
    main()
