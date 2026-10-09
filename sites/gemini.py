"""Gemini Predictions (bourse de prédiction américaine régulée de Gemini) : crypto (BTC/ETH/SOL toutes les
5 min, 15 min, heures, jours), sport, politique… Lecture seule de l'API publique, sans compte.
Chaque « contrat » d'un événement est un pari Oui/Non : c'est lui que le bot suit."""
from .commun import categorie, date_iso, lire_json, maintenant, nombre

BASE = "https://api.gemini.com/v1/prediction-markets"
# (catégorie, pages de 100) : les événements sportifs sont très lourds, on en lit moins
CATEGORIES = [("Crypto", 5), ("Politics", 2), ("Economics", 2), ("Culture", 1), ("Weather", 1), ("Tech", 1),
              ("Sports", 1)]


class Gemini:
    nom = "gemini"
    argent_reel = True

    def frais(self, prix):
        return 0.07 * (1 - prix)          # même ordre de grandeur que Kalshi (prudent)

    def candidats(self, jours_max, par_page=100):
        out, vus = [], set()
        for cat, pages in CATEGORIES:
            for p in range(pages):
                r = lire_json(f"{BASE}/events?status=active&limit={par_page}&offset={p * par_page}&category={cat}")
                lot = r.get("data", []) if isinstance(r, dict) else []
                lot = [ev for ev in lot if ev.get("category") == cat]     # filtre ignoré -> on n'insiste pas
                for ev in lot:
                    for c in self._contrats(ev):
                        if c["id"] not in vus:
                            vus.add(c["id"])
                            out.append(c)
                if len(lot) < par_page:
                    break
        return out

    def _contrats(self, ev):
        out = []
        cat = "crypto" if ev.get("category") == "Crypto" else categorie(ev.get("title", ""), ev.get("ticker", ""))
        for k in ev.get("contracts") or []:
            sym = k.get("instrumentSymbol")
            if not sym or k.get("isCombo"):
                continue
            px = k.get("prices") or {}
            bid, ask = nombre(px.get("bestBid")), nombre(px.get("bestAsk"))
            achat = [nombre((px.get("buy") or {}).get("yes")), nombre((px.get("buy") or {}).get("no"))]
            achat = [a if a is not None and 0 < a < 1 else None for a in achat]
            if bid is not None and ask is not None and 0 < bid <= ask < 1:
                oui = (bid + ask) / 2
                if ask - bid > 0.05:
                    achat = [None, None]          # écart achat/vente trop grand : prix pas fiable
            elif achat[0] is not None:
                oui = achat[0]
            else:
                continue
            titre = ev.get("title", "")
            lab = k.get("label", "")
            out.append({"site": self.nom, "id": sym, "slug": ev.get("ticker", ""),
                        "question": f"{titre} — {lab}" if lab and lab not in titre else titre,
                        "issues": ["Oui", "Non"], "cotes": [round(oui, 4), round(1 - oui, 4)], "achat": achat,
                        "fin": date_iso(k.get("expiryDate") or ev.get("expiryDate")),
                        "volume": nombre(ev.get("volume")) or 0.0, "cat": cat,
                        "_etat": k.get("marketState"), "_statut": k.get("status"),
                        "_cote": k.get("resolutionSide")})
        return out

    def adresses(self, marche):
        # l'adresse de l'événement, relue 6 fois (le # sert seulement à savoir quel contrat regarder)
        return [f"{BASE}/events/{marche['slug']}#{marche['id']}"] * 6

    def _lire_contrat(self, url):
        base, sym = url.split("#", 1)
        ev = lire_json(base)
        return ev, next((c for c in self._contrats(ev) if c["id"] == sym), None)

    def lire(self, url):
        ev, c = self._lire_contrat(url)
        if not c:
            return None
        ferme = c["_etat"] != "open" or c["_statut"] != "active" or (c["fin"] and c["fin"] <= maintenant())
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"], "ferme": bool(ferme)}

    def resultat(self, marche):
        lectures = []
        url = f"{BASE}/events/{marche['slug']}#{marche['id']}"
        for _ in range(2):
            ev, c = self._lire_contrat(url)
            statut = str(ev.get("status", "")).lower()
            if c is None:
                k = next((k for k in ev.get("contracts") or [] if k.get("instrumentSymbol") == marche["id"]), None)
                cote = (k or {}).get("resolutionSide")
                statut_c = str((k or {}).get("status", "")).lower()
            else:
                cote, statut_c = c["_cote"], str(c["_statut"]).lower()
            if statut_c in ("cancelled", "canceled", "voided", "void") or statut in ("cancelled", "canceled"):
                lectures.append("rembourse")
            elif cote in ("yes", "no") and (statut_c == "settled" or statut == "settled"):
                lectures.append([1.0, 0.0] if cote == "yes" else [0.0, 1.0])
            else:
                return {"fini": False}
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        if lectures[0] == "rembourse":
            return {"fini": True, "rembourse": True}
        return {"fini": True, "paiement": lectures[0]}
