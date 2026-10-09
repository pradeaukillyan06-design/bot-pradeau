"""SX Bet (bourse de paris sportifs décentralisée, internationale) : NBA, NFL, foot, tennis… Lecture seule
du carnet d'ordres public, sans compte. Un ordre « issue 1 à 76 % » posé par un parieur permet à un autre
de jouer l'issue 2 au prix de 24 % : le prix d'achat d'une issue vient donc des ordres posés sur l'autre."""
from datetime import timedelta

from .commun import categorie, date_iso, lire_json, maintenant

BASE = "https://api.sx.bet"
SPORTS = {"Basketball": "basket", "Football": "sport US", "Soccer": "foot", "Tennis": "tennis", "Hockey": "hockey",
          "Baseball": "sport US", "E Sports": "esport", "MMA": "combat", "Boxing": "combat", "Cricket": "cricket"}


def _cote(x):
    try:
        return int(x["percentageOdds"]) / 1e20
    except (KeyError, TypeError, ValueError):
        return None


class SxBet:
    nom = "sxbet"
    argent_reel = True

    def frais(self, prix):
        return 0.0

    def _marches(self, pages=10, heures_max=72):
        limite = maintenant() + timedelta(hours=heures_max)
        out, cle = [], ""
        for _ in range(pages):
            r = lire_json(f"{BASE}/markets/active?onlyMainLine=true" + (f"&paginationKey={cle}" if cle else ""))
            d = (r or {}).get("data") or {}
            for m in d.get("markets") or []:
                debut = date_iso(m.get("gameTime"))
                if debut and maintenant() < debut <= limite and m.get("status") == "ACTIVE":
                    out.append(m)
            cle = d.get("nextKey")
            if not cle:
                break
        return out

    def _normaliser(self, m, carnet):
        un = [c for c in (_cote(x) for x in carnet.get("outcomeOne") or []) if c and 0 < c < 1]
        deux = [c for c in (_cote(x) for x in carnet.get("outcomeTwo") or []) if c and 0 < c < 1]
        if not un or not deux:
            return None                                  # carnet vide d'un côté : pas de prix fiable
        achat = [round(1 - max(deux), 4), round(1 - max(un), 4)]
        if achat[0] + achat[1] - 1 > 0.05 or min(achat) <= 0:
            return None
        oui = (max(un) + achat[0]) / 2
        debut = date_iso(m.get("gameTime"))
        titre = f"{m.get('teamOneName', '')} vs {m.get('teamTwoName', '')}"
        return {"site": self.nom, "id": m["marketHash"], "slug": m.get("sportXeventId", ""),
                "question": f"{titre} — {m.get('outcomeOneName', '')} / {m.get('outcomeTwoName', '')} "
                            f"({m.get('leagueLabel', '')})",
                "issues": [m.get("outcomeOneName", "1"), m.get("outcomeTwoName", "2")],
                "cotes": [round(oui, 4), round(1 - oui, 4)], "achat": achat,
                "fin": debut + timedelta(hours=4), "debut": debut.isoformat(), "volume": 0.0,
                "cat": SPORTS.get(m.get("sportLabel"), categorie(titre))}

    def candidats(self, jours_max, max_carnets=200):
        out = []
        for m in self._marches()[:max_carnets]:
            try:
                carnet = (lire_json(f"{BASE}/orderbook-v3/snapshot?marketHash={m['marketHash']}",
                                    essais=2, pause=1) or {}).get("data") or {}
            except Exception:
                continue
            c = self._normaliser(m, carnet)
            if c:
                out.append(c)
        return out

    def adresses(self, marche):
        return [f"{BASE}/orderbook-v3/snapshot?marketHash={marche['id']}#{marche['debut']}"] * 6

    def lire(self, url):
        base, debut = url.split("#", 1)
        mid = base.split("marketHash=")[1]
        carnet = (lire_json(base) or {}).get("data") or {}
        m = {"marketHash": mid, "gameTime": int(date_iso(debut).timestamp())}
        c = self._normaliser(m, carnet)
        if not c:
            return None
        return {"id": mid, "cotes": c["cotes"], "achat": c["achat"], "ferme": date_iso(debut) <= maintenant()}

    def resultat(self, marche):
        lectures = []
        for _ in range(2):
            m = next(iter((lire_json(f"{BASE}/markets/find?marketHashes={marche['id']}") or {}).get("data") or []), {})
            if str(m.get("status", "")).upper() != "SETTLED":
                return {"fini": False}
            issue = m.get("outcome")
            if issue in (1, 2):
                lectures.append([1.0, 0.0] if issue == 1 else [0.0, 1.0])
            elif issue == 0:
                lectures.append("rembourse")
            else:
                return {"fini": False}
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        if lectures[0] == "rembourse":
            return {"fini": True, "rembourse": True}
        return {"fini": True, "paiement": lectures[0]}
