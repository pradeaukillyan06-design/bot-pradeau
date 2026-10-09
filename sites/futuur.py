"""Futuur (marché de prédiction international, Brésil/Amérique latine) : foot du monde entier, crypto
(hausse/baisse du bitcoin par heure et par jour), politique… Lecture seule de l'API publique, sans compte.
La plupart des mises y sont en monnaie de jeu : le bot observe et apprend, mais ne mise pas ici."""
from .commun import categorie, date_iso, lire_json, maintenant, nombre

BASE = "https://api.futuur.com/api/v1"


def _prix(o):
    p = o.get("price") or {}
    v = nombre(p.get("USDC"))
    if v is None:
        v = nombre(p.get("OOM"))
    return v if v is not None and 0 < v < 1 else None


class Futuur:
    nom = "futuur"
    argent_reel = False                   # surtout de la monnaie de jeu : apprentissage seulement

    def frais(self, prix):
        return 0.0

    def candidats(self, jours_max, pages=8):
        out = []
        for p in range(pages):
            r = lire_json(f"{BASE}/markets/?limit=100&offset={p * 100}")
            lot = r.get("results", []) if isinstance(r, dict) else []
            for m in lot:
                c = self._normaliser(m)
                if c:
                    out.append(c)
            if not (r.get("pagination") or {}).get("next"):
                break
        return out

    def _normaliser(self, m):
        if not m or "id" not in m:
            return None
        outs = sorted((o for o in m.get("outcomes") or [] if not o.get("disabled")), key=lambda o: o.get("id", 0))
        if m.get("outcomes_type") == "updown":
            if len(outs) != 1 or _prix(outs[0]) is None:
                return None
            p = _prix(outs[0])
            issues, cotes = ["Hausse", "Baisse"], [p, round(1 - p, 4)]
            ids = ["hausse", "baisse"]
        else:
            if len(outs) < 2 or any(_prix(o) is None for o in outs):
                return None
            issues, cotes, ids = [o.get("title", "") for o in outs], [_prix(o) for o in outs], [o["id"] for o in outs]
        if m.get("outcomes_type") == "updown" or "bitcoin" in (m.get("title", "").lower()):
            cat = "crypto"
        elif m.get("event_type") == "soccer_match":
            cat = "foot"
        else:
            cat = categorie(m.get("title", ""))
        return {"site": self.nom, "id": str(m["id"]), "slug": m.get("slug", ""), "question": m.get("title", ""),
                "issues": issues, "cotes": cotes, "achat": list(cotes), "fin": date_iso(m.get("bet_end_date")),
                "volume": (nombre(m.get("volume_real_money")) or 0) + (nombre(m.get("volume_play_money")) or 0),
                "cat": cat, "_ids": ids, "_statut": m.get("status"), "_type": m.get("outcomes_type"),
                "_resolution": m.get("resolution"), "_extra": m.get("event_extra_data") or {}}

    def adresses(self, marche):
        return [f"{BASE}/markets/{marche['id']}/"] * 6

    def lire(self, url):
        c = self._normaliser(lire_json(url))
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"],
                "ferme": c["_statut"] != "open" or (c["fin"] and c["fin"] <= maintenant())}

    def resultat(self, marche):
        lectures = []
        for _ in range(2):
            c = self._normaliser(lire_json(f"{BASE}/markets/{marche['id']}/"))
            if not c:
                return {"fini": False}
            statut = str(c["_statut"]).lower()
            if statut in ("cancelled", "canceled", "voided"):
                lectures.append("rembourse")
                continue
            if statut != "resolved":
                return {"fini": False}
            if c["_type"] == "updown":
                o, f = nombre(c["_extra"].get("open_price")), nombre(c["_extra"].get("close_price"))
                if o is None or f is None:
                    return {"fini": False}
                lectures.append([1.0, 0.0] if f >= o else [0.0, 1.0])
            else:
                gagnant = (c["_resolution"] or {}).get("id")
                if gagnant not in c["_ids"]:
                    return {"fini": False}
                lectures.append([1.0 if i == gagnant else 0.0 for i in c["_ids"]])
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        if lectures[0] == "rembourse":
            return {"fini": True, "rembourse": True}
        return {"fini": True, "paiement": lectures[0]}
