"""Manifold Markets (argent VIRTUEL, « mana »). Idéal pour l'entraînement : beaucoup de marchés,
y compris les plus absurdes. Ses cotes sont moins fiables (pas d'argent réel en jeu), donc
l'apprentissage Manifold est tenu à part et le bot n'y mise pas sa bankroll « argent réel »."""
from datetime import timedelta

from .commun import categorie, date_iso, lire_json, maintenant, nombre

BASE = "https://api.manifold.markets/v0"


class Manifold:
    nom = "manifold"
    argent_reel = False

    def frais(self, prix):
        return 0.0

    def candidats(self, jours_max, parieurs_min=10):
        limite = maintenant() + timedelta(days=jours_max)
        out = []
        for page in range(3):                      # triés par date de fin : les plus proches d'abord
            lot = lire_json(f"{BASE}/search-markets?term=&filter=open&contractType=BINARY"
                            f"&sort=close-date&limit=1000&offset={page * 1000}")
            for m in lot:
                c = self._normaliser(m)
                if c and c["fin"] and c["fin"] <= limite and (m.get("uniqueBettorCount") or 0) >= parieurs_min:
                    out.append(c)
            if not lot or (date_iso(lot[-1].get("closeTime")) or limite) > limite:
                break
        return out

    def _normaliser(self, m):
        if m.get("outcomeType") != "BINARY" or m.get("isResolved"):
            return None
        p = nombre(m.get("probability"))
        if p is None or not 0 < p < 1:
            return None
        return {"site": self.nom, "id": m["id"], "slug": m.get("slug", ""), "question": m.get("question", ""),
                "issues": ["Oui", "Non"], "cotes": [round(p, 4), round(1 - p, 4)],
                "achat": [round(p, 4), round(1 - p, 4)],
                "fin": date_iso(m.get("closeTime")), "volume": nombre(m.get("volume")) or 0.0,
                "cat": categorie(m.get("question", ""), m.get("slug", ""))}

    def adresses(self, marche):
        return [f"{BASE}/market/{marche['id']}"] * 3 + [f"{BASE}/slug/{marche['slug']}"] * 3

    def lire(self, url):
        m = lire_json(url)
        c = self._normaliser(m) if m else None
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"],
                "ferme": bool(m.get("isResolved")) or (c["fin"] is not None and c["fin"] <= maintenant())}

    def resultat(self, marche):
        lectures = []
        for url in (f"{BASE}/market/{marche['id']}", f"{BASE}/slug/{marche['slug']}"):
            m = lire_json(url)
            if not m.get("isResolved"):
                return {"fini": False}
            r = m.get("resolution")
            if r == "YES":
                lectures.append([1.0, 0.0])
            elif r == "NO":
                lectures.append([0.0, 1.0])
            elif r == "MKT":
                q = nombre(m.get("resolutionProbability")) or 0.5
                lectures.append([q, 1 - q])
            else:
                lectures.append("rembourse")
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        if lectures[0] == "rembourse":
            return {"fini": True, "rembourse": True}
        return {"fini": True, "paiement": lectures[0]}

    def historique(self, curseur, nombre_max=60, heures_avant=24, parieurs_min=10):
        """Marchés Manifold terminés : probabilité `heures_avant` heures avant la fin (dernier pari
        avant ce moment). Si un côté était > 97 %, on note s'il a gagné."""
        # le site refuse les décalages au-delà de 1000 : on change d'ordre de tri tous les 1000 marchés
        tris = ["most-popular", "newest", "resolve-date", "liquidity", "24-hour-vol", "score", "last-updated"]
        tri, decalage = tris[(curseur // 1000) % len(tris)], curseur % 1000
        nombre_max = min(nombre_max, 1000 - decalage)
        lot = lire_json(f"{BASE}/search-markets?term=&filter=resolved&contractType=BINARY"
                        f"&sort={tri}&limit={nombre_max}&offset={decalage}")
        out = []
        for m in lot or []:
            try:
                if m.get("resolution") not in ("YES", "NO") or (m.get("uniqueBettorCount") or 0) < parieurs_min:
                    continue
                fin_ms = min(x for x in (m.get("closeTime"), m.get("resolutionTime")) if x)
                t_obs = int(fin_ms - heures_avant * 3600 * 1000)
                paris = lire_json(f"{BASE}/bets?contractId={m['id']}&beforeTime={t_obs}&limit=1")
                if not paris:
                    continue
                p_oui = nombre(paris[0].get("probAfter"))
                if p_oui is None:
                    continue
                gagnant = 0 if m["resolution"] == "YES" else 1
                for idx, p in ((0, p_oui), (1, 1 - p_oui)):
                    if 0.97 < p < 1.0:
                        out.append({"site": self.nom, "id": m["id"], "question": m.get("question", ""),
                                    "cat": categorie(m.get("question", ""), m.get("slug", "")), "idx": idx,
                                    "prix": round(p, 4), "gagne": int(idx == gagnant), "horizon_h": heures_avant,
                                    "fin": date_iso(fin_ms).isoformat(), "source": "historique"})
            except Exception:
                continue
        return out, (curseur + len(lot)) if lot else (curseur // 1000 + 1) * 1000   # liste finie : tri suivant
