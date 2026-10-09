"""ESPN (cotes du bookmaker DraftKings affichées par ESPN) : foot de nombreux pays (Angleterre, Espagne,
Allemagne, Italie, France, Pays-Bas, Portugal, Brésil, Argentine, Mexique, Japon…), football américain
universitaire et NFL, NBA, NHL, MLB… Lecture seule de l'API publique d'ESPN, sans compte.
Les résultats viennent du même tableau des scores une fois le match terminé."""
from datetime import timedelta

from .commun import date_iso, lire_json, maintenant, nombre

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

    def _url(self, sport, ligue, jour):
        return f"{BASE}/{sport}/{ligue}/scoreboard?dates={jour}&limit=300"     # un seul jour par adresse

    def candidats(self, jours_max, jours=3):
        t0 = maintenant() - timedelta(hours=5)             # les journées d'ESPN suivent l'heure américaine
        out, vus = [], set()
        for sport, ligue, cat in LIGUES:
            for n in range(min(jours, jours_max)):
                try:
                    r = lire_json(self._url(sport, ligue, f"{t0 + timedelta(days=n):%Y%m%d}"), essais=2, pause=1)
                except Exception:
                    break                                  # ligue hors saison ou absente : on passe
                for ev in (r or {}).get("events") or []:
                    c = self._normaliser(ev, sport, ligue, cat)
                    if c and c["_etat"] == "pre" and c["id"] not in vus:
                        vus.add(c["id"])
                        out.append(c)
        return out

    def _normaliser(self, ev, sport, ligue, cat, cle_cote="close"):
        try:
            return self._normaliser_brut(ev, sport, ligue, cat, cle_cote)
        except (AttributeError, KeyError, IndexError, TypeError, ValueError):
            return None                                    # match au format inattendu : ignoré

    def _normaliser_brut(self, ev, sport, ligue, cat, cle_cote):
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
        return {"site": self.nom, "id": f"{sport}/{ligue}/{ev['id']}", "slug": ",".join(sorted({f"{debut - timedelta(hours=5):%Y%m%d}", f"{debut:%Y%m%d}"})),
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
        """L'adresse peut porter deux jours (« 20261009,20261010 ») : on cherche le match dans chacun."""
        base, mid = url.split("#", 1)
        sport, ligue, eid = mid.split("/")
        racine, jours = base.split("dates=", 1)
        jours, reste = (jours.split("&", 1) + [""])[:2]
        for jour in jours.split(","):
            for ev in (lire_json(f"{racine}dates={jour}&{reste}") or {}).get("events") or []:
                if str(ev.get("id")) == eid:
                    return self._normaliser(ev, sport, ligue, "")
        return None

    def lire(self, url):
        c = self._trouver(url)
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"],
                "ferme": c["_etat"] != "pre" or c["fin"] - timedelta(hours=4) <= maintenant()}

    def _evenement(self, sport, ligue, jours, eid):
        for jour in jours.split(","):
            for ev in (lire_json(self._url(sport, ligue, jour)) or {}).get("events") or []:
                if str(ev.get("id")) == eid:
                    return ev
        return None

    def _lire_resultat(self, ev, sport):
        """Résultat lu SANS les cotes (ESPN les retire après le match). Même ordre d'issues que les cotes :
        domicile, extérieur, puis nul au foot."""
        comp = (ev.get("competitions") or [{}])[0]
        statut = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
        if not statut.get("completed"):
            return None
        equipes = {c.get("homeAway"): c for c in comp.get("competitors") or []}
        if "home" not in equipes or "away" not in equipes:
            return None
        nom = str(statut.get("name", "")).upper() + " " + str(statut.get("detail", "")).upper()
        if any(x in nom for x in ("CANCEL", "POSTPON", "ABANDON", "FORFEIT")):
            return "rembourse"
        if sport == "soccer":
            # pari « 1 N 2 » = temps réglementaire : prolongation ou tirs au but -> on ne sait pas, remboursé
            if any(x in nom for x in ("AET", "PEN", "EXTRA", "SHOOTOUT")):
                return "rembourse"
            d, x = nombre(equipes["home"].get("score")), nombre(equipes["away"].get("score"))
            if d is None or x is None:
                return None
            return [float(d > x), float(x > d), float(d == x)]
        g = [bool(equipes["home"].get("winner")), bool(equipes["away"].get("winner"))]
        return [float(g[0]), float(g[1])] if sum(g) == 1 else "rembourse"

    def resultat(self, marche):
        sport, ligue, eid = marche["id"].split("/")
        lectures = []
        for _ in range(2):
            ev = self._evenement(sport, ligue, marche.get("slug") or "", eid)
            r = self._lire_resultat(ev, sport) if ev else None
            if r is None:
                return {"fini": False}
            lectures.append(r)
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        if lectures[0] == "rembourse":
            return {"fini": True, "rembourse": True}
        return {"fini": True, "paiement": lectures[0]}
