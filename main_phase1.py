"""
main_phase1.py
==============

Point d'entrée d'exemple pour la phase 1 (data pipeline).
Permet de lancer une analyse complète et d'afficher tous les indicateurs
calculés en console. À utiliser pour :
- vérifier que l'environnement est correctement configuré
- inspecter rapidement les indicateurs de la dernière vague
- tester l'effet d'un nouveau point ajouté dans le fichier Excel

Usage :
    python main_phase1.py
"""

from __future__ import annotations

import json
from pathlib import Path

from src.data_loader import load_all
from src.indicators import compute_full_report


def main(data_dir: str = "data") -> None:
    print(f"Chargement des données depuis {Path(data_dir).resolve()} ...")
    data = load_all(data_dir)
    print(f"OK — dernière vague observée : {data.last_wave.strftime('%Y-%m')}\n")

    report = compute_full_report(data)

    print(f"=== Rapport d'enquête de conjoncture — vague {report.derniere_vague} ===\n")

    # Indicateurs nationaux ---------------------------------------------------
    print("--- Indicateurs nationaux ---")
    for ind in (report.ca, report.eff, report.carnets_passes, report.carnets_futurs):
        r = ind.rang_hors_crises
        print(f"\n  {ind.nom}")
        print(f"    valeur            : {ind.valeur:+.1f}")
        print(f"    delta semestriel  : {ind.delta_semestriel:+.1f} pts")
        print(f"    delta annuel      : {ind.delta_annuel:+.1f} pts")
        print(f"    écart à la moy LT : {ind.ecart_moyenne_lt:+.1f} pts (LT = {ind.moyenne_lt:+.1f})")
        print(f"    rang hors crises  : {r['rang_croissant']}/{r['sur']}")

    # Secteurs ----------------------------------------------------------------
    print("\n\n--- CA par secteur ---")
    print(f"  Ensemble : {report.secteurs.ensemble:+.1f}")
    for sect, val in report.secteurs.classement_decroissant:
        ds = report.secteurs.delta_semestriel[sect]
        da = report.secteurs.delta_annuel[sect]
        print(f"    {sect:13s}: {val:+6.1f}  (Δsem {ds:+.1f} | Δan {da:+.1f})")

    # Difficultés d'approvisionnement ----------------------------------------
    da_rep = report.diff_appro
    print("\n\n--- Difficultés d'approvisionnement ---")
    print(f"  'Somme oui significativement' : {da_rep.somme_oui_significativement:.1f} %")
    print(f"    Δsem {da_rep.delta_semestriel_somme_oui:+.1f} | Δan {da_rep.delta_annuel_somme_oui:+.1f}")
    print(f"  Répartition actuelle :")
    rep_sorted = sorted(da_rep.repartition_actuelle.items(),
                        key=lambda kv: kv[1], reverse=True)
    for mod, val in rep_sorted:
        print(f"    {val:5.1f}%  {mod}")

    # Sauvegarde JSON pour vérif et pour le LLM en aval ----------------------
    out_path = Path("output") / "report_phase1.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n\nRapport JSON sauvegardé dans : {out_path}")


if __name__ == "__main__":
    main()
