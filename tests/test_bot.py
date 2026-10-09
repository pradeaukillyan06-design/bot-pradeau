"""Tests du programme chef avec un faux Internet (données au format réel de chaque site).
Lancer : python tests/test_bot.py"""
import copy
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cerveau as C                      # noqa: E402
import sites.commun as SC                # noqa: E402
from sites import kalshi, limitless, manifold, polymarket  # noqa: E402

T0 = SC.maintenant()
FIN = (T0 + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
FIN_MS = int((T0 + timedelta(days=2)).timestamp() * 1000)

# --- faux marchés -----------------------------------------------------------------
PM = {
    "1": {"id": "1", "slug": "lol-a-b", "question": "LoL: A vs B", "outcomes": '["A", "B"]',
          "outcomePrices": '["0.98", "0.02"]', "endDate": FIN, "volumeNum": 90000, "closed": False,
          "bestBid": 0.979, "bestAsk": 0.981},
    "2": {"id": "2", "slug": "btc-90k", "question": "Bitcoin above 90k?", "outcomes": '["Yes", "No"]',
          "outcomePrices": '["0.02", "0.98"]', "endDate": FIN, "volumeNum": 50000, "closed": False,
          "bestBid": 0.019, "bestAsk": 0.021},
    "4": {"id": "4", "slug": "cs2-x-y", "question": "CS2: X vs Y (déjà joué)", "outcomes": '["X", "Y"]',
          "outcomePrices": '["0.9995", "0.0005"]', "endDate": FIN, "volumeNum": 50000, "closed": False,
          "bestBid": 0.999, "bestAsk": None},
    "3": {"id": "3", "slug": "who-wins", "question": "Who wins?", "outcomes": '["A", "B", "C"]',
          "outcomePrices": '["0.98", "0.01", "0.01"]', "endDate": FIN, "volumeNum": 50000, "closed": False},
}
KA = {"markets": [
    {"ticker": "KXBTC-1", "title": "Bitcoin above 50k", "status": "active", "market_type": "binary",
     "yes_bid_dollars": "0.9800", "yes_ask_dollars": "0.9850", "no_bid_dollars": "0.0150", "no_ask_dollars": "0.0200",
     "close_time": FIN, "volume_fp": "5000.00"},
    {"ticker": "KXWIDE-4", "title": "Spread énorme", "status": "active", "market_type": "binary",
     "yes_bid_dollars": "0.0100", "yes_ask_dollars": "0.9900", "no_bid_dollars": "0.0100", "no_ask_dollars": "0.9900",
     "close_time": FIN, "volume_fp": "5000.00"},
    {"ticker": "KXNBA-2", "title": "Lakers win", "status": "active", "market_type": "binary",
     "yes_bid": 1, "yes_ask": 2, "no_bid": 98, "no_ask": 99, "close_time": FIN, "volume": 5000},   # centimes
    {"ticker": "KXMVECOMBO-3", "title": "combo", "status": "active", "market_type": "binary",
     "yes_bid_dollars": "0.99", "yes_ask_dollars": "0.995", "close_time": FIN, "volume": 5000},
], "cursor": ""}
MA = [{"id": "m1", "slug": "will-x", "question": "Will X happen?", "outcomeType": "BINARY", "probability": 0.985,
       "closeTime": FIN_MS, "isResolved": False, "volume": 1000, "uniqueBettorCount": 40}]

HIST_PM = [{"id": "h1", "slug": "nba-x", "question": "NBA: X vs Y", "outcomes": '["X", "Y"]', "outcomePrices": '["1", "0"]',
            "endDate": FIN, "closedTime": "2026-09-01 20:00:00+00", "umaResolutionStatus": "resolved", "volumeNum": 9e4,
            "clobTokenIds": '["111", "222"]', "closed": True},
           {"id": "h2", "slug": "btc-y", "question": "Bitcoin above 200k?", "outcomes": '["Yes", "No"]', "outcomePrices": '["1", "0"]',
            "endDate": FIN, "closedTime": "2026-09-02 20:00:00+00", "umaResolutionStatus": "resolved", "volumeNum": 9e4,
            "clobTokenIds": '["333", "444"]', "closed": True}]
HIST_MA = [{"id": "r1", "slug": "will-z", "question": "Will Z happen?", "resolution": "NO", "closeTime": FIN_MS,
            "resolutionTime": FIN_MS, "uniqueBettorCount": 50, "outcomeType": "BINARY"}]
LI = [{"slug": "sol-hourly-1", "title": "Solana Up or Down Hourly", "marketType": "single", "status": "FUNDED",
       "prices": [0.985, 0.015], "tradePrices": {"buy": {"market": [0.987, 0.02]}}, "expirationTimestamp": FIN_MS,
       "categories": ["Hourly"], "volumeFormatted": "1910.5", "expired": False},
      {"slug": "btc-5min-2", "title": "BTC Up or Down - 5 Min", "marketType": "single", "status": "FUNDED",
       "prices": [0.98, 0.02], "tradePrices": {"buy": {"market": [0.99, 0.30]}}, "expirationTimestamp": FIN_MS,
       "categories": ["Minutely"], "volumeFormatted": "0", "expired": False}]
ETAT_SITE = {"pm": copy.deepcopy(PM), "ka": copy.deepcopy(KA), "ma": copy.deepcopy(MA), "discord": set()}


def faux_internet(url, *a, **k):
    s = ETAT_SITE
    if "clob.polymarket.com/prices-history" in url:            # jeton 111 : X à 0,985 la veille ; 333 : 0,40
        p = 0.985 if "market=111" in url else 0.40
        fin_obs = int(url.split("endTs=")[1].split("&")[0])
        return {"history": [{"t": fin_obs - 7200, "p": p}, {"t": fin_obs + 3600, "p": 0.999}]}
    if "gamma-api.polymarket.com" in url and "closed=true&limit=" in url and "order=" in url:
        return HIST_PM if "offset=0" in url else []
    if "limitless.exchange" in url:
        if "/markets/active" in url:
            return {"data": LI} if "page=1&" in url else {"data": []}
        return next((m for m in LI if url.endswith(m["slug"])), {})
    if "manifold.markets" in url and "filter=resolved" in url:
        return HIST_MA if "offset=0" in url else []
    if "manifold.markets" in url and "/bets?" in url:
        return [{"createdTime": 1, "probAfter": 0.02}]              # Oui à 2 % -> Non favori à 98 %
    if "gamma-api.polymarket.com" in url:
        if "/markets?" in url and ("closed=false&active=true" in url):
            return list(s["pm"].values()) if "offset=0" in url and "volumeNum" in url else []
        for i, m in s["pm"].items():
            if url.endswith(f"/markets/{i}") or f"id={i}" in url or m["slug"] in url:
                m = copy.deepcopy(m)
                if i in s["discord"] and "slug/" in url:      # une adresse renvoie une cote différente
                    m["outcomePrices"] = '["0.95", "0.05"]'
                return [m] if "?" in url else m
        return []
    if "kalshi.com" in url:
        if "/markets?" in url:
            return s["ka"]
        t = url.rsplit("/", 1)[1]
        return {"market": next((m for m in s["ka"]["markets"] if m["ticker"] == t), {})}
    if "manifold.markets" in url:
        if "search-markets" in url:
            return s["ma"] if "offset=0" in url else []
        return next((m for m in s["ma"] if url.endswith(m["id"]) or url.endswith(m["slug"])), {})
    raise AssertionError("adresse inattendue " + url)


for mod in (polymarket, kalshi, manifold, limitless):
    mod.lire_json = faux_internet
C.CFG["pause_lectures_s"] = 0
ERREURS = []


def verifier(nom, cond):
    print(("OK  " if cond else "ÉCHEC ") + nom)
    if not cond:
        ERREURS.append(nom)


with tempfile.TemporaryDirectory() as d:
    C.ETAT = Path(d) / "etat.json"

    # 1) premier passage : observations seulement (aucune expérience -> pas de mise)
    ETAT_SITE["discord"] = {"2"}
    C.passage()
    e = C.charger()
    obs = {(o["site"], o["id"]) for o in e["observations"]}
    verifier("Polymarket 0,98 vérifié 6 fois -> observé", ("polymarket", "1") in obs)
    verifier("lectures discordantes -> rejeté", ("polymarket", "2") not in obs)
    verifier("marché à 3 issues -> exclu", ("polymarket", "3") not in obs)
    verifier("Kalshi format dollars lu", ("kalshi", "KXBTC-1") in obs)
    verifier("Kalshi format centimes lu (côté Non à 0,985)", ("kalshi", "KXNBA-2") in obs)
    verifier("Kalshi écart achat/vente énorme exclu", ("kalshi", "KXWIDE-4") not in obs)
    verifier("Kalshi combinés exclus", ("kalshi", "KXMVECOMBO-3") not in obs)
    verifier("Manifold observé", ("manifold", "m1") in obs)
    verifier("côté sans vendeur -> pas observé (déjà joué)", ("polymarket", "4") not in obs)
    hist = {(h["site"], h["id"], h["idx"]): h for h in e["historique"]}
    verifier("historique Polymarket : favori 98,5 % la veille, gagnant", hist.get(("polymarket", "h1", 0), {}).get("gagne") == 1)
    verifier("historique : pas de favori > 97 % -> rien noté", not any(k[1] == "h2" for k in hist))
    verifier("historique Manifold : Non à 98 % la veille, gagnant", hist.get(("manifold", "r1", 1), {}).get("gagne") == 1)
    verifier("historique : cote lue AVANT la fin, pas après", hist.get(("polymarket", "h1", 0), {}).get("prix") == 0.985)
    verifier("Limitless lu et observé", ("limitless", "sol-hourly-1") in obs)
    verifier("Limitless écart achat/vente énorme -> pas achetable", ("limitless", "btc-5min-2") not in obs)
    verifier("aucune mise sans expérience", e["ouverts"] == [] and e["cash"] == 1000)
    n_obs = len(e["observations"])

    # 2) second passage : pas de doublon
    C.passage()
    verifier("pas de doublon au 2e passage", len(C.charger()["observations"]) == n_obs)
    verifier("historique : pas de doublon au 2e passage", len(C.charger()["historique"]) == len(e["historique"]))

    # 3) expérience : sur Polymarket, les favoris ~0,98 gagnent à 100 % -> le bot doit miser
    e = C.charger()
    e["observations"] = [o for o in e["observations"] if o["site"] != "polymarket"]
    e["obs_resolues"] += [{"site": "polymarket", "id": f"x{i}", "prix": 0.98, "cat": "esport", "gagne": 1}
                          for i in range(400)]
    C.sauver(e)
    C.passage()
    e = C.charger()
    pari = [o for o in e["ouverts"] if o["site"] == "polymarket" and o["id"] == "1"]
    verifier("avec expérience favorable -> mise sur Polymarket", len(pari) == 1)
    verifier("mise dans les garde-fous", pari and 0 < pari[0]["mise_pct"] <= 0.25)
    verifier("jamais de mise sur Manifold (argent virtuel)", not any(o["site"] == "manifold" for o in e["ouverts"]))
    verifier("cash cohérent", abs(e["cash"] + sum(o["mise"] for o in e["ouverts"]) - 1000) < 0.01)

    # 4) résolutions
    passe = (T0 - timedelta(hours=1)).isoformat()
    e = C.charger()
    for o in e["ouverts"] + e["observations"]:
        o["fin"] = passe
    C.sauver(e)
    ETAT_SITE["pm"]["1"].update(closed=True, umaResolutionStatus="resolved", outcomePrices='["1", "0"]')
    k1 = next(m for m in ETAT_SITE["ka"]["markets"] if m["ticker"] == "KXBTC-1")
    k1.update(status="settled", result="")                         # Kalshi annulé -> remboursé
    k2 = next(m for m in ETAT_SITE["ka"]["markets"] if m["ticker"] == "KXNBA-2")
    k2.update(status="settled", result="yes")                      # le favori (Non) perd
    ETAT_SITE["ma"][0].update(isResolved=True, resolution="MKT", resolutionProbability=0.6)
    LI[0].update(status="RESOLVED", winningOutcomeIndex=1)               # le favori Limitless perd
    mise_pm = pari[0]["mise"]
    cash_avant = e["cash"]
    C.passage()
    e = C.charger()
    r = {(x["site"], x["id"]): x for x in e["resolus"]}
    o = {(x["site"], x["id"]): x for x in e["obs_resolues"]}
    verifier("pari Polymarket gagné et payé", ("polymarket", "1") in r and r[("polymarket", "1")]["gagne"] == 1
             and abs(e["cash"] - (cash_avant + mise_pm / pari[0]["prix"])) < 0.02)
    verifier("Kalshi annulé exclu de l'apprentissage", ("kalshi", "KXBTC-1") not in o)
    verifier("Kalshi favori perdant enregistré", ("kalshi", "KXNBA-2") in o and o[("kalshi", "KXNBA-2")]["gagne"] == 0)
    verifier("Limitless favori perdant enregistré", o.get(("limitless", "sol-hourly-1"), {}).get("gagne") == 0)
    verifier("Manifold résolution partielle exclue", ("manifold", "m1") not in o)
    verifier("plus rien en attente", e["observations"] == [] and e["ouverts"] == [])
    verifier("apprentissage Kalshi mis à jour", e["apprentissage"].get("kalshi|cat:sport US", {}).get("n") == 1)

    # 5) panne d'un site : les autres continuent
    ancien = kalshi.lire_json
    kalshi.lire_json = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("panne"))
    ETAT_SITE["pm"]["9"] = {**PM["1"], "id": "9", "slug": "cs2-c-d", "question": "CS2: C vs D", "closed": False}
    C.passage()
    kalshi.lire_json = ancien
    e = C.charger()
    verifier("panne Kalshi n'arrête pas Polymarket", any(x["id"] == "9" for x in e["observations"] + e["ouverts"]))
    verifier("panne notée dans le journal", any("kalshi" in j["texte"] and "illisible" in j["texte"] for j in e["journal"]))

print("\n" + ("TOUS LES TESTS PASSENT" if not ERREURS else f"{len(ERREURS)} ÉCHEC(S) : {ERREURS}"))
sys.exit(1 if ERREURS else 0)
