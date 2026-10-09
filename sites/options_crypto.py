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


def _annees(ech):
    return (ech - maintenant()).total_seconds() / (365.25 * 86400)


class DeltaInde:
    """Delta Exchange India (Inde) : options bitcoin et ether, réglées chaque jour à 12 h UTC."""
    nom = "delta_inde"
    argent_reel = False
    BASE = "https://api.india.delta.exchange/v2"
    ACTIFS = ["BTC", "ETH"]

    def frais(self, prix):
        return 0.0

    @staticmethod
    def _decoupe(sym):
        # C-BTC-99000-271126 -> BTC, 99000, 27/11/2026 12:00 UTC
        sens, actif, strike, jour = sym.split("-")
        ech = datetime(2000 + int(jour[4:6]), int(jour[2:4]), int(jour[:2]), 12, tzinfo=timezone.utc)
        return sens, actif, float(strike), ech

    def _depuis_ticker(self, r):
        try:
            sens, actif, strike, ech = self._decoupe(r.get("symbol", ""))
        except (ValueError, IndexError):
            return None
        if sens != "C" or _annees(ech) < 2 / (365.25 * 24):
            return None
        spot = nombre(r.get("spot_price")) or nombre((r.get("greeks") or {}).get("spot"))
        vol = nombre(r.get("mark_vol")) or nombre((r.get("quotes") or {}).get("mark_iv"))
        c = _marche(self.nom, r["symbol"], actif, strike, ech, proba_au_dessus(spot, strike, vol, _annees(ech)))
        if c:
            c["question"] = c["question"].replace("8 h UTC", "12 h UTC")
        return c

    def candidats(self, jours_max):
        out = []
        for a in self.ACTIFS:
            r = lire_json(f"{self.BASE}/tickers?contract_types=call_options&underlying_asset_symbols={a}")
            for t in r.get("result") or []:
                c = self._depuis_ticker(t)
                if c and (nombre(t.get("oi")) or 0) > 0:
                    out.append(c)
        return out

    def adresses(self, marche):
        return [f"{self.BASE}/tickers/{marche['id']}"] * 6

    def lire(self, url):
        c = self._depuis_ticker(lire_json(url).get("result") or {})
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"], "ferme": c["fin"] <= maintenant()}

    def resultat(self, marche):
        _, _, strike, _ = self._decoupe(marche["id"])
        lectures = []
        for _ in range(2):
            p = lire_json(f"{self.BASE}/products/{marche['id']}").get("result") or {}
            prix = nombre((p.get("product_specs") or {}).get("settlement_index_price")) if p.get("state") == "expired" else None
            lectures.append(_resultat_prix(prix, strike))
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        return lectures[0]


class Gate:
    """Gate (bourse crypto internationale) : options bitcoin et ether."""
    nom = "gate"
    argent_reel = False
    BASE = "https://api.gateio.ws/api/v4/options"
    ACTIFS = ["BTC_USDT", "ETH_USDT"]

    def frais(self, prix):
        return 0.0

    def _depuis_ticker(self, r):
        nom = r.get("name", "")
        try:
            uly, jour, strike, sens = nom.split("-")
            strike = float(strike)
        except ValueError:
            return None
        ech = datetime.fromtimestamp(int(r.get("expiration_time") or 0), tz=timezone.utc) if r.get("expiration_time") \
            else datetime(int(jour[:4]), int(jour[4:6]), int(jour[6:8]), 8, tzinfo=timezone.utc)
        if sens != "C" or _annees(ech) < 2 / (365.25 * 24):
            return None
        p = proba_au_dessus(nombre(r.get("underlying_price")), strike, nombre(r.get("mark_iv")), _annees(ech))
        return _marche(self.nom, nom, uly.split("_")[0], strike, ech, p)

    def candidats(self, jours_max):
        out = []
        for u in self.ACTIFS:
            for t in lire_json(f"{self.BASE}/tickers?underlying={u}") or []:
                c = self._depuis_ticker(t)
                if c:
                    out.append(c)
        return out

    def adresses(self, marche):
        return [f"{self.BASE}/tickers?underlying={marche['id'].split('-')[0]}#{marche['id']}"] * 6

    def lire(self, url):
        base, nom = url.split("#", 1)
        r = next((t for t in lire_json(base) or [] if t.get("name") == nom), None)
        c = self._depuis_ticker(r) if r else None
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"], "ferme": c["fin"] <= maintenant()}

    def resultat(self, marche):
        uly, _, strike, _ = marche["id"].split("-")
        lectures = []
        for _ in range(2):
            lot = lire_json(f"{self.BASE}/settlements?underlying={uly}&limit=1000") or []
            prix = next((nombre(s.get("settle_price")) for s in lot if s.get("contract") == marche["id"]), None)
            lectures.append(_resultat_prix(prix, float(strike)))
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        return lectures[0]


