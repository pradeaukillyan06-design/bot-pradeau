"""Outils partagés par tous les modules de sites."""
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

AGENT = "BotPradeau/1.0 (paper trading, lecture seule)"


def maintenant():
    return datetime.now(timezone.utc)


def lire_json(url, essais=3, pause=2.0, corps=None):
    """Lecture JSON (GET, ou POST de lecture quand `corps` est donné, ex. GraphQL) avec quelques nouvelles
    tentatives. Lève une exception si tout échoue."""
    derniere = None
    for i in range(essais):
        try:
            entetes = {"User-Agent": AGENT, "Accept": "application/json"}
            donnees = None
            if corps is not None:
                donnees = json.dumps(corps).encode("utf-8")
                entetes["Content-Type"] = "application/json"
            req = urllib.request.Request(url, data=donnees, headers=entetes)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            derniere = e
            if e.code == 429:                    # « trop de lectures » : on attend plus longtemps avant de relire
                try:
                    attente = float(e.headers.get("Retry-After") or 0)
                except ValueError:
                    attente = 0
                time.sleep(min(30.0, max(attente, 5.0 * (i + 1))))
            elif 400 <= e.code < 500:
                break                            # adresse refusée ou inexistante : inutile d'insister
            else:
                time.sleep(pause * (i + 1))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            derniere = e
            time.sleep(pause * (i + 1))
    raise RuntimeError(f"lecture impossible : {url} ({derniere})")


def date_iso(x):
    """Accepte ISO texte, millisecondes ou secondes ; renvoie un datetime UTC ou None."""
    if x in (None, ""):
        return None
    if isinstance(x, (int, float)):
        return datetime.fromtimestamp(x / 1000 if x > 1e11 else x, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except ValueError:
        return None


def nombre(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def categorie(texte, slug=""):
    """Catégorie lisible à partir du nom du marché (commune à tous les sites)."""
    s = (slug + " " + texte).lower()
    pref = slug.lower().split("-", 1)[0]
    ligues = {"tennis": {"atp", "wta"}, "esport": {"dota2", "lol", "cs2", "val"},
              "foot": {"epl", "ucl", "uel", "lal", "sea", "bun", "fl1", "mls", "bra", "bra2", "rou1", "por",
                       "ere", "itc", "arg", "mex", "lig", "efl", "spl", "tur", "bel", "sco", "uecl", "fifa"},
              "sport US": {"nfl", "nba", "nhl", "mlb", "cfb", "ncaab", "cbb", "wnba"},
              "autres sports": {"shl", "cehl", "khl", "del", "nll", "f1", "cricket", "ipl"}}
    for nom, codes in ligues.items():
        if pref in codes:
            return nom
    regles = [("tweets", ["tweet", " post "]),
              ("esport", ["valorant", "counter-strike", "dota 2", "lol:", "league of legends"]),
              ("tennis", ["atp ", "wta ", "tennis"]),
              ("sport US", ["kxnfl", "kxnba", "kxnhl", "kxmlb", "ncaa", " nba", " nfl", " nhl", " mlb"]),
              ("foot", ["premier league", "champions league", " fc ", "fc win", "soccer"]),
              ("combat", ["ufc", "boxing"]), ("youtube", ["mrbeast", "youtube"]),
              ("crypto", ["bitcoin", "btc", "ethereum", "eth ", "solana", "crypto"]),
              ("météo", ["temperature", "weather", "°", "rain", "snow", "hurricane"]),
              ("marchés", ["s&p", "spy", "nasdaq", "stock", "fed ", "inflation", "cpi", "rate"]),
              ("politique", ["trump", "election", "president", "senate", "vote", "minister", "congress"])]
    for nom, mots in regles:
        if any(m in s for m in mots):
            return nom
    return "autre"
