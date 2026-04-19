"""
build_corpus.py
===============

Construit un corpus few-shot à partir des PDFs de rapports Bpifrance
présents dans rapports_bpifrance/.

Ce script est à lancer UNE FOIS au setup du projet (et à chaque ajout
de nouveau rapport). Il produit un fichier corpus/fewshot_corpus.json
qui sera utilisé au runtime par prompts/templates.py pour alimenter
les prompts Gemini.

Pourquoi ce design ?
- Le corpus est propriétaire Bpifrance. On évite de dupliquer son
  contenu dans le code source du projet.
- En cas d'ajout d'un rapport (82e, 83e...), il suffit de poser le
  nouveau PDF dans rapports_bpifrance/ et de relancer ce script.
- Les heuristiques d'extraction sont transparentes et ajustables ici.

Principe d'extraction :
1. Convertir chaque PDF en texte brut (pypdf).
2. Découper le texte en "paragraphes" (séquences de lignes sans saut
   double).
3. Filtrer par type d'indicateur via mots-clés + présence de chiffres.
4. Conserver les paragraphes de longueur 2-8 phrases (ni trop court,
   ni trop long pour un few-shot exemple).

Usage :
    python corpus/build_corpus.py

Sortie : corpus/fewshot_corpus.json

Structure du JSON de sortie :
{
  "meta": {"n_rapports": 12, "generated_at": "..."},
  "examples": {
    "ca_eff":       [ {"source": "81e_...", "text": "..."}, ... ],
    "carnets":      [ ... ],
    "diff_appro":   [ ... ],
    "secteurs":     [ ... ],
    "titres":       [ "Stabilisation", "Refroidissement", ... ]
  }
}
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from pypdf import PdfReader
except ImportError as e:
    raise SystemExit(
        "pypdf est requis : pip install pypdf\n"
        "Si tu as déjà python-pptx et pandas installés, c'est juste "
        "un package en plus."
    ) from e


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PDF_DIR = Path("rapports_bpifrance")
OUT_FILE = Path("corpus") / "fewshot_corpus.json"

# Mots-clés par type d'indicateur. Un paragraphe est rattaché à un type
# s'il contient AU MOINS UN mot-clé de sa liste. Les listes sont
# ordonnées par spécificité décroissante (on préfère "carnets de
# commandes" qui est univoque plutôt que "commandes" seul).
KEYWORDS = {
    "ca_eff": [
        "chiffre d'affaires", "chiffre d’affaires",
        "effectifs", "embauches", "indicateur d'emploi",
        "indicateur d’emploi", "indicateur d'activité",
        "indicateur d’activité",
    ],
    "carnets": [
        "carnet de commandes", "carnets de commandes",
        "carnet de commande", "carnets de commande",
    ],
    "diff_appro": [
        "difficultés d'approvisionnement", "difficultés d’approvisionnement",
        "approvisionnement",
    ],
    "secteurs": [
        "industrie", "commerce", "construction",
        "tourisme", "transports", "services",
        "par secteur", "par branche",
    ],
}

# Un paragraphe-candidat doit :
# - faire entre MIN_WORDS et MAX_WORDS (2 à ~8 phrases environ)
# - contenir au moins un nombre (sinon ce n'est pas un commentaire
#   factuel qui cite des chiffres : c'est de l'introduction)
MIN_WORDS = 25
MAX_WORDS = 150

# Nombre max d'exemples conservés par catégorie. On prend les N plus
# "denses en chiffres" (heuristique : plus un paragraphe contient de
# deltas type "X points", plus il est représentatif du style cible).
MAX_EXAMPLES_PER_KIND = 6


# ---------------------------------------------------------------------------
# Extraction PDF -> texte
# ---------------------------------------------------------------------------

def extract_pdf_text(pdf_path: Path) -> str:
    """
    Convertit un PDF en texte brut. On ne fait pas de layout preservation
    ici : l'ordre de lecture naturel suffit, et les paragraphes restent
    séparés par des doubles sauts de ligne.
    """
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages:
        t = page.extract_text() or ""
        parts.append(t)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Découpe en phrases + fenêtrage autour des mots-clés
# ---------------------------------------------------------------------------

# pypdf ne produit pas de sauts de paragraphe fiables. On découpe donc
# directement par phrases, puis on construit des "fenêtres" de 2-4
# phrases consécutives autour de chaque occurrence de mot-clé.

# Sépare sur un point suivi d'un espace puis d'une majuscule OU d'un
# retour ligne. On conserve le point avec la phrase précédente.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀÂÉÈÊÎÔÙÇ])")

# Taille de la fenêtre : phrase matching + N phrases suivantes.
WINDOW_SIZE = 3


def split_sentences(text: str) -> list[str]:
    """
    Découpe un texte en phrases. Étape préalable :
    - On remplace tous les retours à la ligne par des espaces pour
      lisser les sauts de ligne parasites de pypdf.
    - On fusionne les espaces multiples.
    """
    text = re.sub(r"\s+", " ", text)
    # Filtre les traits de page type "TPE-PME │ 81e ENQUÊTE … Bpifrance Le Lab 3"
    # en les remplaçant par un séparateur de phrase.
    text = re.sub(r"\s*Bpifrance Le Lab\s*\d*\s*", ". ", text)
    sentences = _SENTENCE_RE.split(text)
    return [s.strip() for s in sentences if s.strip()]


def build_windows(sentences: list[str],
                  keywords: list[str]) -> list[str]:
    """
    Pour chaque phrase qui contient un keyword, construit une "fenêtre"
    de WINDOW_SIZE phrases (la phrase + les suivantes) et retourne ces
    fenêtres comme extraits candidats.

    Déduplique les fenêtres qui se chevauchent en ne conservant que la
    première d'une séquence consécutive de phrases matching.
    """
    windows = []
    i = 0
    n = len(sentences)
    while i < n:
        s = sentences[i]
        if contains_keywords(s, keywords):
            # Fenêtre : phrase i et les WINDOW_SIZE-1 suivantes
            window_sentences = sentences[i:i + WINDOW_SIZE]
            windows.append(" ".join(window_sentences))
            # On saute la taille de la fenêtre pour éviter les
            # chevauchements trop forts entre exemples successifs.
            i += WINDOW_SIZE
        else:
            i += 1
    return windows


# ---------------------------------------------------------------------------
# Classification & filtrage
# ---------------------------------------------------------------------------

_DIGIT_RE = re.compile(r"\d")
_POINTS_RE = re.compile(r"\b\d+\s*point", re.IGNORECASE)


def count_words(text: str) -> int:
    return len(text.split())


def contains_keywords(text: str, keywords: list[str]) -> bool:
    """True si le paragraphe contient au moins un mot-clé (case-insensitive)."""
    low = text.lower()
    return any(kw.lower() in low for kw in keywords)


def density_score(text: str) -> int:
    """
    Heuristique pour classer la 'qualité' d'un paragraphe : plus il
    contient d'occurrences de "X points", plus il est représentatif
    du style chiffré Bpifrance.
    """
    return len(_POINTS_RE.findall(text))


def is_candidate_paragraph(p: str) -> bool:
    """Filtres de base : longueur + présence d'au moins un chiffre."""
    n = count_words(p)
    if n < MIN_WORDS or n > MAX_WORDS:
        return False
    if not _DIGIT_RE.search(p):
        return False
    return True


