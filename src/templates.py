"""
prompts/templates.py
====================

Centralise tous les prompts envoyés à Gemini pour la génération des
commentaires du rapport de conjoncture.

Design :
- Un prompt = une fonction qui prend en entrée des métriques pré-
  calculées (dict issu de FullReport.to_dict()) + le corpus few-shot,
  et retourne la chaîne complète à envoyer au modèle.
- Les métriques sont injectées sous forme de JSON lisible dans le
  prompt (pas de recalcul côté LLM = anti-hallucination).
- Les exemples few-shot sont chargés depuis corpus/fewshot_corpus.json
  (généré une fois par corpus/build_corpus.py).
- Chaque prompt impose un format de sortie strict : UNIQUEMENT le
  texte demandé, pas de préambule ni de postambule.

Auteur : projet challenge Bpifrance — phase 3 (commentaires LLM).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Chargement du corpus few-shot (lazy, une seule fois)
# ---------------------------------------------------------------------------

_CORPUS_PATH_DEFAULT = Path("corpus/fewshot_corpus.json")
_corpus_cache: Optional[dict] = None


def load_corpus(path: Path = _CORPUS_PATH_DEFAULT) -> dict:
    """Charge le corpus few-shot (avec cache pour éviter relectures)."""
    global _corpus_cache
    if _corpus_cache is None:
        if not path.exists():
            raise FileNotFoundError(
                f"Corpus few-shot introuvable : {path}\n"
                f"Lance d'abord : python corpus/build_corpus.py"
            )
        _corpus_cache = json.loads(path.read_text(encoding="utf-8"))
    return _corpus_cache


def _fewshot_block(kind: str, n: int = 2,
                   corpus: Optional[dict] = None) -> str:
    """
    Renvoie un bloc de texte avec n exemples few-shot du corpus pour
    la catégorie demandée. Formaté pour insertion dans le prompt.
    """
    corpus = corpus or load_corpus()
    examples = corpus.get("examples", {}).get(kind, [])[:n]
    if not examples:
        return "(Aucun exemple few-shot disponible)"
    parts = []
    for i, ex in enumerate(examples, 1):
        parts.append(f"Exemple {i} (source : {ex['source']}) :\n{ex['text']}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Rôle système commun — à préfixer à chaque prompt
# ---------------------------------------------------------------------------

SYSTEM_ROLE = """Tu es analyste à la direction des études de Bpifrance (Le Lab), \
spécialiste des enquêtes de conjoncture auprès des TPE-PME françaises. Tu rédiges \
des commentaires factuels, sobres, au registre économique, dans le style codifié \
des publications Bpifrance.

Règles de style à respecter STRICTEMENT :
- Ton factuel et mesuré, registre économique.
- Formulations types : "l'indicateur s'établit à...", "il recule/progresse de X \
points en 6 mois et Y points sur un an", "X points en-deçà de sa moyenne historique", \
"en territoire négatif/positif".
- Modalisation prudente pour les projections : conditionnel ("resterait", "s'établirait").
- Ne JAMAIS inventer de chiffres. N'utiliser QUE les valeurs fournies dans les données.
- Pas de préambule ("Voici le commentaire..."), pas de postambule ("J'espère...").
- Pas de bullet points, du texte en prose.
- N'utiliser que les chiffres fournis dans le bloc DONNÉES ci-dessous.

