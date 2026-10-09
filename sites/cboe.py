"""CBOE (bourse d'options de Chicago, États-Unis) : options sur le S&P 500 (SPY), le Nasdaq (QQQ) et de
grandes actions (Apple, Microsoft, Nvidia…). Données publiques différées de 15 min, sans compte.
Comme pour les options crypto : probabilité « l'action finira au-dessus de X $ à l'échéance », tirée de la
volatilité du marché ; le résultat est le cours de clôture officiel du jour d'échéance. Observation seulement."""
from datetime import datetime, timezone

from .commun import lire_json, maintenant, nombre
from .options_crypto import proba_au_dessus

BASE = "https://cdn.cboe.com/api/global/delayed_quotes"
SYMBOLES = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN"]


def _decoupe(code):
    """SPY261016C00700000 -> SPY, échéance 16/10/2026 20 h UTC (clôture de New York), call, 700."""
    racine = code[:-15]
    jour, sens, strike = code[-15:-9], code[-9], int(code[-8:]) / 1000
    ech = datetime(2000 + int(jour[:2]), int(jour[2:4]), int(jour[4:6]), 20, tzinfo=timezone.utc)
    return racine, ech, sens, strike


class Cboe:
    nom = "cboe"
    argent_reel = False                      # probabilité tirée des options : on observe, on ne mise pas
    verifs_max = 10                          # chaque relecture télécharge toute la chaîne d'options

    def frais(self, prix):
        return 0.0

    def _cours(self, sym):
        return nombre((lire_json(f"{BASE}/quotes/{sym}.json").get("data") or {}).get("current_price"))

    def _marche(self, o, cours):
        try:
            racine, ech, sens, strike = _decoupe(o.get("option", ""))
        except (ValueError, IndexError):
            return None
        annees = (ech - maintenant()).total_seconds() / (365.25 * 86400)
        vol = nombre(o.get("iv"))
        if sens != "C" or annees < 2 / (365.25 * 24) or not vol or vol < 0.02:
            return None
        p = proba_au_dessus(cours, strike, vol, annees)
        if p is None:
            return None
        p = round(min(0.9999, max(0.0001, p)), 4)
        return {"site": self.nom, "id": o["option"], "slug": f"{racine}|{ech:%Y-%m-%d}|{strike:g}",
                "question": f"{racine} au-dessus de {strike:g} $ à la clôture du {ech:%d/%m/%Y} ?",
                "issues": ["Au-dessus", "En dessous"], "cotes": [p, round(1 - p, 4)], "achat": [p, round(1 - p, 4)],
                "fin": ech, "volume": nombre(o.get("open_interest")) or 0.0, "cat": "bourse US"}

    def candidats(self, jours_max):
        out = []
        for sym in SYMBOLES:
            try:
                cours = self._cours(sym)
                chaine = (lire_json(f"{BASE}/options/{sym}.json").get("data") or {}).get("options") or []
            except Exception:
                continue
            for o in chaine:
                c = self._marche(o, cours)
                if c and c["volume"] > 0:
                    out.append(c)
        return out

    def adresses(self, marche):
        sym = marche["slug"].split("|")[0]
        return [f"{BASE}/options/{sym}.json#{marche['id']}"] * 6

    def lire(self, url):
        base, code = url.split("#", 1)
        sym = base.rsplit("/", 1)[1][:-5]
        o = next((x for x in (lire_json(base).get("data") or {}).get("options") or [] if x.get("option") == code), None)
        c = self._marche(o, self._cours(sym)) if o else None
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"], "ferme": c["fin"] <= maintenant()}

    def resultat(self, marche):
        sym, jour, strike = marche["slug"].split("|")
        lectures = []
        for _ in range(2):
            jours = lire_json(f"{BASE}/charts/historical/{sym}.json").get("data") or []
            cloture = next((nombre(j.get("close")) for j in reversed(jours) if j.get("date") == jour), None)
            if cloture is None:
                return {"fini": False}
            lectures.append({"fini": True, "paiement": [1.0, 0.0] if cloture > float(strike) else [0.0, 1.0]})
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        return lectures[0]