class Aevo:
    """Aevo (bourse d'options décentralisée, internationale) : options bitcoin et ether."""
    nom = "aevo"
    argent_reel = False
    BASE = "https://api.aevo.xyz"
    ACTIFS = ["BTC", "ETH"]

    def frais(self, prix):
        return 0.0

    def _depuis_marche(self, r):
        nom = r.get("instrument_name", "")
        if r.get("option_type") != "call" or not r.get("is_active", True):
            return None
        try:
            ech = datetime.fromtimestamp(int(r["expiry"]) / 1e9, tz=timezone.utc)
            strike = float(r["strike"])
        except (KeyError, TypeError, ValueError):
            return None
        if _annees(ech) < 2 / (365.25 * 24):
            return None
        p = proba_au_dessus(nombre(r.get("forward_price")), strike, nombre((r.get("greeks") or {}).get("iv")),
                            _annees(ech))
        return _marche(self.nom, nom, r.get("underlying_asset", nom.split("-")[0]), strike, ech, p)

    def candidats(self, jours_max):
        out = []
        for a in self.ACTIFS:
            for r in lire_json(f"{self.BASE}/markets?asset={a}&instrument_type=OPTION") or []:
                c = self._depuis_marche(r)
                if c:
                    out.append(c)
        return out

    def adresses(self, marche):
        return [f"{self.BASE}/markets?asset={marche['id'].split('-')[0]}&instrument_type=OPTION#{marche['id']}"] * 6

    def lire(self, url):
        base, nom = url.split("#", 1)
        r = next((m for m in lire_json(base) or [] if m.get("instrument_name") == nom), None)
        c = self._depuis_marche(r) if r else None
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"], "ferme": c["fin"] <= maintenant()}

    def resultat(self, marche):
        actif, jour, strike = marche["slug"].split("|")
        lectures = []
        for _ in range(2):
            prix = None
            for s in lire_json(f"{self.BASE}/settlement-history?asset={actif}&limit=50") or []:
                try:
                    if datetime.fromtimestamp(int(s["expiry"]) / 1e9, tz=timezone.utc).strftime("%Y-%m-%d") == jour:
                        prix = nombre(s.get("settlement_price"))
                except (KeyError, TypeError, ValueError):
                    continue
            lectures.append(_resultat_prix(prix, float(strike)))
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        return lectures[0]


class Thalex:
    """Thalex (bourse d'options crypto, Gibraltar) : options bitcoin et ether."""
    nom = "thalex"
    argent_reel = False
    BASE = "https://thalex.com/api/v2/public"
    jours_lus = 7                                # options à moins de 7 jours : une lecture par option

    def frais(self, prix):
        return 0.0

    def _calls(self, liste="instruments"):
        return [i for i in lire_json(f"{self.BASE}/{liste}").get("result") or []
                if i.get("type") == "option" and i.get("option_type") == "call"]

    def _depuis(self, inst, t):
        if not inst or not t:
            return None
        ech = datetime.fromtimestamp(int(inst["expiration_timestamp"]), tz=timezone.utc)
        if _annees(ech) < 2 / (365.25 * 24):
            return None
        strike = float(inst["strike_price"])
        p = proba_au_dessus(nombre(t.get("forward")), strike, nombre(t.get("iv")), _annees(ech))
        return _marche(self.nom, inst["instrument_name"], inst["instrument_name"].split("-")[0], strike, ech, p)

    def candidats(self, jours_max, max_lectures=120):
        limite = maintenant().timestamp() + min(jours_max, self.jours_lus) * 86400
        out = []
        for inst in [i for i in self._calls() if i.get("expiration_timestamp", 0) <= limite][:max_lectures]:
            try:
                t = lire_json(f"{self.BASE}/ticker?instrument_name={inst['instrument_name']}", essais=2, pause=1)
            except Exception:
                continue
            c = self._depuis(inst, (t or {}).get("result"))
            if c:
                out.append(c)
        return out

    def adresses(self, marche):
        e = marche["fin"]
        return [f"{self.BASE}/ticker?instrument_name={marche['id']}#{int(e.timestamp())}"] * 6

    def lire(self, url):
        base, ts = url.split("#", 1)
        nom = base.split("instrument_name=")[1]
        inst = {"instrument_name": nom, "expiration_timestamp": int(ts), "strike_price": nom.split("-")[2]}
        c = self._depuis(inst, lire_json(base).get("result"))
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"], "ferme": c["fin"] <= maintenant()}

    def resultat(self, marche):
        strike = float(marche["id"].split("-")[2])
        lectures = []
        for _ in range(2):
            inst = next((i for i in lire_json(f"{self.BASE}/all_instruments").get("result") or []
                         if i.get("instrument_name") == marche["id"]), None)
            lectures.append(_resultat_prix(nombre((inst or {}).get("settlement_index_price")), strike))
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        return lectures[0]