RÈGLE CRITIQUE SUR LE FORMATAGE :
- N'utilise JAMAIS de markdown. Pas d'astérisques (**texte** ou *texte*), pas de \
souligné, pas de gras markdown. Le texte doit être en prose brute.
- La mise en forme (gras, couleurs) est gérée automatiquement par l'outil qui \
affichera ton texte. Ton rôle est de produire du français sans décoration typographique.
- Écris tes phrases avec des points SÉPARANT BIEN les idées, pour que l'outil puisse \
reconnaître les limites de phrases. Une phrase courte d'accroche suivie d'un point, \
puis des phrases de détails : c'est le pattern attendu."""


# ---------------------------------------------------------------------------
# 1. Titre de la slide 1
# ---------------------------------------------------------------------------

def prompt_slide1_title(metrics: dict, corpus: Optional[dict] = None) -> str:
    """
    Génère le titre de la slide 1 — phrase évocatrice, 1 ligne.
    Exemples cibles : "l'activité et les embauches continuent de se tasser",
    "Les PME remontent la pente", "Stabilisation".
    """
    corpus = corpus or load_corpus()
    titres_ex = corpus.get("titres", [])[:8]
    titres_str = "\n".join(f"- {t['titre']} ({t['source']})"
                           for t in titres_ex)

    # Résumé ultra-compact des faits saillants pour guider le titre
    ca = metrics["ca"]
    eff = metrics["eff"]
    carnets = metrics["carnets_passes"]
    faits = (
        f"- Chiffre d'affaires : {ca['valeur']:+.0f} "
        f"(Δsem {ca['delta_semestriel']:+.1f}, Δan {ca['delta_annuel']:+.1f}, "
        f"rang hors crises {ca['rang_hors_crises']['rang_croissant']}/"
        f"{ca['rang_hors_crises']['sur']})\n"
        f"- Effectifs : {eff['valeur']:+.0f} "
        f"(Δsem {eff['delta_semestriel']:+.1f}, Δan {eff['delta_annuel']:+.1f})\n"
        f"- Carnets passés : {carnets['valeur']:+.0f} "
        f"(moyenne LT : {carnets['moyenne_lt']:+.1f})"
    )

    return f"""{SYSTEM_ROLE}

TÂCHE : Rédige le titre principal de la slide 1 du rapport.

CONTRAINTES STRICTES :
- UNE seule phrase, entre 10 et 18 mots.
- Le titre sera affiché en gros caractères (44pt) et doit tenir sur \
2 LIGNES MAX dans la slide.
- Compte tes mots avant de répondre. Si tu dépasses 18 mots, reformule plus court.
- Ton évocateur mais sobre (pas d'alarmisme, pas d'enthousiasme).
- Doit synthétiser la tendance globale (activité + effectifs + carnets).
- Exemples de titres Bpifrance passés :
{titres_str}

FAITS SAILLANTS DE LA VAGUE {metrics['derniere_vague']} :
{faits}

Produis UNIQUEMENT le titre, sans guillemets ni ponctuation finale."""


# ---------------------------------------------------------------------------
# 2. Chapeau de la slide 1 (lead paragraph)
# ---------------------------------------------------------------------------

def prompt_slide1_chapeau(metrics: dict, corpus: Optional[dict] = None) -> str:
    """
    Génère le chapeau de la slide 1 : UNE phrase unique qui synthétise
    les grandes tendances activité + embauches.
    """
    fewshot = _fewshot_block("ca_eff", n=1, corpus=corpus)

    ca = metrics["ca"]
    eff = metrics["eff"]
    resume = (
        f"- CA : {ca['valeur']:+.0f}, moyenne LT {ca['moyenne_lt']:+.1f}, "
        f"rang {ca['rang_hors_crises']['rang_croissant']}/"
        f"{ca['rang_hors_crises']['sur']} hors crises.\n"
        f"- Effectifs : {eff['valeur']:+.0f}, moyenne LT {eff['moyenne_lt']:+.1f}, "
        f"rang {eff['rang_hors_crises']['rang_croissant']}/"
        f"{eff['rang_hors_crises']['sur']} hors crises."
    )

    return f"""{SYSTEM_ROLE}

TÂCHE : Rédige le chapeau d'introduction de la slide 1 en UNE SEULE PHRASE \
qui résume la tendance globale de l'activité et des embauches en \
{metrics['derniere_vague']}.

CONTRAINTES STRICTES :
- UNE seule phrase, 25-40 mots. Pas deux, pas trois : UNE.
- Un seul point final à la fin. Pas de point intermédiaire.
- Ne cite que les indicateurs d'ACTIVITÉ et d'EMPLOI (pas les carnets, pas les secteurs).
- Mentionne si les indicateurs atteignent un plus bas niveau historique \
(préciser "hors crises financière et sanitaire" si pertinent).
- Pas de chiffres précis (pas de "-14", pas de "-3 points") : c'est un résumé qualitatif.

EXEMPLE DE FORMAT ATTENDU (référence réelle Bpifrance) :
"Les indicateurs d'activité et d'embauches repartent à la baisse au second \
semestre, rejoignant leurs plus bas niveaux historiques hors crises financière \
et sanitaire."

EXEMPLE DE STYLE LLM (extrait réel Bpifrance) :
{fewshot}

DONNÉES DE LA VAGUE {metrics['derniere_vague']} :
{resume}

