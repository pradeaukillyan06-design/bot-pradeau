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
- Azuro (paris sportifs décentralisés, monde entier : France, Japon, Brésil, Turquie…), via
  api.onchainfeed.org (POST conditions-by-game-ids).
- SX Bet (bourse de paris sportifs décentralisée) : carnet d'ordres public v3 (orderbook-v3/snapshot).
- Polymarket US (bourse américaine régulée, distincte de Polymarket) : gateway.polymarket.us.
- Options crypto, observation seulement (probabilité N(d2) tirée de la volatilité, résultat = prix de règlement
  officiel) : Deribit (Panama/Dubaï), OKX (Seychelles), Delta Exchange India et Delta Exchange international,
  Gate, Aevo, Thalex (Gibraltar), Derive (ex-Lyra).
- CBOE (Chicago) : options sur actions américaines (SPY, QQQ, IWM, Apple, Microsoft, Nvidia, Tesla, Amazon),
  observation seulement ; résultat = cours de clôture du jour d'échéance.

## Sondés et écartés pour l'instant (voir outils/sonde.py, branche sonde-resultats)
- Metaculus, Insight Prediction, Overtime, Predict.fun, Opinion : compte ou clé obligatoire.
- PredictIt, Matchbook, Kambi (Unibet…), Bovada : cotes lisibles mais AUCUN résultat après la fin.
- Myriad : monnaie de points, presque aucun marché ouvert. Azuro : ancienne API vide, nouvelle API
  (api.onchainfeed.org) à explorer. Hyperliquid (marchés « outcome ») : résultats introuvables pour l'instant.
- Bybit, Binance (options) : bloqués depuis les serveurs de GitHub (pays). Coincall : règlements non publics.
- HKJC (Hong Kong), TAB (Australie), Betfair, Sportsbet, bwin, FDJ, Sporttery (Chine), Sofascore : bloqués
  ou clé obligatoire. Pinnacle : cotes lisibles mais pas de résultats. PMU : rapports jamais > 97 %.

## Vérification du 9 octobre (chef-1.7)
- Historique : la cote était prise 24 h avant la FERMETURE du marché ; pour un marché fermé tôt (événement déjà
  arrivé) ou tard (résultat connu des jours avant), elle connaissait déjà la fin -> 1 082 favoris gagnants sur
  1 082, trop beau. Désormais : cote 24 h avant la fin PRÉVUE, marchés fermés en avance ignorés. Premier
  résultat honnête : 24 gagnants sur 26 (≈ 92 %). Surveiller ce taux : c'est lui qui règle la confiance du bot.
- ESPN retire les cotes après le match : les résultats sont lus sans elles ; foot = 90 minutes (prolongation ou
  tirs au but -> remboursé). Pas d'historique ESPN possible.
- Résultats introuvables : relus à tour de rôle, abandonnés au bout de 30 jours (pari fictif remboursé).

## À faire, par ordre d'intérêt
1. Historique Kalshi : chandeliers de prix (/series/{serie}/markets/{ticker}/candlesticks), cote 24 h avant la fin.
2. Historique Limitless : trouver la liste des marchés résolus (status RESOLVED) et l'historique des prix.
3. Vérifier sur les premiers résultats réels que Azuro, SX Bet et Polymarket US lisent bien les résultats
   (champs state/wonOutcomeIds, status SETTLED/outcome, state/settlementPx) ; corriger sinon.
4. Hyperliquid « outcomes » (POST api.hyperliquid.xyz/info, type outcomeMeta + allMids) : trouver le résultat.
5. Smarkets : élargir aux autres catégories de marchés que « winner » si le temps de passage le permet.
6. Bourses d'actions d'autres pays (Europe, États-Unis, Japon…) via les données gratuites accessibles depuis
   GitHub Actions (ex. bibliothèque yfinance), avec le même principe que le bot actions (pari +0,5 % / −20 % / 30 j).
7. Tout autre site public de prédiction ou de paris qui respecte la règle ci-dessus.
