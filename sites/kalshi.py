"""Kalshi (bourse de prédiction américaine régulée). Lecture seule de l'API publique."""
from datetime import timedelta

from .commun import categorie, date_iso, lire_json, maintenant, nombre

BASE = "https://api.elections.kalshi.com/trade-api/v2"


def _prix(m, cle):
    """Kalshi donne les prix en dollars (champ *_dollars) ou en centimes (ancien format)."""
    v = nombre(m.get(f"{cle}_dollars"))
    if v is None:
        c = nombre(m.get(cle))
        v = c / 100 if c is not None else None
    return v if v is not None and 0 < v < 1 else None


class Kalshi:
    nom = "kalshi"
    argent_reel = True

    def frais(self, prix):
        """Frais Kalshi ≈ 0,07 × p × (1-p) par contrat, ramené à la mise (fraction du prix payé)."""
        return 0.07 * (1 - prix)

    def candidats(self, jours_max, volume_min=500):
        t0 = maintenant()
        fin = t0 + timedelta(days=jours_max)
        url = (f"{BASE}/markets?status=open&limit=1000&mve_filter=exclude&min_close_ts={int(t0.timestamp())}"
               f"&max_close_ts={int(fin.timestamp())}")
        out, curseur = [], ""
        for _ in range(5):
            r = lire_json(url + (f"&cursor={curseur}" if curseur else ""))
            for m in r.get("markets", []):
                c = self._normaliser(m)
                if c and c["volume"] >= volume_min:
                    out.append(c)
            curseur = r.get("cursor") or ""
            if not curseur:
                break
        return out

    def _normaliser(self, m):
        t = m.get("ticker", "")
        if not t or t.startswith("KXMVE"):          # combinés multi-paris : illiquides, exclus
            return None
        if m.get("market_type", "binary") != "binary":
            return None
        ya, na = _prix(m, "yes_ask"), _prix(m, "no_ask")
        yb = _prix(m, "yes_bid")
        if ya is None or yb is None or ya - yb > 0.03:
            return None                     # écart achat/vente trop grand : pas de cote fiable
        oui = (ya + yb) / 2
        titre = m.get("title", "") + (f" — {m['yes_sub_title']}" if m.get("yes_sub_title") else "")
        return {"site": self.nom, "id": t, "slug": t.lower(), "question": titre, "issues": ["Oui", "Non"],
                "cotes": [round(oui, 4), round(1 - oui, 4)], "achat": [ya, na],
                "fin": date_iso(m.get("close_time")), "volume": nombre(m.get("volume_fp")) or nombre(m.get("volume")) or 0.0,
                "cat": categorie(titre, t.lower()), "groupe": m.get("event_ticker") or None}

    def adresses(self, marche):
        return [f"{BASE}/markets/{marche['id']}"] * 6       # même source, relue 6 fois à quelques secondes

    def lire(self, url):
        m = lire_json(url).get("market")
        c = self._normaliser(m) if m else None
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"],
                "ferme": m.get("status") not in ("active", "open")}

    def resultat(self, marche):
        lectures = []
        for _ in range(2):
            m = lire_json(f"{BASE}/markets/{marche['id']}").get("market", {})
            statut, res = m.get("status", ""), str(m.get("result", "")).lower()
            if statut not in ("settled", "finalized", "determined"):
                return {"fini": False}
            if res == "yes":
                lectures.append([1.0, 0.0])
            elif res == "no":
                lectures.append([0.0, 1.0])
            elif statut in ("settled", "finalized"):
                lectures.append("rembourse")            # marché réglé sans gagnant : annulé, mise rendue
            else:
                return {"fini": False}                  # « determined » sans résultat encore publié : on attend
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        if lectures[0] == "rembourse":
            return {"fini": True, "rembourse": True}
        return {"fini": True, "paiement": lectures[0]}
