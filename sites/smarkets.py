"""Smarkets (bourse de paris britannique) : football de dizaines de pays, tennis, esport, politique…
Lecture seule de l'API publique, sans compte. Chaque « contrat » (ex. « Kashima gagne », « Match nul »)
est un pari Oui/Non : acheter = parier pour (back), le côté Non = parier contre (lay)."""
from datetime import timedelta

from .commun import categorie, date_iso, lire_json, maintenant

BASE = "https://api.smarkets.com/v3"
SPORTS = {"football": "foot", "tennis": "tennis", "esports": "esport", "basketball": "basket",
          "american-football": "sport US", "baseball": "sport US", "ice-hockey": "hockey", "cricket": "cricket",
          "rugby-union": "rugby", "rugby-league": "rugby", "golf": "golf", "boxing": "combat", "mma": "combat",
          "darts": "fléchettes", "snooker": "snooker", "volleyball": "volley", "handball": "handball"}


def _par_lots(ids, n=20):
    ids = list(ids)
    for i in range(0, len(ids), n):
        yield ids[i:i + n]


class Smarkets:
    nom = "smarkets"
    argent_reel = True

    def frais(self, prix):
        return 0.02 * (1 - prix) / prix        # commission 2 % sur le gain net, ramenée à la mise

    def _categorie(self, ev):
        morceaux = (ev.get("full_slug") or "").strip("/").split("/")
        if len(morceaux) > 1 and morceaux[0] == "sport":
            return SPORTS.get(morceaux[1], "autres sports")
        if morceaux and morceaux[0] == "politics":
            return "politique"
        return categorie(ev.get("name", ""))

    def candidats(self, jours_max, pages=5, heures_max=72):
        t0 = maintenant()
        fin = t0 + timedelta(hours=min(heures_max, jours_max * 24))
        url = (f"{BASE}/events/?state=upcoming&type_scope=single_event&limit=100&sort=start_datetime,id"
               f"&start_datetime_min={t0:%Y-%m-%dT%H:%M:%SZ}&start_datetime_max={fin:%Y-%m-%dT%H:%M:%SZ}")
        evs = {}
        for _ in range(pages):
            r = lire_json(url)
            for ev in r.get("events", []):
                if ev.get("bettable") and not ev.get("hidden"):
                    evs[ev["id"]] = ev
            suite = (r.get("pagination") or {}).get("next_page")
            if not suite:
                break
            url = f"{BASE}/events/{suite}"
        marches = {}
        for lot in _par_lots(evs):
            for m in lire_json(f"{BASE}/events/{','.join(lot)}/markets/").get("markets", []):
                if m.get("state") == "open" and not m.get("hidden") and m.get("category") == "winner":
                    marches[m["id"]] = m
        out = []
        for lot in _par_lots(marches, 40):
            cl = ",".join(lot)
            contrats = lire_json(f"{BASE}/markets/{cl}/contracts/").get("contracts", [])
            cotations = lire_json(f"{BASE}/markets/{cl}/quotes/")
            for k in contrats:
                m = marches.get(k.get("market_id"))
                if not m or k.get("hidden") or k.get("state_or_outcome") != "open":
                    continue
                ev = evs.get(m.get("event_id"), {})
                c = self._normaliser(k, m, ev, cotations.get(k["id"]))
                if c:
                    out.append(c)
        return out

    @staticmethod
    def _prix(q):
        """Meilleur prix acheteur (bid) et vendeur (offer), en probabilité (10000 = 100 %)."""
        if not q:
            return None, None
        bids = [b["price"] for b in q.get("bids", []) if b.get("price")]
        offres = [o["price"] for o in q.get("offers", []) if o.get("price")]
        return (max(bids) / 10000 if bids else None), (min(offres) / 10000 if offres else None)

    def _normaliser(self, k, m, ev, q):
        bid, offre = self._prix(q)
        if bid is None or offre is None or not 0 < bid <= offre < 1:
            return None
        oui = (bid + offre) / 2
        achat = [offre, round(1 - bid, 4)] if offre - bid <= 0.05 else [None, None]
        debut = date_iso(ev.get("start_datetime"))
        if not debut:
            return None
        return {"site": self.nom, "id": f"{m['id']}:{k['id']}", "slug": m["id"],
                "question": f"{ev.get('name', '')} — {m.get('name', '')} : {k.get('name', '')}",
                "issues": ["Oui", "Non"], "cotes": [round(oui, 4), round(1 - oui, 4)], "achat": achat,
                "fin": debut + timedelta(hours=3), "debut": debut.isoformat(), "volume": 0.0,
                "cat": self._categorie(ev)}

    def adresses(self, marche):
        mid, cid = marche["id"].split(":")
        return [f"{BASE}/markets/{mid}/quotes/#{cid}|{marche['debut']}"] * 6

    def lire(self, url):
        base, reste = url.split("#", 1)
        cid, debut = reste.split("|", 1)
        mid = base.rstrip("/").split("/")[-2]
        bid, offre = self._prix(lire_json(base).get(cid))
        if bid is None or offre is None or not 0 < bid <= offre < 1:
            return None
        oui = (bid + offre) / 2
        achat = [offre, round(1 - bid, 4)] if offre - bid <= 0.05 else [None, None]
        commence = date_iso(debut) <= maintenant()       # match commencé : on ne prend plus de nouveau pari
        return {"id": f"{mid}:{cid}", "cotes": [round(oui, 4), round(1 - oui, 4)], "achat": achat, "ferme": commence}

    def resultat(self, marche):
        mid, cid = marche["id"].split(":")
        lectures = []
        for _ in range(2):
            k = next((c for c in lire_json(f"{BASE}/markets/{mid}/contracts/").get("contracts", [])
                      if c.get("id") == cid), None)
            etat = (k or {}).get("state_or_outcome")
            if etat == "winner":
                lectures.append([1.0, 0.0])
            elif etat == "loser":
                lectures.append([0.0, 1.0])
            elif etat in ("void", "voided", "cancelled", "dead_heat", "removed"):
                lectures.append("rembourse")
            else:
                return {"fini": False}
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        if lectures[0] == "rembourse":
            return {"fini": True, "rembourse": True}
        return {"fini": True, "paiement": lectures[0]}
