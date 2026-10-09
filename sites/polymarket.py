"""Polymarket (argent réel côté marché, mais le bot ne fait que LIRE). API publique Gamma."""
import json
from datetime import timedelta

from .commun import categorie, date_iso, lire_json, maintenant, nombre

BASE = "https://gamma-api.polymarket.com"


class Polymarket:
    nom = "polymarket"
    argent_reel = True

    def frais(self, prix):
        return 0.0                       # pas de frais sur la plupart des marchés

    def candidats(self, jours_max, volume_min=5000):
        t0 = maintenant()
        fin = t0 + timedelta(days=jours_max)
        commun = (f"closed=false&active=true&limit=200&volume_num_min={volume_min}"
                  f"&end_date_min={t0.strftime('%Y-%m-%dT%H:%M:%SZ')}&end_date_max={fin.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        vus, out = set(), []
        for ordre, pages in (("order=volumeNum&ascending=false", 5), ("order=endDate&ascending=true", 3)):
            for p in range(pages):
                lot = lire_json(f"{BASE}/markets?{commun}&{ordre}&offset={p * 200}")
                if not lot:
                    break
                for m in lot:
                    c = self._normaliser(m)
                    if c and c["id"] not in vus:
                        vus.add(c["id"])
                        out.append(c)
        return out

    def _normaliser(self, m):
        try:
            issues = json.loads(m["outcomes"]) if isinstance(m.get("outcomes"), str) else m.get("outcomes")
            prix = [float(x) for x in (json.loads(m["outcomePrices"]) if isinstance(m.get("outcomePrices"), str)
                                       else m.get("outcomePrices"))]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        if not issues or len(issues) != 2 or len(prix) != 2:
            return None                  # le calcul du prix d'achat ne vaut que pour 2 issues
        return {"site": self.nom, "id": str(m["id"]), "slug": m.get("slug", ""), "question": m.get("question", ""),
                "issues": issues, "cotes": prix, "fin": date_iso(m.get("endDate")),
                "volume": nombre(m.get("volumeNum")) or 0.0,
                "cat": categorie(m.get("question", ""), m.get("slug", ""))}

    def adresses(self, marche):
        i, s = marche["id"], marche.get("slug", "")
        return [f"{BASE}/markets/{i}", f"{BASE}/markets?id={i}", f"{BASE}/markets/slug/{s}",
                f"{BASE}/markets?slug={s}", f"{BASE}/markets?id={i}&limit=1", f"{BASE}/markets?slug={s}&closed=false"]

    def lire(self, url):
        r = lire_json(url)
        m = r[0] if isinstance(r, list) else r
        if not m:
            return None
        c = self._normaliser(m)
        if not c:
            return None
        bid, ask = nombre(m.get("bestBid")), nombre(m.get("bestAsk"))
        achat = [ask if ask and 0 < ask < 1 else None,
                 round(1 - bid, 4) if bid and 0 < bid < 1 else None]
        return {"id": c["id"], "cotes": c["cotes"], "achat": achat, "ferme": bool(m.get("closed"))}

    def resultat(self, marche):
        """{'fini': bool, 'paiement': [p_oui, p_non] ou None}"""
        lectures = []
        for url in self.adresses(marche)[:2]:
            r = lire_json(url)
            m = r[0] if isinstance(r, list) else r
            if not m or not m.get("closed") or str(m.get("umaResolutionStatus", "")).lower() != "resolved":
                return {"fini": False}
            c = self._normaliser(m)
            if not c:
                return {"fini": False}
            lectures.append(c["cotes"])
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        return {"fini": True, "paiement": lectures[0]}
