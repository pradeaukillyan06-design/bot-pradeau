"""Azuro (paris sportifs décentralisés, monde entier) : foot, tennis, basket, hockey, esport, boxe… de
dizaines de pays (France, Japon, Brésil, Turquie…). Lecture seule de l'API publique, sans compte.
Chaque « condition » (ex. vainqueur du match, plus/moins de buts) a 2 ou 3 issues avec une cote décimale."""
from datetime import timedelta

from .commun import categorie, date_iso, lire_json, maintenant, nombre

BASE = "https://api.onchainfeed.org/api/v1/public/market-manager"
ENV = "PolygonUSDT"
SPORTS = {"football": "foot", "tennis": "tennis", "basketball": "basket", "ice-hockey": "hockey",
          "american-football": "sport US", "baseball": "sport US", "esports": "esport", "cs2": "esport",
          "dota-2": "esport", "league-of-legends": "esport", "boxing": "combat", "mma": "combat",
          "cricket": "cricket", "volleyball": "volley", "handball": "handball", "rugby-union": "rugby",
          "table-tennis": "tennis de table"}


class Azuro:
    nom = "azuro"
    argent_reel = True
    verifs_max = 30

    def frais(self, prix):
        return 0.0                            # la marge est déjà dans la cote

    def _matchs(self, pages=5, par_page=100, heures_max=72):
        limite = maintenant() + timedelta(hours=heures_max)
        out = []
        for p in range(1, pages + 1):
            r = lire_json(f"{BASE}/games-by-filters?gameState=Prematch&environment={ENV}&orderBy=startsAt"
                          f"&orderDirection=asc&page={p}&perPage={par_page}")
            lot = (r or {}).get("games") or []
            out += lot
            if len(lot) < par_page or (lot and (date_iso(int(lot[-1].get("startsAt", 0))) or limite) > limite):
                break
        return out

    def candidats(self, jours_max):
        matchs = {g["gameId"]: g for g in self._matchs() if g.get("gameId")}
        ids = list(matchs)
        out = []
        for i in range(0, len(ids), 40):
            r = lire_json(f"{BASE}/conditions-by-game-ids", corps={"gameIds": ids[i:i + 40], "environment": ENV})
            for cond in (r or {}).get("conditions") or []:
                g = matchs.get((cond.get("game") or {}).get("gameId"))
                c = self._normaliser(cond, g)
                if c:
                    out.append(c)
        return out

    def _normaliser(self, cond, g):
        if not cond or not g or cond.get("hidden") or cond.get("state") != "Active":
            return None
        # toutes les issues, triées par numéro : le même ordre servira à lire le résultat
        outs = sorted(cond.get("outcomes") or [], key=lambda o: int(o.get("outcomeId", 0)))
        if len(outs) not in (2, 3) or any(o.get("state") != "Active" or o.get("hidden") for o in outs):
            return None
        cotes_dec = [nombre(o.get("odds")) for o in outs]
        if any(c is None or c <= 1.0 for c in cotes_dec):
            return None
        implicites = [1 / c for c in cotes_dec]
        marge = sum(implicites) - 1
        if not -0.02 < marge < 0.25:
            return None
        debut = date_iso(int(g.get("startsAt", 0)))
        if not debut:
            return None
        sport = (g.get("sport") or {}).get("slug", "")
        pays = (g.get("country") or {}).get("name", "")
        ligue = (g.get("league") or {}).get("name", "")
        return {"site": self.nom, "id": cond["conditionId"], "slug": g["gameId"],
                "question": f"{g.get('title', '')} — {cond.get('title', '')} ({ligue}, {pays})",
                "issues": [o.get("title", "") for o in outs],
                "cotes": [round(min(0.9999, max(0.0001, p - marge / len(outs))), 4) for p in implicites],
                "achat": [round(p, 4) for p in implicites],
                "fin": debut + timedelta(hours=4), "debut": debut.isoformat(), "volume": nombre(g.get("turnover")) or 0.0,
                "cat": SPORTS.get(sport, categorie(g.get("title", ""))), "_ids": [o["outcomeId"] for o in outs]}

    def _condition(self, game_id, cond_id):
        r = lire_json(f"{BASE}/conditions-by-game-ids", corps={"gameIds": [game_id], "environment": ENV})
        return next((c for c in (r or {}).get("conditions") or [] if c.get("conditionId") == cond_id), None)

    def adresses(self, marche):
        return [f"{BASE}/conditions-by-game-ids#{marche['slug']}|{marche['id']}|{marche['debut']}"] * 6

    def lire(self, url):
        game_id, cond_id, debut = url.split("#", 1)[1].split("|")
        cond = self._condition(game_id, cond_id)
        g = {"gameId": game_id, "startsAt": int(date_iso(debut).timestamp()), "title": ""}
        c = self._normaliser(cond, g)
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"], "ferme": date_iso(debut) <= maintenant()}

    def resultat(self, marche):
        lectures = []
        for _ in range(2):
            cond = self._condition(marche["slug"], marche["id"])
            if not cond:
                return {"fini": False}
            etat = str(cond.get("state", ""))
            gagnants = [str(x) for x in cond.get("wonOutcomeIds") or []]
            ids = [str(o.get("outcomeId")) for o in sorted(cond.get("outcomes") or [],
                                                         key=lambda o: int(o.get("outcomeId", 0)))]
            if etat in ("Canceled", "Cancelled"):
                lectures.append("rembourse")
            elif etat == "Resolved" and gagnants:
                lectures.append([1.0 if i in gagnants else 0.0 for i in ids])
            else:
                return {"fini": False}
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        if lectures[0] == "rembourse":
            return {"fini": True, "rembourse": True}
        return {"fini": True, "paiement": lectures[0]}
