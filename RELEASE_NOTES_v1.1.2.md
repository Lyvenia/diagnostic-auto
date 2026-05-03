# RODIA v1.1.2 — Patch updater

Petit correctif sur le mécanisme de mise à jour automatique.

## Correctifs

- **Fermeture propre lors d'une mise à jour** : la fenêtre de l'ancienne version se ferme désormais automatiquement quand l'installateur se lance, plus besoin de la fermer à la main
- **Sécurité de l'installation** : le script de mise à jour kill explicitement le process RODIA avant d'écraser les fichiers, évitant les erreurs "fichier en cours d'utilisation"
- **Mécanisme Inno Setup** : ajout de `CloseApplications=yes` / `RestartApplications=yes` pour une transition fluide

Aucune action requise — la mise à jour s'installe en 1 clic depuis le bandeau RODIA.
