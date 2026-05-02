# RODIA v1.1.0 — Refonte premium

Refonte visuelle et fonctionnelle complète de l'interface, alignée sur l'identité de marque Lyvenia (cream + terracotta), avec ajout de fonctionnalités majeures pour les gestionnaires de flotte.

## Nouveautés

### Tableau de bord repensé
- **Hero personnalisé** : « Bonjour [vous] » + résumé dynamique des alertes du jour
- **Bandeau d'alerte critique** : remonte la panne urgente la plus récente avec CTA direct
- **4 KPI cards avec sparklines** : flotte active, diagnostics ce mois, alertes urgentes, score fiabilité moyen
- **Liste véhicules compacte** triée par criticité (les + critiques en premier)
- **Activity feed** : timeline des événements récents (diagnostics, alertes, maintenance)
- **Graphique SVG** : évolution du score fiabilité moyen sur 30 jours

### Mode « Bilan de santé » (en plus du diagnostic de panne)
- Welcome card avec **2 choix au démarrage** : Diagnostic de panne / Bilan de santé
- 4 sous-types de bilan : pré-achat, périodique, pré-CT, pré-route longue
- L'IA adapte son analyse selon le type (cause racine vs scoring préventif)
- PDF différencié : « Bilan de santé véhicule » + plan de maintenance recommandée

### Wizard de diagnostic refondu
- **Rail vertical sticky** à gauche du contenu (étapes Lecture / Contexte / Ralenti / Roulant / Analyse)
- **Anamnèse en accordéon progressif** : une question à la fois, révélation en cascade selon les réponses
- Branchement intelligent (skip de la question « quand survient » si véhicule ne démarre pas)
- Bouton « Tout déplier » pour les techniciens experts
- Résumé compact des sections déjà remplies

### Nouvelles fonctionnalités
- **Recherche globale** (`Ctrl+K`) — command palette qui cherche dans véhicules, codes DTC, techniciens, et propose des actions rapides
- **Menu utilisateur** — modifier son nom, basculer le thème, réinitialiser le profil
- **Centre d'aide** — raccourcis clavier, tour guidé interactif de l'application, signalement de bug avec rapport système
- **Tour guidé** : visite interactive de 6 étapes pour découvrir l'app

### Améliorations UI
- **Mode sombre warm** repensé (fond vert encre + accent saumon) au lieu du dark générique
- **Topbar premium** : brand mark, search globale, notifications, thème, avatar
- **Nouvelle palette** alignée sur l'identité Lyvenia (cream + terracotta)
- **Typographie** : Inter avec features OpenType (cv02, cv03, cv11, ss01) + tabular-nums

### Améliorations PDF
- **Pagination intelligente** : `KeepTogether` sur les blocs sémantiques, `keepWithNext` sur les titres, `widows`/`orphans` sur les paragraphes — fini les coupures bizarres
- **Palette adaptée** : titre éditorial sobre + sections avec barre latérale terracotta
- **Suppression complète des emojis** (qui apparaissaient en carrés vides dans le PDF)
- **DTC chips en monospace** terracotta (plus lisibles)

### Backend
- Nouveau endpoint `/api/support/diagnostic` (rapport système pour le bouton « Signaler un problème »)
- Endpoint `/api/support/erase-all` (zone de danger Paramètres)
- Persistance du `type` (panne / contrôle) dans l'historique des diagnostics

## Notes techniques

- Aucune migration de données nécessaire — la flotte existante reste intacte
- Compatibilité ascendante : les diagnostics enregistrés avant la 1.1.0 sont par défaut considérés en mode « panne »
- Le toggle de thème est désormais persisté en localStorage
