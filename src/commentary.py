"""
commentary.py
=============

Wrapper autour de Gemini pour la génération des commentaires du rapport
de conjoncture. Orchestre l'ensemble des appels LLM à partir d'un
FullReport (cf. indicators.py) et produit un FullCommentary prêt à
être injecté dans le PPTX final (phase 4).

Fonctionnalités :
- Client Gemini (SDK google-genai) avec paramètres validés (temp, tokens).
- Mode MOCK pour tester le pipeline sans clé API (retourne du texte
  déterministe construit à partir des métriques).
- Validation anti-hallucination : après génération, on vérifie que les
  nombres cités dans le texte correspondent effectivement à des valeurs
  présentes dans les métriques pré-calculées. Si le LLM a inventé un
  chiffre, on le signale.

Modes :
- mode="mock"    : aucune clé API requise, texte déterministe à partir des métriques.
- mode="gemini"  : vraie requête à l'API Gemini (nécessite GEMINI_API_KEY dans .env).

Auteur : projet challenge Bpifrance — phase 3 (commentaires LLM).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from typing import Literal, Optional

from .indicators import FullReport
from prompts.templates import (
    prompt_slide1_title,
    prompt_slide1_chapeau,
    prompt_slide1_chapeau_droite,
    prompt_ca_eff,
    prompt_carnets_appro,
    prompt_slide2_title,
    prompt_slide2_chapeau,
    prompt_secteurs,
    load_corpus,
)


# ---------------------------------------------------------------------------
# Paramètres Gemini retenus (cf. synthèse globale, section 10)
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_TEMPERATURE = 0.3       # sobre, factuel, reproductible

# Budget tokens généreux : avec les modèles Gemini 2.5, le "thinking"
# interne consomme une partie du budget max_output_tokens. Même quand
# on le désactive (thinking_budget=0 sur Flash), on prévoit large
# pour Pro qui ne permet pas la désactivation.
DEFAULT_MAX_TOKENS = 1500


# ---------------------------------------------------------------------------
# Conteneur des commentaires générés
# ---------------------------------------------------------------------------

@dataclass
class FullCommentary:
    """
    Ensemble structuré des commentaires pour le rapport.
    Injecté tel quel par report_builder.py dans les slots du PPTX.

    Structure alignée sur le template Bpifrance :
    - slide1_title              : titre principal slide 1
    - slide1_chapeau            : 1 phrase verte d'intro (bloc gauche)
    - ca_eff_comment            : 2 puces détaillées CA + Effectifs (bloc gauche)
    - slide1_chapeau_droite     : 1 phrase verte d'intro (bloc droite, offre/demande)
    - carnets_appro_comment     : 2 puces détaillées offre + demande (bloc droite)
    - slide2_title              : titre principal slide 2
    - slide2_chapeau            : 1 phrase verte synthétique (haut du bloc sectoriel)
    - secteurs_comment          : 3-4 puces détaillées par groupe de secteurs
    """
    slide1_title: str
    slide1_chapeau: str
    ca_eff_comment: str
    slide1_chapeau_droite: str
    carnets_appro_comment: str
    slide2_title: str
    slide2_chapeau: str
    secteurs_comment: str

    # Métadonnées utiles pour debug et pour le rapport méthodologique
    model: str = ""
    mode: str = ""                      # "mock" ou "gemini"
    hallucination_warnings: list = None  # liste de warnings détectés

    def __post_init__(self):
        if self.hallucination_warnings is None:
            self.hallucination_warnings = []

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Client Gemini (import paresseux)
# ---------------------------------------------------------------------------

def _get_gemini_client():
    """
    Import paresseux du SDK google-genai. On ne le charge que si on est
    en mode gemini — permet au mode mock de tourner sans installer le SDK.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise RuntimeError(
            "SDK google-genai manquant. Installe-le avec :\n"
            "  pip install google-genai python-dotenv"
        ) from e

    # Chargement .env (pour GEMINI_API_KEY)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass    # dotenv optionnel si la variable est déjà en env

    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY absent. Ajoute-le dans .env à la racine du projet."
        )

    return genai.Client(), types


