"""ESPN (cotes du bookmaker DraftKings affichées par ESPN) : foot de nombreux pays (Angleterre, Espagne,
Allemagne, Italie, France, Pays-Bas, Portugal, Brésil, Argentine, Mexique, Japon…), football américain
universitaire et NFL, NBA, NHL, MLB… Lecture seule de l'API publique d'ESPN, sans compte.
Les résultats viennent du même tableau des scores une fois le match terminé."""
from datetime import timedelta

from .commun import date_iso, lire_json, maintenant

BASE = "https://site.web.api.espn.com/apis/site/v2/sports"
LIGUES = [  # (sport, ligue, catégorie du bot)
    ("football", "college-football", "sport US"), ("football", "nfl", "sport US"),
    ("basketball", "nba", "basket"), ("basketball", "wnba", "basket"),
    ("basketball", "mens-college-basketball", "basket"), ("basketball", "womens-college-basketball", "basket"),
    ("baseball", "mlb", "sport US"), ("hockey", "nhl", "hockey"),
    ("soccer", "eng.1", "foot"), ("soccer", "eng.2", "foot"), ("soccer", "esp.1", "foot"), ("soccer", "esp.2", "foot"),
    ("soccer", "ger.1", "foot"), ("soccer", "ita.1", "foot"), ("soccer", "fra.1", "foot"), ("soccer", "ned.1", "foot"),
    ("soccer", "por.1", "foot"), ("soccer", "bel.1", "foot"), ("soccer", "tur.1", "foot"), ("soccer", "sco.1", "foot"),
    ("soccer", "usa.1", "foot"), ("soccer", "mex.1", "foot"), ("soccer", "bra.1", "foot"), ("soccer", "arg.1", "foot"),
    ("soccer", "jpn.1", "foot"), ("soccer", "ksa.1", "foot"), ("soccer", "uefa.champions", "foot"),
    ("soccer", "uefa.europa", "foot"), ("soccer", "fifa.worldq.uefa", "foot"),
]
COTE_CLE = {"home": "domicile", "away": "extérieur", "draw": "nul"}


def proba_us(cote):
    """Cote américaine (-500, +380, EVEN) -> probabilité implicite (marge du bookmaker comprise)."""
    s = str(cote or "").strip().upper()
    if s in ("EVEN", "EV"):
        return 0.5
    try:
        v = float(s)
    except ValueError:
        return None
    if v <= -100:
        return -v / (-v + 100)
    if v >= 100:
        return 100 / (v + 100)
    return None