def classify(paragraph: str) -> list[str]:
    """
    Retourne la liste des catégories auxquelles un paragraphe appartient.
    Un paragraphe peut relever de plusieurs catégories (ex. un passage
    qui parle à la fois de secteurs ET de carnets).
    """
    return [kind for kind, kws in KEYWORDS.items()
            if contains_keywords(paragraph, kws)]


# ---------------------------------------------------------------------------
# Extraction des titres de rapports (slogan principal)
# ---------------------------------------------------------------------------

# Heuristique : le titre-slogan apparaît dans les premières lignes du
# PDF, en majuscules, entre 1 et 6 mots, et n'est pas "ENQUÊTE DE
# CONJONCTURE" / "JANVIER 2024" / etc.
_BOILERPLATE = {
    "ENQUÊTE DE CONJONCTURE", "SEMESTRIELLE AUPRÈS DES PME",
    "TPE-PME", "BPIFRANCE LE LAB",
}


def extract_title_slogan(text: str) -> Optional[str]:
    """
    Extrait le slogan principal du rapport (ex. "STABILISATION",
    "REFROIDISSEMENT", "LES PME RÉSISTENT GRÂCE À LEUR MARCHÉ
    DOMESTIQUE"). On scanne les 30 premières lignes non vides et on
    prend la plus longue ligne full-caps qui n'est pas du boilerplate.
    """
    candidates = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:30]:
        # Doit être majoritairement en majuscules (certains accents en
        # minuscules toléré, chiffres toléré).
        letters = [c for c in line if c.isalpha()]
        if not letters:
            continue
        upper_ratio = sum(1 for c in letters if c == c.upper()) / len(letters)
        if upper_ratio < 0.9:
            continue
        # Éviter le boilerplate
        if any(bp in line.upper() for bp in _BOILERPLATE):
            continue
        # Éviter les mois/années seuls
        if re.fullmatch(r"[A-ZÉÈÊ]+\s+\d{4}", line):
            continue
        # Éviter les numéros de version
        if re.fullmatch(r"\d+E.*", line):
            continue
        candidates.append(line)
    # Le slogan est généralement le plus long parmi les candidats.
    if not candidates:
        return None
    return max(candidates, key=len)


