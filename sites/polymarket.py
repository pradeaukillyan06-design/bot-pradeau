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
        # les adresses ?id= et /markets/<id> restent figées des heures après la fin : on lit les adresses
        # « marchés fermés », qui donnent le résultat officiel tout de suite (leçon des nuits précédentes)
        i = marche["id"]
        for url in (f"{BASE}/markets?id={i}&closed=true", f"{BASE}/markets?id={i}&closed=true&limit=1"):
            r = lire_json(url)
            m = (r[0] if r else None) if isinstance(r, list) else r   # liste vide : pas encore fermé
            if not m or not m.get("closed") or str(m.get("umaResolutionStatus", "")).lower() != "resolved":
                return {"fini": False}
            c = self._normaliser(m)
            if not c:
                return {"fini": False}
            lectures.append(c["cotes"])
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        return {"fini": True, "paiement": lectures[0]}

    # ------------------------------------------------------------------
    # Historique : marchés déjà terminés, cote la veille de la fin
    # ------------------------------------------------------------------
    def historique(self, curseur, nombre_max=60, heures_avant=24):
        """Renvoie (observations historiques, nouveau curseur). Pour chaque marché terminé,
        on regarde la cote `heures_avant` heures avant la fin : si un côté était > 97 %,
        on note s'il a gagné. C'est de l'expérience immédiate, sans attendre."""
        import time as _t
        CLOB = "https://clob.polymarket.com"
        lot = lire_json(f"{BASE}/markets?closed=true&limit={nombre_max}&offset={curseur}"
                        f"&order=volumeNum&ascending=false&volume_num_min=5000")
        out = []
        for m in lot or []:
            try:
                if str(m.get("umaResolutionStatus", "")).lower() != "resolved":
                    continue
                c = self._normaliser(m)
                jetons = json.loads(m["clobTokenIds"]) if isinstance(m.get("clobTokenIds"), str) else m.get("clobTokenIds")
                ct = (m.get("closedTime") or "").replace(" ", "T")
                ct = ct + ":00" if ct.endswith("+00") else ct
                fin = date_iso(ct) or (c and c["fin"])
                if not c or not jetons or not fin or sorted(c["cotes"]) != [0.0, 1.0]:
                    continue
                t_obs = int(fin.timestamp()) - heures_avant * 3600
                h = lire_json(f"{CLOB}/prices-history?market={jetons[0]}&startTs={t_obs - 3 * 86400}"
                              f"&endTs={t_obs}&fidelity=60").get("history", [])
                avant = [pt for pt in h if pt.get("t", 0) <= t_obs]
                if not avant:
                    continue
                p0 = float(avant[-1]["p"])
                for idx, p in ((0, p0), (1, 1 - p0)):
                    if 0.97 < p < 1.0:
                        out.append({"site": self.nom, "id": c["id"], "question": c["question"], "cat": c["cat"],
                                    "idx": idx, "prix": round(p, 4), "gagne": int(c["cotes"][idx] >= 0.99),
                                    "horizon_h": heures_avant, "fin": fin.isoformat(), "source": "historique"})
                _t.sleep(0.1)
            except Exception:
                continue
        return out, curseur + len(lot or [])