class Espn:
    nom = "espn"
    argent_reel = True

    def frais(self, prix):
        return 0.0                        # la marge du bookmaker est déjà dans le prix

    def _url(self, sport, ligue, jours):
        return f"{BASE}/{sport}/{ligue}/scoreboard?dates={jours}&limit=300"

    @staticmethod
    def _plage(t0, n):
        return f"{t0:%Y%m%d}-{t0 + timedelta(days=n):%Y%m%d}"

    def candidats(self, jours_max, jours=3):
        t0 = maintenant()
        out = []
        for sport, ligue, cat in LIGUES:
            try:
                r = lire_json(self._url(sport, ligue, self._plage(t0, min(jours, jours_max))), essais=2, pause=1)
            except Exception:
                continue                                   # ligue hors saison ou absente : on passe
            for ev in r.get("events", []):
                c = self._normaliser(ev, sport, ligue, cat)
                if c and c["_etat"] == "pre":
                    out.append(c)
        return out

    def _normaliser(self, ev, sport, ligue, cat, cle_cote="close"):
        try:
            comp = ev["competitions"][0]
            equipes = {c["homeAway"]: c for c in comp["competitors"]}
            ml = (comp.get("odds") or [{}])[0].get("moneyline") or {}
        except (KeyError, IndexError, TypeError):
            return None
        cotes_bk = {}
        for cote in ("home", "away", "draw"):
            p = proba_us(((ml.get(cote) or {}).get(cle_cote) or {}).get("odds"))
            if p is not None:
                cotes_bk[cote] = p
        if "home" not in cotes_bk or "away" not in cotes_bk:
            return None
        if sport == "soccer" and "draw" not in cotes_bk:
            return None                                    # le nul existe au foot : sans lui, cote incomplète
        issues = [c for c in ("home", "away", "draw") if c in cotes_bk]
        somme = sum(cotes_bk.values())
        if not 0.9 < somme < 1.25:
            return None
        noms = {k: (equipes.get(k, {}).get("team") or {}).get("displayName", k) for k in ("home", "away")}
        noms["draw"] = "Match nul"
        etat = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
        debut = date_iso(ev.get("date"))
        if not debut:
            return None
        return {"site": self.nom, "id": f"{sport}/{ligue}/{ev['id']}", "slug": f"{debut - timedelta(days=1):%Y%m%d}-{debut:%Y%m%d}",
                "question": f"{ev.get('name', '')} ({ligue})", "issues": [noms[c] for c in issues],
                # sans la marge du bookmaker (marge retirée à parts égales, méthode additive : sur un gros
                # favori elle ne l'écrase pas comme la division proportionnelle)
                "cotes": [round(min(0.9999, max(0.0001, cotes_bk[c] - (somme - 1) / len(issues))), 4) for c in issues],
                "achat": [round(cotes_bk[c], 4) for c in issues],                  # prix réellement payé
                "fin": debut + timedelta(hours=4), "volume": 0.0, "cat": cat,
                "_etat": etat.get("state"), "_fini": bool(etat.get("completed")), "_cles": issues,
                "_gagnants": [bool((equipes.get(c) or {}).get("winner")) for c in issues]}

    def adresses(self, marche):
        sport, ligue, _ = marche["id"].split("/")
        return [self._url(sport, ligue, marche["slug"]) + f"#{marche['id']}"] * 6

    def _trouver(self, url):
        base, mid = url.split("#", 1)
        sport, ligue, eid = mid.split("/")
        for ev in lire_json(base).get("events", []):
            if str(ev.get("id")) == eid:
                return self._normaliser(ev, sport, ligue, "")
        return None

    def lire(self, url):
        c = self._trouver(url)
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"],
                "ferme": c["_etat"] != "pre" or c["fin"] - timedelta(hours=4) <= maintenant()}

    def resultat(self, marche):
        sport, ligue, _ = marche["id"].split("/")
        jour = marche.get("slug") or ""
        url = self._url(sport, ligue, jour) + f"#{marche['id']}"
        lectures = []
        for _ in range(2):
            c = self._trouver(url)
            if not c or not c["_fini"]:
                return {"fini": False}
            g = c["_gagnants"]
            if sum(g) == 1:
                lectures.append([1.0 if x else 0.0 for x in g])
            elif sum(g) == 0 and "draw" in c["_cles"]:
                lectures.append([1.0 if k == "draw" else 0.0 for k in c["_cles"]])
            else:
                lectures.append("rembourse")               # égalité sans option « nul » : remboursé
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        if lectures[0] == "rembourse":
            return {"fini": True, "rembourse": True}
        return {"fini": True, "paiement": lectures[0]}

    def historique(self, curseur, nombre_max=250, heures_avant=24, ligues_par_passage=12):
        """Matchs déjà joués : cote de clôture DraftKings (juste avant le match) et résultat.
        Le curseur avance d'un jour en arrière à chaque passage, sur un groupe de ligues à la fois."""
        curseur = int(curseur or 0)
        jour = maintenant() - timedelta(days=1 + curseur // 3)
        groupe = curseur % 3
        out = []
        for sport, ligue, cat in LIGUES[groupe::3][:ligues_par_passage]:
            try:
                r = lire_json(self._url(sport, ligue, f"{jour:%Y%m%d}"), essais=2, pause=1)
            except Exception:
                continue
            for ev in r.get("events", []):
                c = self._normaliser(ev, sport, ligue, cat)
                if not c or not c["_fini"] or sum(c["_gagnants"]) > 1:
                    continue
                g = c["_gagnants"] if sum(c["_gagnants"]) == 1 else [k == "draw" for k in c["_cles"]]
                if not any(g):
                    continue
                for idx, p in enumerate(c["cotes"]):
                    if 0.97 < p < 1.0:
                        out.append({"site": self.nom, "id": c["id"], "question": c["question"], "cat": cat,
                                    "idx": idx, "prix": p, "gagne": int(g[idx]), "horizon_h": 0,
                                    "fin": c["fin"].isoformat(), "source": "historique"})
            if len(out) >= nombre_max:
                break
        return out, curseur + 1