Produis UNIQUEMENT la phrase, sans guillemets ni préambule."""


# ---------------------------------------------------------------------------
# 3. Commentaire CA + Effectifs (le gros paragraphe)
# ---------------------------------------------------------------------------

def prompt_ca_eff(metrics: dict, corpus: Optional[dict] = None) -> str:
    """
    Génère le commentaire détaillé sur CA + Effectifs.

    STRUCTURE IMPOSÉE : 2 paragraphes-puces, chacun commençant par une
    phrase d'accroche courte (qui sera mise en gras par report_builder.py)
    suivie des détails chiffrés.
    """
    fewshot = _fewshot_block("ca_eff", n=2, corpus=corpus)

    # Bloc données : JSON compact, lisible
    ca = metrics["ca"]
    eff = metrics["eff"]
    data_block = json.dumps({
        "chiffre_affaires": ca,
        "effectifs": eff,
    }, ensure_ascii=False, indent=2)

    return f"""{SYSTEM_ROLE}

TÂCHE : Rédige le commentaire détaillé sur l'évolution du chiffre d'affaires \
et des effectifs pour la vague {metrics['derniere_vague']}.

STRUCTURE OBLIGATOIRE : 2 paragraphes-puces séparés par UNE LIGNE VIDE.
Chaque paragraphe-puce commence par une PHRASE D'ACCROCHE courte (10-15 mots, \
qui sera mise en gras) suivie d'une ou deux phrases chiffrées détaillées.

PATRON EXACT à reproduire pour chaque paragraphe :
"[Accroche courte sur la tendance : verbe fort, ton factuel]. [Détails chiffrés : \
valeur actuelle, delta semestriel, delta annuel, comparaison à la moyenne LT, \
rang historique si pertinent]."

EXEMPLES D'ACCROCHES VALIDES :
- "Le solde d'opinion relatif à l'évolution du chiffre d'affaires fléchit ce semestre."
- "L'indicateur d'activité atteint un plus bas niveau historique."
- "Les embauches reculent à un rythme inédit hors crises."

