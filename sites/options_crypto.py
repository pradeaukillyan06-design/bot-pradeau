"""Options crypto (Deribit — Panama/Dubaï — et OKX — Seychelles) : les prix des options disent quelle
probabilité le marché donne à « le bitcoin (ou l'ether) finira au-dessus de X € le jour J à 8 h UTC ».
Probabilité « risque-neutre » = N(d2), calculée avec la volatilité du marché et le prix à terme.
Le résultat est le prix de règlement officiel publié par la bourse. Lecture seule, sans compte.
On ne peut pas acheter ce pari tel quel : le bot observe et apprend seulement (jamais de mise)."""
import math
from datetime import datetime, timezone

from .commun import lire_json, maintenant, nombre

MOIS = {m: i + 1 for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
                                        "NOV", "DEC"])}


def proba_au_dessus(fwd, strike, vol, annees):
    """N(d2) du modèle de Black : probabilité que le prix final dépasse le strike."""
    if not (fwd and strike and vol and annees) or fwd <= 0 or strike <= 0 or vol <= 0 or annees <= 0:
        return None
    s = vol * math.sqrt(annees)
    d2 = (math.log(fwd / strike) - s * s / 2) / s
    return 0.5 * (1 + math.erf(d2 / math.sqrt(2)))


def _marche(site, mid, actif, strike, echeance, p):
    if p is None:
        return None
    p = round(min(0.9999, max(0.0001, p)), 4)
    return {"site": site, "id": mid, "slug": f"{actif}|{echeance:%Y-%m-%d}|{strike:g}",
            "question": f"{actif} au-dessus de {strike:,.0f} $ le {echeance:%d/%m/%Y} à 8 h UTC ?".replace(",", " "),
            "issues": ["Au-dessus", "En dessous"], "cotes": [p, round(1 - p, 4)], "achat": [p, round(1 - p, 4)],
            "fin": echeance, "volume": 0.0, "cat": "crypto"}


def _resultat_prix(prix_final, strike):
    if prix_final is None:
        return {"fini": False}
    return {"fini": True, "paiement": [1.0, 0.0] if prix_final > strike else [0.0, 1.0]}


class Deribit:
    nom = "deribit"
    argent_reel = False                      # probabilité tirée des options : on observe, on ne mise pas
    BASE = "https://www.deribit.com/api/v2/public"
    ACTIFS = {"BTC": "btc_usd", "ETH": "eth_usd"}

    def frais(self, prix):
        return 0.0

    @staticmethod
    def _echeance(nom):
        # BTC-12OCT26-84500-C -> 12/10/2026 08:00 UTC
        j = nom.split("-")[1]
        return datetime(2000 + int(j[-2:]), MOIS[j[-5:-2]], int(j[:-5]), 8, tzinfo=timezone.utc)

    def _depuis_resume(self, r):
        nom = r.get("instrument_name", "")
        if not nom.endswith("-C"):
            return None                      # une seule option par strike suffit (call)
        actif, _, strike, _ = nom.split("-")
        ech = self._echeance(nom)
        annees = (ech - maintenant()).total_seconds() / (365.25 * 86400)
        if annees < 2 / (365.25 * 24):       # moins de 2 h : la volatilité affichée n'est plus fiable
            return None
        p = proba_au_dessus(nombre(r.get("underlying_price")), float(strike),
                            (nombre(r.get("mark_iv")) or 0) / 100, annees)
        return _marche(self.nom, nom, actif, float(strike), ech, p)

    def candidats(self, jours_max):
        out = []
        for actif in self.ACTIFS:
            for r in lire_json(f"{self.BASE}/get_book_summary_by_currency?currency={actif}&kind=option").get("result", []):
                c = self._depuis_resume(r)
                if c and (nombre(r.get("open_interest")) or 0) > 0:
                    out.append(c)
        return out

    def adresses(self, marche):
        return [f"{self.BASE}/get_book_summary_by_instrument?instrument_name={marche['id']}"] * 6

    def lire(self, url):
        res = lire_json(url).get("result") or []
        c = self._depuis_resume(res[0]) if res else None
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"], "ferme": c["fin"] <= maintenant()}

    def resultat(self, marche):
        actif, jour, strike = marche["slug"].split("|")
        lectures = []
        for _ in range(2):
            r = lire_json(f"{self.BASE}/get_delivery_prices?index_name={self.ACTIFS[actif]}&count=40")
            prix = next((nombre(x.get("delivery_price")) for x in (r.get("result") or {}).get("data", [])
                         if x.get("date") == jour), None)
            lectures.append(_resultat_prix(prix, float(strike)))
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        return lectures[0]


class Okx:
    nom = "okx"
    argent_reel = False
    BASE = "https://www.okx.com/api/v5/public"
    ACTIFS = ["BTC-USD", "ETH-USD"]

    def frais(self, prix):
        return 0.0

    @staticmethod
    def _decoupe(inst):
        # BTC-USD_UM-261023-74000-C (ou BTC-USD-261023-74000-C)
        morceaux = inst.split("-")
        jour, strike, sens = morceaux[-3], float(morceaux[-2]), morceaux[-1]
        ech = datetime(2000 + int(jour[:2]), int(jour[2:4]), int(jour[4:6]), 8, tzinfo=timezone.utc)
        return morceaux[0], jour, strike, sens, ech

    def _depuis_resume(self, r):
        inst = r.get("instId", "")
        try:
            actif, _, strike, sens, ech = self._decoupe(inst)
        except (ValueError, IndexError):
            return None
        if sens != "C":
            return None
        annees = (ech - maintenant()).total_seconds() / (365.25 * 86400)
        if annees < 2 / (365.25 * 24):
            return None
        p = proba_au_dessus(nombre(r.get("fwdPx")), strike, nombre(r.get("markVol")), annees)
        return _marche(self.nom, inst, actif, strike, ech, p)

    def candidats(self, jours_max):
        out, vus = [], set()
        for u in self.ACTIFS:
            for r in lire_json(f"{self.BASE}/opt-summary?uly={u}").get("data", []):
                c = self._depuis_resume(r)
                if c and c["slug"] not in vus:       # deux familles d'options pour un même strike : une seule
                    vus.add(c["slug"])
                    out.append(c)
        return out

    def adresses(self, marche):
        _, jour, *_ = self._decoupe(marche["id"])
        uly = marche["id"].split("_")[0] if "_" in marche["id"] else "-".join(marche["id"].split("-")[:2])
        return [f"{self.BASE}/opt-summary?uly={uly}&expTime={jour}#{marche['id']}"] * 6

    def lire(self, url):
        base, inst = url.split("#", 1)
        r = next((x for x in lire_json(base).get("data", []) if x.get("instId") == inst), None)
        c = self._depuis_resume(r) if r else None
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"], "ferme": c["fin"] <= maintenant()}

    def resultat(self, marche):
        inst = marche["id"]
        uly = inst.split("_")[0] if "_" in inst else "-".join(inst.split("-")[:2])
        _, _, strike, _, _ = self._decoupe(inst)
        lectures = []
        for _ in range(2):
            prix = None
            for lot in lire_json(f"{self.BASE}/delivery-exercise-history?instType=OPTION&uly={uly}&limit=20").get("data", []):
                for d in lot.get("details", []):
                    if d.get("insId") == inst:
                        prix = nombre(d.get("px"))
            lectures.append(_resultat_prix(prix, strike))
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        return lectures[0]
