"""Limitless (marché de prédiction crypto) : paris « BTC/ETH/SOL… monte ou baisse » toutes les 5 min,
15 min, heures, jours, plus du sport et de l'esport. Lecture seule de l'API publique, sans compte.
Beaucoup de marchés se terminent très vite : idéal pour accumuler de l'expérience."""
from .commun import categorie, date_iso, lire_json, maintenant, nombre

BASE = "https://api.limitless.exchange"


class Limitless:
    nom = "limitless"
    argent_reel = True

    def frais(self, prix):
        return 0.003                     # frais de transaction prudents (le site annonce des frais)

    def candidats(self, jours_max, pages=20):
        out, vus = [], set()
        for p in range(1, pages + 1):
            r = lire_json(f"{BASE}/markets/active?limit=25&page={p}&sortBy=ending_soon")
            lot = r.get("data", []) if isinstance(r, dict) else r
            if not lot:
                break
            for m in lot:
                c = self._normaliser(m)
                if c and c["id"] not in vus:
                    vus.add(c["id"])
                    out.append(c)
        return out

    def _normaliser(self, m):
        if not m or m.get("marketType", "single") != "single" or not m.get("slug"):
            return None
        prix = m.get("prices") or []
        if len(prix) != 2:
            return None
        try:
            cotes = [float(prix[0]), float(prix[1])]
        except (TypeError, ValueError):
            return None
        achat = [None, None]
        tp = (m.get("tradePrices") or {}).get("buy", {}).get("market")
        if isinstance(tp, list) and len(tp) == 2:
            achat = [nombre(tp[0]), nombre(tp[1])]
            achat = [a if a is not None and 0 < a < 1 else None for a in achat]
        if all(a is not None for a in achat) and achat[0] + achat[1] - 1 > 0.05:
            achat = [None, None]          # écart achat/vente trop grand : pas de prix fiable
        cats = " ".join(m.get("categories") or [])
        titre = m.get("title", "")
        cat = "crypto" if (m.get("priceOracleMetadata") or "Minutely" in cats or "Hourly" in cats) else categorie(titre)
        return {"site": self.nom, "id": m["slug"], "slug": m["slug"], "question": titre, "issues": ["Oui", "Non"],
                "cotes": cotes, "achat": achat, "fin": date_iso(nombre(m.get("expirationTimestamp"))),
                "volume": nombre(m.get("volumeFormatted")) or 0.0, "cat": cat,
                "_statut": m.get("status"), "_expire": bool(m.get("expired"))}

    def adresses(self, marche):
        return [f"{BASE}/markets/{marche['id']}"] * 6       # même source relue 6 fois à quelques secondes

    def lire(self, url):
        m = lire_json(url)
        c = self._normaliser(m)
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"],
                "ferme": c["_statut"] != "FUNDED" or c["_expire"] or (c["fin"] and c["fin"] <= maintenant())}

    def resultat(self, marche):
        lectures = []
        for _ in range(2):
            m = lire_json(f"{BASE}/markets/{marche['id']}")
            if str(m.get("status", "")).upper() != "RESOLVED":
                return {"fini": False}
            g = m.get("winningOutcomeIndex")
            if g in (0, 1):
                lectures.append([1.0, 0.0] if g == 0 else [0.0, 1.0])
            else:
                return {"fini": False}                  # résolu mais gagnant pas encore publié : on attend
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        if lectures[0] == "rembourse":
            return {"fini": True, "rembourse": True}
        return {"fini": True, "paiement": lectures[0]}