# ---------------------------------------------------------------------------
# Orchestrateur
# ---------------------------------------------------------------------------

def build_corpus(pdf_dir: Path = PDF_DIR,
                 out_file: Path = OUT_FILE) -> dict:
    """
    Construit le corpus few-shot et l'écrit sur disque.
    Retourne le dict résultant (pour usage programmatique).
    """
    pdf_paths = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_paths:
        raise SystemExit(
            f"Aucun PDF trouvé dans {pdf_dir}/ — place tes rapports "
            f"Bpifrance dans ce dossier et relance."
        )

    # On collecte tous les paragraphes candidats avec leur source.
    # Structure : {kind: [(source, para, density), ...]}
    gathered: dict[str, list[tuple[str, str, int]]] = {k: [] for k in KEYWORDS}
    titres: list[dict[str, str]] = []

    for pdf_path in pdf_paths:
        source_name = pdf_path.stem
        print(f"  lecture de {pdf_path.name} ...")
        try:
            text = extract_pdf_text(pdf_path)
        except Exception as e:
            print(f"    ⚠ échec lecture : {e}")
            continue

        # Titre / slogan (sur le texte brut, avant linéarisation)
        slogan = extract_title_slogan(text)
        if slogan:
            titres.append({"source": source_name, "titre": slogan})

        # Découpage en phrases une fois pour toutes
        sentences = split_sentences(text)

        # Par catégorie : on construit des fenêtres ciblées
        for kind, kws in KEYWORDS.items():
            for window in build_windows(sentences, kws):
                if not is_candidate_paragraph(window):
                    continue
                score = density_score(window)
                gathered[kind].append((source_name, window, score))

    # Pour chaque catégorie : on trie par densité décroissante (plus
    # représentatif d'abord) puis on coupe à MAX_EXAMPLES_PER_KIND. On
    # garde aussi une diversité des sources : on prend au plus 1 exemple
    # par PDF source dans le top-N pour avoir du style varié.
    final: dict[str, list[dict[str, str]]] = {}
    for kind, items in gathered.items():
        items.sort(key=lambda t: t[2], reverse=True)
        selected = []
        seen_sources = set()
        for src, para, score in items:
            if src in seen_sources:
                continue
            selected.append({"source": src, "text": para, "score": score})
            seen_sources.add(src)
            if len(selected) >= MAX_EXAMPLES_PER_KIND:
                break
        final[kind] = selected

    corpus = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "n_rapports": len(pdf_paths),
            "sources": [p.stem for p in pdf_paths],
        },
        "examples": final,
        "titres": titres,
    }

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nCorpus écrit dans : {out_file}")
    for kind, exs in final.items():
        print(f"  {kind:12s} : {len(exs)} exemples")
    print(f"  titres       : {len(titres)} slogans")
    return corpus


if __name__ == "__main__":
    build_corpus()
