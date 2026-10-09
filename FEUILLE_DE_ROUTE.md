# Feuille de route du Bot Pradeau

Suivie par la relecture de nuit (Claude, 1h29). Objectif de Killyan : un maximum d'expérience, sur le plus
de sites, pays et marchés possible. Règle pour tout nouveau site : API publique en LECTURE seule, sans compte,
et le site doit donner le RÉSULTAT des marchés terminés (sinon le bot ne peut rien apprendre).
Chaque nouveau module : un fichier dans sites/, des tests avec un faux Internet dans tests/test_bot.py,
puis vérification sur un vrai passage (compteurs dans etat.json -> sites).

## Fait
- Polymarket (États-Unis, international) : marchés en cours + historique (cote 24 h avant la fin).
- Kalshi (États-Unis, régulé) : marchés en cours.
- Manifold (argent virtuel) : marchés en cours + historique. Jamais de mise.
- Limitless (crypto, marchés de 5 min à quelques jours) : marchés en cours.
- Gemini Predictions (États-Unis, régulé) : crypto toutes les 5 min / heures / jours, sport, politique.
- Smarkets (Royaume-Uni) : foot de dizaines de pays, tennis, esport, F1, fléchettes… (relu plus lentement :
  le site limite les lectures rapides ; 20 vérifications par passage).
- ESPN (cotes du bookmaker DraftKings) : 29 ligues de 12 pays (foot européen et sud-américain, Japon,
  Arabie saoudite, Mexique, NFL, NCAA, NBA, NHL, MLB…) + historique (cote de clôture et résultat).
- Futuur (Brésil / international, surtout monnaie de jeu) : foot du monde entier, bitcoin heure par heure.
  Jamais de mise (apprentissage seulement).

## Sondés et écartés pour l'instant (voir outils/sonde.py, branche sonde-resultats)
- Metaculus, Insight Prediction, Overtime, Predict.fun, Opinion : compte ou clé obligatoire.
- PredictIt, Matchbook, Kambi (Unibet…), Bovada : cotes lisibles mais AUCUN résultat après la fin.
- Myriad : monnaie de points, presque aucun marché ouvert. Azuro : ancienne API vide, nouvelle API
  (api.onchainfeed.org) à explorer. Hyperliquid (marchés « outcome ») : résultats introuvables pour l'instant.
- SX Bet : les cotes ne sont plus publiques (« OrderBook V2 is no longer supported »).

## À faire, par ordre d'intérêt
1. Historique Kalshi : chandeliers de prix (/series/{serie}/markets/{ticker}/candlesticks), cote 24 h avant la fin.
2. Historique Limitless : trouver la liste des marchés résolus (status RESOLVED) et l'historique des prix.
3. Azuro (paris sportifs décentralisés) : api.onchainfeed.org/api/v1/public/market-manager (sports,
   games-by-filters avec environment=PolygonUSDT, orderBy, orderDirection, page=1) -> trouver les cotes
   (conditions) et les résultats.
4. Hyperliquid « outcomes » (POST api.hyperliquid.xyz/info, type outcomeMeta + allMids) : trouver le résultat.
5. Smarkets : élargir aux autres catégories de marchés que « winner » si le temps de passage le permet.
6. Bourses d'actions d'autres pays (Europe, États-Unis, Japon…) via les données gratuites accessibles depuis
   GitHub Actions (ex. bibliothèque yfinance), avec le même principe que le bot actions (pari +0,5 % / −20 % / 30 j).
7. Tout autre site public de prédiction ou de paris qui respecte la règle ci-dessus.
