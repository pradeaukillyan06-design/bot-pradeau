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

## À faire, par ordre d'intérêt
1. Historique Kalshi : chandeliers de prix (/series/{serie}/markets/{ticker}/candlesticks), cote 24 h avant la fin.
2. Historique Limitless : trouver la liste des marchés résolus (status RESOLVED) et l'historique des prix.
3. SX Bet (bourse de paris sportifs, api.sx.bet) : /markets/active lisible ; trouver la bonne route des cotes
   (/orders/odds/best et son baseToken) et le résultat des marchés réglés (status SETTLED, outcome 1/2/0).
4. Smarkets (bourse de paris britannique, api.smarkets.com/v3) : événements -> marchés -> contrats -> cotes
   (quotes) ; résultat via l'état des contrats (gagnant / perdant).
5. Bourses d'actions d'autres pays (Europe, États-Unis, Japon…) via les données gratuites accessibles depuis
   GitHub Actions (ex. bibliothèque yfinance), avec le même principe que le bot actions (pari +0,5 % / −20 % / 30 j).
6. Tout autre site public de prédiction ou de paris qui respecte la règle ci-dessus.
