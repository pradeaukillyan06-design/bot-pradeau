# Bot Pradeau — paris fictifs

Bot d'entraînement en **argent fictif** : il ne parie jamais en vrai. Il lit les marchés de prédiction
(Polymarket, Kalshi, Manifold), note ce qu'il *aurait* parié sur les issues cotées à plus de 97 %,
attend le résultat réel et apprend si ces cotes disent vrai.

- `cerveau.py` : programme chef (un seul programme, un seul cahier d'apprentissage commun).
- `sites/` : un module par site (lecture seule des API publiques, aucun compte).
- `mise.py` : mise choisie par le bot (critère de Kelly sur une proba prudente, garde-fous 25 % / 80 %).
- `etat/etat.json` : tout ce que le bot a observé, parié et appris.
- `tests/test_bot.py` : tests avec un faux Internet (lancés avant chaque passage).
- `.github/workflows/bot.yml` : lance un passage toutes les 15 minutes.

Règles : seuil > 97 % ; chaque cote lue 6 fois et concordante à 0,5 point près ; chaque résultat lu 2 fois.