ORDRE des détails chiffrés (après l'accroche) :
1. Valeur actuelle : "Il s'établit à X"
2. Delta semestriel : "en recul de X points en 6 mois"
3. Delta annuel : "et de X points sur un an"
4. Comparaison moyenne LT : "soit X points en-deçà de sa moyenne historique"
5. Si rang hors crises ≤ 3 : "atteignant son plus bas niveau historique hors \
crises financière de 2008-09 et sanitaire de 2020"

CONTRAINTES :
- 140-200 mots au total.
- Utiliser UNIQUEMENT les chiffres du bloc DONNÉES ci-dessous.
- PAS de tirets ni de bullets au début des paragraphes : le template les ajoute \
automatiquement.

EXEMPLES DE STYLE (extraits réels Bpifrance) :
{fewshot}

DONNÉES (ne citer que ces chiffres) :
```json
{data_block}
```

Produis UNIQUEMENT les 2 paragraphes, sans titre ni préambule, séparés par \
une ligne vide."""


# ---------------------------------------------------------------------------
# 4. Commentaire Carnets de commande + Difficultés d'appro
# ---------------------------------------------------------------------------

def prompt_slide1_chapeau_droite(metrics: dict, corpus: Optional[dict] = None) -> str:
    """
    Chapeau du bloc droite de la slide 1 : UNE phrase qui introduit la
    tension "offre vs demande" avant les puces détaillées.
    """
    da = metrics["diff_appro"]
    cp = metrics["carnets_passes"]
    return f"""{SYSTEM_ROLE}

TÂCHE : Rédige le chapeau du bloc droit de la slide 1 en UNE SEULE PHRASE \
qui introduit la tension "offre / demande".

CONTRAINTES STRICTES :
- UNE seule phrase, 10-20 mots.
- Un seul point final. Pas de point intermédiaire.
- Pas de chiffres précis : c'est un résumé qualitatif.
- Évoquer soit l'insuffisance de la demande, soit la pression des difficultés \
d'approvisionnement (selon laquelle est la plus marquante).

EXEMPLES DE FORMAT ATTENDU (références réelles Bpifrance) :
"La faiblesse de la demande continue de contraindre l'activité des TPE-PME."
"L'insuffisance de la demande reste le premier frein à l'activité."

DONNÉES DE LA VAGUE {metrics['derniere_vague']} :
- Carnets de commande passés : {cp['valeur']:+.0f} (moyenne LT : {cp['moyenne_lt']:+.1f})
- Difficultés d'approvisionnement significatives : {da['somme_oui_significativement']:.0f} % \
(variation semestrielle : {da['delta_semestriel_somme_oui']:+.1f} pts)

Produis UNIQUEMENT la phrase, sans guillemets ni préambule."""


def prompt_carnets_appro(metrics: dict, corpus: Optional[dict] = None) -> str:
    """
    Commentaire combiné "côté offre / côté demande" :
    - Offre : difficultés d'approvisionnement
    - Demande : carnets de commande (passés + futurs)

    STRUCTURE IMPOSÉE : 2 paragraphes-puces, chacun commençant par une
    phrase d'accroche courte (qui sera rendue en gras par report_builder.py)
    suivie des détails chiffrés.
    """
    fewshot_carnets = _fewshot_block("carnets", n=1, corpus=corpus)
    fewshot_appro = _fewshot_block("diff_appro", n=1, corpus=corpus)

    data_block = json.dumps({
        "carnets_passes": metrics["carnets_passes"],
        "carnets_futurs": metrics["carnets_futurs"],
        "diff_appro": metrics["diff_appro"],
    }, ensure_ascii=False, indent=2)

    return f"""{SYSTEM_ROLE}

TÂCHE : Rédige le commentaire "offre vs demande" pour la vague \
{metrics['derniere_vague']}. Il couvre deux facettes :
- Côté OFFRE : difficultés d'approvisionnement.
- Côté DEMANDE : carnets de commande (passés et futurs).

STRUCTURE OBLIGATOIRE : 2 paragraphes exactement, séparés par UNE LIGNE VIDE.
Chaque paragraphe commence par une phrase d'accroche courte (qui sera mise \
en gras) suivie d'une explication chiffrée détaillée dans la même phrase ou \
la suivante.

PATRON EXACT à reproduire :
Paragraphe 1 : "Du côté de l'offre, [accroche synthétique]. [Détails chiffrés avec \
delta semestriel, delta annuel]."
Paragraphe 2 : "Du côté de la demande, [accroche synthétique]. [Détails sur \
carnets passés + futurs, valeurs, comparaisons moyenne LT]."

CONTRAINTES :
- 100-150 mots au total.
- Utiliser UNIQUEMENT les chiffres du bloc DONNÉES.
- PAS de tirets ou de bullets au début des paragraphes : le template les ajoute automatiquement.

EXEMPLES DE STYLE (extraits réels Bpifrance) :

Sur les carnets :
{fewshot_carnets}

Sur l'approvisionnement :
{fewshot_appro}

DONNÉES :
```json
{data_block}
```

Produis UNIQUEMENT les 2 paragraphes, sans titre ni préambule, séparés \
par une ligne vide."""


# ---------------------------------------------------------------------------
# 5. Titre de la slide 2 (sectorielle)
# ---------------------------------------------------------------------------

def prompt_slide2_title(metrics: dict, corpus: Optional[dict] = None) -> str:
    """
    Titre de la slide 2 : doit évoquer l'analyse sectorielle.
    Exemples cibles : "La dégradation de la conjoncture s'observe dans tous
    les secteurs", "Une éclaircie du côté de l'Industrie et du Commerce".
    """
    secteurs = metrics["secteurs"]
    # Mini-résumé des valeurs sectorielles triées
    ligne_sect = ", ".join(
        f"{s}: {v:+.0f}" for s, v in secteurs["classement_decroissant"]
    )

    return f"""{SYSTEM_ROLE}

TÂCHE : Rédige le titre principal de la slide 2 (analyse sectorielle du CA).

CONTRAINTES STRICTES :
- UNE seule phrase, entre 10 et 18 mots.
- Le titre sera affiché en gros caractères (44pt) et doit tenir sur \
2 LIGNES MAX dans la slide.
- Compte tes mots avant de répondre. Si tu dépasses 18 mots, reformule plus court.
- Doit caractériser la dispersion/convergence des secteurs.
- Ton évocateur mais sobre.
- Si tous les secteurs sont en territoire négatif, l'exprimer (homogénéité baissière).
- Si un secteur se démarque fortement, le nommer (ex. "Le Tourisme s'effondre").

EXEMPLES DE TITRES BPIFRANCE PASSÉS :
- "La dégradation de la conjoncture s'observe dans tous les secteurs"
- "Une éclaircie du côté de l'Industrie et du Commerce"
- "Le tourisme et les services aux extrêmes d'une conjoncture sectorielle majoritairement négative"

DONNÉES — CA par secteur à la vague {metrics['derniere_vague']} (solde d'opinion en %) :
Ensemble : {secteurs['ensemble']:+.0f}
Secteurs : {ligne_sect}
Extrêmes : {secteurs['secteur_le_plus_haut'][0]} ({secteurs['secteur_le_plus_haut'][1]:+.0f}) \
vs {secteurs['secteur_le_plus_bas'][0]} ({secteurs['secteur_le_plus_bas'][1]:+.0f})

Produis UNIQUEMENT le titre, sans guillemets ni ponctuation finale."""


# ---------------------------------------------------------------------------
# 6. Commentaire sectoriel détaillé
# ---------------------------------------------------------------------------

def prompt_slide2_chapeau(metrics: dict, corpus: Optional[dict] = None) -> str:
    """
    Chapeau vert de la slide 2 : UNE phrase qui caractérise la dynamique
    sectorielle globale. Apparaîtra en vert en haut du bloc, sous forme
    de première puce.
    """
    secteurs = metrics["secteurs"]
    return f"""{SYSTEM_ROLE}

TÂCHE : Rédige le chapeau introductif de la slide 2 (analyse sectorielle) \
en UNE SEULE PHRASE synthétique.

CONTRAINTES STRICTES :
- UNE seule phrase, 15-30 mots.
- Un seul point final.
- Caractériser la tendance globale des secteurs (ex. "Tous les secteurs en \
territoire négatif", "Dynamiques contrastées", "Dégradation généralisée").
- Pas de chiffres précis.

EXEMPLE DE FORMAT ATTENDU (référence réelle Bpifrance) :
"Tous les secteurs affichent un indicateur d'activité en territoire négatif \
et en baisse sur un an, bien loin de leur moyenne historique."

DONNÉES :
- Ensemble : {secteurs['ensemble']:+.0f}
- Plus haut : {secteurs['secteur_le_plus_haut'][0]} ({secteurs['secteur_le_plus_haut'][1]:+.0f})
- Plus bas : {secteurs['secteur_le_plus_bas'][0]} ({secteurs['secteur_le_plus_bas'][1]:+.0f})

Produis UNIQUEMENT la phrase, sans guillemets ni préambule."""


def prompt_secteurs(metrics: dict, corpus: Optional[dict] = None) -> str:
    """
    Commentaire sectoriel détaillé de la slide 2.

    STRUCTURE IMPOSÉE : 3 à 4 paragraphes-puces, chacun traitant un
    REGROUPEMENT de secteurs ayant une dynamique similaire. Chaque
    paragraphe commence par une phrase d'accroche courte (qui sera mise
    en gras) suivie de l'analyse chiffrée.
    """
    fewshot = _fewshot_block("secteurs", n=2, corpus=corpus)

    data_block = json.dumps({
        "secteurs": metrics["secteurs"],
    }, ensure_ascii=False, indent=2)

    return f"""{SYSTEM_ROLE}

TÂCHE : Rédige le commentaire sectoriel détaillé pour la vague \
{metrics['derniere_vague']}.

STRUCTURE OBLIGATOIRE : 3 à 4 paragraphes-puces, séparés par UNE LIGNE VIDE.
Chaque paragraphe-puce commence par une phrase d'accroche courte (qui sera \
mise en gras) suivie d'une explication chiffrée.

REGROUPEMENTS RECOMMANDÉS (à adapter aux données) :
- Industrie + Commerce (quand proches)
- Tourisme + Services + Transports (quand proches)
- Construction (souvent à part)
Laisse les DONNÉES guider les regroupements : regroupe les secteurs dont les \
valeurs et deltas sont proches. Le secteur le PLUS TOUCHÉ mérite souvent son \
propre paragraphe.

PATRON DE CHAQUE PARAGRAPHE :
"[Accroche synthétique sur le groupe]. [Détails chiffrés : valeurs, deltas \
semestriels et annuels, comparaison à la moyenne LT]."

CONTRAINTES :
- 180-260 mots au total.
- Utiliser UNIQUEMENT les chiffres du bloc DONNÉES.
- PAS de tirets ni de bullets au début des paragraphes.

EXEMPLES DE STYLE (extraits réels Bpifrance) :
{fewshot}

DONNÉES :
```json
{data_block}
```

Produis UNIQUEMENT les 3 ou 4 paragraphes, sans titre ni préambule, \
séparés par des lignes vides."""