class Derive:
    """Derive, ex-Lyra (bourse d'options décentralisée, internationale) : options bitcoin et ether."""
    nom = "derive"
    argent_reel = False
    BASE = "https://api.lyra.finance/public"
    ACTIFS = ["BTC", "ETH"]
    jours_lus = 7

    def frais(self, prix):
        return 0.0

    def _depuis(self, t):
        if not t:
            return None
        d = t.get("option_details") or {}
        if d.get("option_type") != "C" or not t.get("is_active", True):
            return None
        ech = datetime.fromtimestamp(int(d.get("expiry") or 0), tz=timezone.utc)
        if _annees(ech) < 2 / (365.25 * 24):
            return None
        strike = float(d.get("strike") or 0)
        pr = t.get("option_pricing") or {}
        p = proba_au_dessus(nombre(pr.get("forward_price")), strike, nombre(pr.get("iv")), _annees(ech))
        return _marche(self.nom, t["instrument_name"], t.get("base_currency") or t["instrument_name"].split("-")[0],
                       strike, ech, p)

    def candidats(self, jours_max, max_lectures=120):
        limite = maintenant().timestamp() + min(jours_max, self.jours_lus) * 86400
        noms = []
        for a in self.ACTIFS:
            r = lire_json(f"{self.BASE}/get_instruments",
                          corps={"currency": a, "instrument_type": "option", "expired": False})
            noms += [i["instrument_name"] for i in r.get("result") or []
                     if (i.get("option_details") or {}).get("option_type") == "C"
                     and (i.get("option_details") or {}).get("expiry", 0) <= limite]
        out = []
        for nom in noms[:max_lectures]:
            try:
                t = lire_json(f"{self.BASE}/get_ticker", corps={"instrument_name": nom}, essais=2, pause=1)
            except Exception:
                continue
            c = self._depuis((t or {}).get("result"))
            if c:
                out.append(c)
        return out

    def adresses(self, marche):
        return [f"{self.BASE}/get_ticker#{marche['id']}"] * 6

    def lire(self, url):
        base, nom = url.split("#", 1)
        c = self._depuis(lire_json(base, corps={"instrument_name": nom}).get("result"))
        if not c:
            return None
        return {"id": c["id"], "cotes": c["cotes"], "achat": c["achat"], "ferme": c["fin"] <= maintenant()}

    def resultat(self, marche):
        actif = marche["id"].split("-")[0]
        strike = float(marche["id"].split("-")[2])
        lectures = []
        for _ in range(2):
            r = lire_json(f"{self.BASE}/get_instruments",
                          corps={"currency": actif, "instrument_type": "option", "expired": True})
            inst = next((i for i in r.get("result") or [] if i.get("instrument_name") == marche["id"]), None)
            prix = nombre(((inst or {}).get("option_details") or {}).get("settlement_price"))
            lectures.append(_resultat_prix(prix, strike))
        if lectures[0] != lectures[1]:
            return {"fini": False, "contradiction": True}
        return lectures[0]


class DeltaMonde(DeltaInde):
    """Delta Exchange international (bourse distincte de Delta India : autres prix, autre carnet)."""
    nom = "delta_monde"
    BASE = "https://api.delta.exchange/v2"