def _call_gemini(prompt: str,
                 model: str = DEFAULT_MODEL,
                 temperature: float = DEFAULT_TEMPERATURE,
                 max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """
    Appel Gemini unitaire avec les paramètres validés du projet.

    Note sur le 'thinking' : les modèles Gemini 2.5 ont un raisonnement
    interne activé par défaut qui consomme des tokens du budget
    max_output_tokens — ce qui peut tronquer les réponses si le budget
    n'est pas assez large. Pour notre usage (génération de paragraphes
    factuels à partir de chiffres pré-calculés), aucun raisonnement
    complexe n'est nécessaire : on désactive donc le thinking quand
    le modèle le permet. gemini-2.5-pro ne permet PAS la désactivation,
    pour lui on compense par un max_tokens plus élevé.
    """
    client, types = _get_gemini_client()

    config_kwargs = {
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    # Désactiver le thinking sur Flash (supporté) mais pas sur Pro.
    if "flash" in model.lower():
        config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    return (response.text or "").strip()


# ---------------------------------------------------------------------------
# Mode MOCK : génère du texte déterministe à partir des métriques
# ---------------------------------------------------------------------------

def _mock_generate(prompt_kind: str, metrics: dict) -> str:
    """
    Produit du texte déterministe qui respecte la STRUCTURE attendue
    mais sans appeler d'API. Utile pour :
    - tester le pipeline end-to-end sans clé Gemini
    - valider que la phase 4 (assemblage PPTX) reçoit des strings de
      la bonne forme et longueur

    Le texte mock n'imite PAS le style Bpifrance (c'est le rôle du vrai
    LLM), il se contente de décrire factuellement les chiffres.
    """
    wave = metrics["derniere_vague"]
    ca = metrics["ca"]
    eff = metrics["eff"]
    cp = metrics["carnets_passes"]
    cf = metrics["carnets_futurs"]
    da = metrics["diff_appro"]
    sec = metrics["secteurs"]

    if prompt_kind == "slide1_title":
        return (f"[MOCK] Activité et embauches en recul à la vague {wave}, "
                f"carnets de commande encore dégarnis")

    if prompt_kind == "slide1_chapeau":
        return (f"[MOCK] L'activité et les embauches des TPE-PME reculent à la "
                f"vague {wave}, rejoignant leurs plus bas niveaux historiques "
                f"hors crises financière et sanitaire.")

    if prompt_kind == "slide1_chapeau_droite":
        return "[MOCK] La faiblesse de la demande continue de contraindre l'activité des TPE-PME."

    if prompt_kind == "slide2_chapeau":
        return ("[MOCK] Tous les secteurs affichent un indicateur d'activité en "
                "territoire négatif, à des niveaux bien inférieurs à leur moyenne historique.")

    if prompt_kind == "ca_eff":
        return (
            f"[MOCK] Le solde d'opinion sur l'évolution du chiffre d'affaires "
            f"s'établit à {ca['valeur']:+.0f} en {wave}, en recul de "
            f"{abs(ca['delta_semestriel']):.1f} points en 6 mois et de "
            f"{abs(ca['delta_annuel']):.1f} points sur un an. Il s'inscrit à "
            f"{abs(ca['ecart_moyenne_lt']):.1f} points en-deçà de sa moyenne "
            f"historique (+{ca['moyenne_lt']:.1f} sur 2000-2024), atteignant "
            f"son rang {ca['rang_hors_crises']['rang_croissant']} sur "
            f"{ca['rang_hors_crises']['sur']} vagues hors crises.\n\n"
            f"L'indicateur d'emploi recule également. À {eff['valeur']:+.0f}, "
            f"il perd {abs(eff['delta_semestriel']):.1f} points en 6 mois et "
            f"{abs(eff['delta_annuel']):.1f} points sur un an, soit "
            f"{abs(eff['ecart_moyenne_lt']):.1f} points en-deçà de sa moyenne "
            f"historique."
        )

    if prompt_kind == "carnets_appro":
        return (
            f"[MOCK] Côté offre, les difficultés d'approvisionnement "
            f"contraignent significativement l'activité de "
            f"{da['somme_oui_significativement']:.0f}% des TPE-PME "
            f"({da['delta_semestriel_somme_oui']:+.1f} points sur le "
            f"semestre).\n\n"
            f"Côté demande, les carnets de commande passés s'établissent à "
            f"{cp['valeur']:+.0f}, un niveau inférieur de "
            f"{abs(cp['ecart_moyenne_lt']):.1f} points à sa moyenne "
            f"historique ({cp['moyenne_lt']:+.1f}). Les perspectives à 6 mois "
            f"restent dégradées, l'indicateur prévisionnel s'établissant à "
            f"{cf['valeur']:+.0f}."
        )

    if prompt_kind == "slide2_title":
        return (f"[MOCK] La dégradation de l'activité en {wave} s'observe dans "
                f"tous les secteurs, avec une concentration marquée sur le "
                f"{sec['secteur_le_plus_bas'][0].capitalize()}")

    if prompt_kind == "secteurs":
        haut = sec["secteur_le_plus_haut"]
        bas = sec["secteur_le_plus_bas"]
        lignes = "\n".join(
            f"- {nom.capitalize()} : {val:+.0f}" for nom, val in
            sec["classement_decroissant"]
        )
        return (
            f"[MOCK] Tous les secteurs affichent un indicateur d'activité en "
            f"territoire négatif à la vague {wave}, un écart notable par "
            f"rapport aux vagues précédentes.\n\n"
            f"Les {bas[0]} apparaissent comme le secteur le plus touché "
            f"({bas[1]:+.0f}), tandis que les {haut[0]} résistent mieux "
            f"({haut[1]:+.0f}). L'ensemble des TPE-PME s'établit à "
            f"{sec['ensemble']:+.0f}.\n\nRépartition complète :\n{lignes}"
        )

    raise ValueError(f"Type de prompt inconnu : {prompt_kind}")


# ---------------------------------------------------------------------------
# Validation anti-hallucination
# ---------------------------------------------------------------------------

def _extract_numbers(text: str) -> list[float]:
    """
    Extrait tous les nombres cités dans un texte.
    - Capture les entiers, décimaux, signés.
    - Tolère les séparateurs français (virgule décimale, 'minus' unicode).
    - Évite de confondre les plages ("2000-2024") avec des nombres signés :
      un signe n'est valide QUE s'il n'est pas immédiatement précédé
      d'un chiffre (lookbehind négatif).
    """
    # (?<![0-9]) : le signe ne doit pas suivre immédiatement un chiffre
    # (sinon on matcherait le "-" entre 2000 et 2024)
    pattern = re.compile(r"(?<![0-9])[+\-−]?\s?\d+(?:[.,]\d+)?")
    found = []
    for m in pattern.finditer(text):
        raw = m.group(0).replace("−", "-").replace(" ", "").replace(",", ".")
        try:
            found.append(float(raw))
        except ValueError:
            continue
    return found


def _collect_legit_numbers(metrics: dict) -> set[float]:
    """
    Construit l'ensemble des nombres "légitimes" qu'on s'attend à voir
    cités dans les commentaires, dérivés des métriques pré-calculées.
    """
    legit: set[float] = set()

    def add(v):
        """Ajoute la valeur avec tolérance arrondi (entier + 1 décimale)."""
        if v is None:
            return
        try:
            f = float(v)
        except (TypeError, ValueError):
            return
        legit.add(round(f, 1))
        legit.add(round(f))
        legit.add(round(abs(f), 1))
        legit.add(round(abs(f)))

    for key in ("ca", "eff", "carnets_passes", "carnets_futurs"):
        ind = metrics.get(key)
        if not ind:
            continue
        for field in ("valeur", "delta_semestriel", "delta_annuel",
                       "moyenne_lt", "ecart_moyenne_lt"):
            add(ind.get(field))
        rang = ind.get("rang_hors_crises") or {}
        for field in ("rang_croissant", "sur", "min", "max", "mediane"):
            add(rang.get(field))

    da = metrics.get("diff_appro") or {}
    for field in ("somme_oui_significativement",
                   "delta_semestriel_somme_oui",
                   "delta_annuel_somme_oui"):
        add(da.get(field))
    for v in (da.get("repartition_actuelle") or {}).values():
        add(v)

    sec = metrics.get("secteurs") or {}
    add(sec.get("ensemble"))
    for v in (sec.get("valeurs") or {}).values():
        add(v)
    for v in (sec.get("delta_semestriel") or {}).values():
        add(v)
    for v in (sec.get("delta_annuel") or {}).values():
        add(v)

    # On accepte aussi les petits entiers "innocents" qui peuvent
    # apparaître sans hallucination (années, nombre de points, etc.)
    for yr in range(1998, 2030):
        legit.add(float(yr))
    for small in range(0, 11):
        legit.add(float(small))

    return legit


def _validate_numbers(text: str, metrics: dict,
                      tolerance: float = 0.6) -> list[str]:
    """
    Retourne la liste des nombres présents dans `text` qui ne
    correspondent à aucun nombre attendu. tolerance = écart acceptable
    (en absolu) pour tenir compte des arrondis du LLM.
    """
    legit = _collect_legit_numbers(metrics)
    warnings = []
    for n in _extract_numbers(text):
        if any(abs(n - l) <= tolerance for l in legit):
            continue
        warnings.append(f"Chiffre suspect : {n}")
    return warnings


# ---------------------------------------------------------------------------
# Orchestrateur
# ---------------------------------------------------------------------------

def generate_full_commentary(
    report: FullReport,
    mode: Literal["mock", "gemini"] = "mock",
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    verbose: bool = True,
) -> FullCommentary:
    """
    Génère l'ensemble des commentaires à partir d'un FullReport.

    Args:
        report     : rapport issu de compute_full_report() (phase 1).
        mode       : "mock" (offline, déterministe) ou "gemini" (API réelle).
        model      : modèle Gemini à utiliser (ignoré si mode="mock").
        temperature: température d'échantillonnage LLM (0.2-0.4 recommandé).
        max_tokens : plafond de sortie par commentaire.
        verbose    : si True, affiche la progression.

    Returns:
        FullCommentary avec les 6 commentaires générés + warnings
        d'hallucination éventuels.
    """
    metrics = report.to_dict()

    # Table des prompts à générer (clé interne, fonction de prompt)
    tasks = [
        ("slide1_title",          prompt_slide1_title),
        ("slide1_chapeau",        prompt_slide1_chapeau),
        ("ca_eff",                prompt_ca_eff),
        ("slide1_chapeau_droite", prompt_slide1_chapeau_droite),
        ("carnets_appro",         prompt_carnets_appro),
        ("slide2_title",          prompt_slide2_title),
        ("slide2_chapeau",        prompt_slide2_chapeau),
        ("secteurs",              prompt_secteurs),
    ]

    results: dict[str, str] = {}
    warnings_all: list[str] = []
    corpus = load_corpus() if mode == "gemini" else None

    for key, prompt_fn in tasks:
        if verbose:
            print(f"  → {key} ...")
        if mode == "mock":
            text = _mock_generate(key, metrics)
        elif mode == "gemini":
            prompt = prompt_fn(metrics, corpus=corpus)
            text = _call_gemini(prompt, model=model,
                                temperature=temperature, max_tokens=max_tokens)
        else:
            raise ValueError(f"Mode inconnu : {mode}")

        results[key] = text

        # Validation anti-hallucination (désactivée pour les titres et
        # chapeaux qui n'ont pas vocation à contenir de chiffres précis).
        skip_validation = {"slide1_title", "slide2_title",
                           "slide1_chapeau", "slide1_chapeau_droite",
                           "slide2_chapeau"}
        if key not in skip_validation:
            w = _validate_numbers(text, metrics)
            if w:
                warnings_all.extend([f"[{key}] {msg}" for msg in w])

    commentary = FullCommentary(
        slide1_title=results["slide1_title"],
        slide1_chapeau=results["slide1_chapeau"],
        ca_eff_comment=results["ca_eff"],
        slide1_chapeau_droite=results["slide1_chapeau_droite"],
        carnets_appro_comment=results["carnets_appro"],
        slide2_title=results["slide2_title"],
        slide2_chapeau=results["slide2_chapeau"],
        secteurs_comment=results["secteurs"],
        model=model if mode == "gemini" else "mock",
        mode=mode,
        hallucination_warnings=warnings_all,
    )
    return commentary
