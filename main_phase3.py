"""
main_phase3.py
==============

Point d'entrée pour la phase 3 (génération des commentaires LLM).

Lance la chaîne phase 1 -> phase 3 : chargement données, calcul
indicateurs, puis génération des commentaires via Gemini (par défaut)
ou en mode mock (offline, sans appel API).

Usage :
    python main_phase3.py                 # Gemini flash (défaut)
    python main_phase3.py --pro           # Gemini 2.5 pro
    python main_phase3.py --mock          # mode offline (pas d'API)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.data_loader import load_all
from src.indicators import compute_full_report
from src.commentary import generate_full_commentary


def main():
    parser = argparse.ArgumentParser(description="Génère les commentaires du rapport.")
    parser.add_argument("--mock", action="store_true",
                        help="Mode mock (pas d'appel API, pour test offline).")
    parser.add_argument("--pro", action="store_true",
                        help="Utilise gemini-2.5-pro au lieu de flash.")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()

    mode = "mock" if args.mock else "gemini"
    model = "gemini-2.5-pro" if args.pro else "gemini-2.5-flash"

    print(f"Chargement des données ...")
    data = load_all(args.data_dir)
    print(f"OK — vague analysée : {data.last_wave.strftime('%Y-%m')}\n")

    print(f"Calcul des indicateurs ...")
    report = compute_full_report(data)
    print(f"OK — rapport pour {report.derniere_vague}\n")

    print(f"Génération des commentaires (mode={mode}, model={model}) ...")
    commentary = generate_full_commentary(report, mode=mode, model=model)

    # Affichage console
    print("\n" + "=" * 70)
    print(f"TITRE SLIDE 1")
    print("=" * 70)
    print(commentary.slide1_title)

    print("\n" + "=" * 70)
    print("CHAPEAU SLIDE 1")
    print("=" * 70)
    print(commentary.slide1_chapeau)

    print("\n" + "=" * 70)
    print("COMMENTAIRE CA + EFFECTIFS")
    print("=" * 70)
    print(commentary.ca_eff_comment)

    print("\n" + "=" * 70)
    print("COMMENTAIRE CARNETS + APPRO")
    print("=" * 70)
    print(commentary.carnets_appro_comment)

    print("\n" + "=" * 70)
    print(f"TITRE SLIDE 2")
    print("=" * 70)
    print(commentary.slide2_title)

    print("\n" + "=" * 70)
    print("COMMENTAIRE SECTORIEL")
    print("=" * 70)
    print(commentary.secteurs_comment)

    # Warnings anti-hallucination
    if commentary.hallucination_warnings:
        print("\n" + "⚠ " * 30)
        print(f"WARNINGS ANTI-HALLUCINATION ({len(commentary.hallucination_warnings)}) :")
        for w in commentary.hallucination_warnings:
            print(f"  - {w}")
    else:
        print("\n✓ Aucun chiffre suspect détecté dans les commentaires.")

    # Sauvegarde JSON
    out_path = Path("output") / "commentary_phase3.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(
        json.dumps(commentary.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nCommentaires sauvegardés dans : {out_path}")


if __name__ == "__main__":
    main()
