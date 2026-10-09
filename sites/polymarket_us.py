"""Polymarket US (bourse de prédiction américaine régulée, distincte de Polymarket international : ses propres
prix et son propre carnet d'ordres). Sport surtout (NFL, MLB, NBA, NHL, foot, golf…). Lecture seule de
l'API publique, sans compte. Chaque marché a un instrument « long » (1re issue) ; la 2e issue = le côté court."""
from .commun import categorie, date_iso, lire_json, maintenant, nombre

BASE = "https://gateway.polymarket.us/v1"
LIGUES_US = {"nfl", "nba", "mlb", "nhl", "cfb", "cbb", "wnba", "ncaab", "ncaaf"}


def _px(x):
    return nombre(((x or {}).get("px") or {}).get("value"))


class PolymarketUs:
    nom = "polymarket_us"
    argent_reel = True

    def frais(self, prix):
        return 0.07 * (1 - prix)            # prudent, même ordre que Kalshi

    def candidats(self, jours_max, pages=6, par_page=200):
        out = []
        for p in range(pages):
            r = lire_json(f"{BASE}/markets?active=true&closed=false&limit={par_page}&offset={p * par_page}")
            lot = (r or {}).get("markets") or []
            for m in lot:
                c = self._normaliser(m)
                if c:
                    out.append(c)
            if len(lot) < par_page:
                break
        return out

    def _normaliser(self, m):
        cotes = m.get("marketSides") or []
        if len(cotes) != 2 or not m.get("slug") or m.get("closed"):
            return None
        cotes = sorted(cotes, key=lambda c: not c.get("long", False))   # l'instrument « long » en premier
        p = nombre(cotes[0].get("price"))
        if p is None or not 0 < p < 1:
            return None
        ligue = ((cotes[0].get("team") or {}).get("league") or "").lower()
        return {"site": self.nom, "id": m["slug"], "slug": m["slug"], "question": m.get("question", ""),
                "issues": [cotes[0].get("description", "1"), cotes[1].get("description", "2")],
                "cotes": [round(p, 4), round(1 - p, 4)], "achat": [None, None],
                "fin": date_iso(m.get("endDate")), "volume": 0.0,
                "cat": "sport US" if ligue in LIGUES_US else categorie(m.get("question", ""), ligue)}

    def adresses(self, marche):
        return [f"{BASE}/markets/{marche['id']}/book"] * 6

    def lire(self, url):
        d = (lire_json(url) or {}).get("marketData") or {}
        bids = [x for x in (_px(b) for b in d.get("bids") or []) if x and 0 < x < 1]
        offres = [x for x in (_px(o) for o in d.get("offers") or []) if x and 0 < x < 1]
        if not bids and not offres:
            return None
        if not bids or not offres:
            # un seul côté du carnet : le prix se lit, mais l'autre issue n'a personne en face (pas achetable)
            oui = min(offres) if offres else max(bids)
            achat = [min(offres), None] if offres else [None, round(1 - max(bids), 4)]
            return {"id": d.get("marketSlug"), "cotes": [round(oui, 4), round(1 - oui, 4)], "achat": achat,
                    "ferme": d.get("state") != "MARKET_STATE_OPEN"}
        bid, offre = max(bids), min(offres)
        if bid > offre:
            return None
        oui = (bid + offre) / 2
        achat = [offre, round(1 - bid, 4)] if offre - bid <= 0.05 else [None, None]
        return {"id": d.get("marketSlug"), "cotes": [round(oui, 4), round(1 - oui, 4)], "achat": achat,
                "ferme": d.get("state") != "MARKET_STATE_OPEN"}

    def resultat(self, marche):
        lectures = []
        for _ in range(2):
            d = (lire_json(f"{BASE}/markets/{marche['id']}/book") or {}).get("marketData") or {}
            etat = str(d.get("state", ""))
            prix = nombre(((d.get("stats") or {}).get("settlementPx") or {}).get("value"))
            # le prix de règlement existe aussi sur les marchés ouverts (cote du jour) : seul un marché
            # EXPIRÉ est réellement réglé. Prix entre 0 et 1 (ex. 0,5 = match annulé) : le chef l'exclut.
            if etat != "MARKET_STATE_EXPIRED" or prix is None or not 0 <= prix <= 1:
                return {"fini": False}
            lectures.append([prix, round(1 - prix, 4)])
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        return {"fini": True, "paiement": lectures[0]}
