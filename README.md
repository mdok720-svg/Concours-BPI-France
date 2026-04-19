# Concours BPI France

Projet Python pour générer un rapport PowerPoint Bpifrance à partir de données, de graphiques et de commentaires générés.

## Prérequis

- Python 3.11+ recommandé
- Git

## Installation

1. Cloner le dépôt :
   ```bash
   git clone https://github.com/mdok720-svg/Concours-BPI-France.git
   cd Concours-BPI-France
   ```
2. Installer les dépendances :
   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

## Utilisation

Le point d’entrée principal est `main.py`.

### Exemple de lancement

```bash
python main.py --mock
```

Options disponibles :

- `--mock` : utilise des commentaires mock hors-ligne, sans appel à l’API Gemini
- `--pro` : utilise le modèle `gemini-2.5-pro` au lieu de `gemini-2.5-flash`
- `--data-dir` : dossier des données (par défaut `data`)
- `--template` : chemin vers le modèle PowerPoint (par défaut `presentation.pptx`)
- `--output` : chemin de sortie du PPTX généré (par défaut `output/rapport_conjoncture.pptx`)

### Exemple complet

```bash
python main.py --mock --output output/rapport_conjoncture_mock.pptx
```

## Configuration Gemini

Si tu veux utiliser le mode Gemini réel, ajoute un fichier `.env` contenant tes variables d’environnement Google Cloud. Le module `src.commentary` charge `dotenv` si nécessaire.

## CI GitHub

Une action GitHub est configurée dans `.github/workflows/python.yml` pour :

- installer les dépendances
- exécuter `python main.py --mock`

Cela permet de vérifier automatiquement que le projet reste exécutable.

[![CI](https://github.com/mdok720-svg/Concours-BPI-France/actions/workflows/python.yml/badge.svg)](https://github.com/mdok720-svg/Concours-BPI-France/actions/workflows/python.yml)
