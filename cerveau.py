"""
Bot Pradeau — programme chef (paris FICTIFS uniquement).

Un seul programme gère tous les sites (un module par site dans sites/) et tient UN SEUL
cahier d'apprentissage commun (etat/etat.json). Il ne place jamais de vrai pari : il note
ce qu'il aurait parié, attend le résultat réel et apprend.

À chaque passage (toutes les 15 min via GitHub Actions) :
  1. vérifie les résultats des paris et observations terminés (2 lectures concordantes),
  2. met à jour ce qu'il a appris et revoit seul sa prise de risque,
  3. liste les marchés de chaque site, garde les côtés cotés > 97 %,
  4. relit chaque cote 6 fois (elles doivent concorder à 0,5 point près),
  5. enregistre une observation, et mise s'il a appris que le marché sous-estime ce pari.

Règles de Killyan (fixes) : seuil > 97 % ; mise choisie par le bot (Kelly) ; garde-fous de
mise.py (25 % max par pari, 80 % max engagé) ; au moins 5 lectures par cote (ici 6).
"""
import json
import statistics
import sys
import time
import traceback
from datetime import timedelta
from pathlib import Path

import mise as MI
from sites import TOUS
from sites.commun import date_iso, maintenant

ICI = Path(__file__).parent
ETAT = ICI / "etat" / "etat.json"
CFG = {
    "version": "chef-1.0",
    "seuil": 0.97,
    "lectures_min": 6,
    "ecart_lectures_max": 0.005,
    "pause_lectures_s": 0.5,
    "jours_max": 21,
    "verifs_max_par_site": 30,      # nouvelles cotes vérifiées par site et par passage
    "max_par_categorie": 5,         # variété : pas plus de 5 nouvelles cotes d'une même catégorie par passage
    "resolutions_max": 60,
    "force_prior": 30,
    "fraction_kelly": 0.25,
    "max_paris_ouverts": 60,
    "bankroll": 1000.0,
}


# ---------------------------------------------------------------------------
# État
# ---------------------------------------------------------------------------
def etat_vide():
    return {"bankroll_depart": CFG["bankroll"], "cash": CFG["bankroll"], "ouverts": [], "resolus": [],
            "observations": [], "obs_resolues": [], "apprentissage": {}, "fraction_kelly": CFG["fraction_kelly"],
            "pic": CFG["bankroll"], "dernier_ajust": 0, "rejets": 0, "journal": [], "passages": 0, "sites": {}}


def charger():
    if ETAT.exists():
        e = json.loads(ETAT.read_text(encoding="utf-8"))
        for k, v in etat_vide().items():
            e.setdefault(k, v)
        return e
    return etat_vide()


def sauver(e):
    ETAT.parent.mkdir(exist_ok=True)
    tmp = ETAT.with_suffix(".tmp")
    tmp.write_text(json.dumps(e, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(ETAT)                      # écriture atomique : jamais de fichier à moitié écrit


def log(e, texte):
    print(texte, flush=True)
    e["journal"].append({"quand": maintenant().isoformat(timespec="minutes"), "texte": texte})
    e["journal"] = e["journal"][-500:]


def valeur(e):
    return e["cash"] + sum(o["mise"] for o in e["ouverts"])


# ---------------------------------------------------------------------------
# Apprentissage commun
# ---------------------------------------------------------------------------
def tranche(prix):
    for b in (0.999, 0.995, 0.99, 0.985, 0.98, 0.975, 0.97):
        if prix >= b:
            return f">={b}"
    return "<0.97"


def cles(site, cat, prix):
    return (f"{site}|cat:{cat}", f"{site}|tranche:{tranche(prix)}")


def reapprendre(e):
    app, vus = {}, set()
    for r in e["obs_resolues"] + e["resolus"]:
        cle_unique = (r["site"], r["id"])
        if cle_unique in vus or r.get("annule"):
            continue
        vus.add(cle_unique)
        for k in cles(r["site"], r["cat"], r["prix"]):
            a = app.setdefault(k, {"n": 0, "gagnes": 0, "somme_prix": 0.0})
            a["n"] += 1
            a["gagnes"] += r["gagne"]
            a["somme_prix"] += r["prix"]
    for a in app.values():
        a["prix_moy"] = round(a.pop("somme_prix") / a["n"], 5)
        a["taux_reel"] = round(a["gagnes"] / a["n"], 5)
    e["apprentissage"] = app


def proba_estimee(e, site, cat, prix):
    """Cote du marché, corrigée par ce que le bot a observé sur le même site (catégorie et tranche).
    Peu d'exemples -> il fait confiance au marché ; beaucoup -> il se fie à son expérience."""
    k, corr, n_max = CFG["force_prior"], [], 0
    for cle in cles(site, cat, prix):
        a = e["apprentissage"].get(cle)
        if a and a["n"]:
            corr.append((a["gagnes"] / a["n"] - a["prix_moy"]) * a["n"] / (a["n"] + k))
            n_max = max(n_max, a["n"])
    p = prix + (sum(corr) / len(corr) if corr else 0.0)
    return max(0.0, min(0.9999, p)), n_max


def ajuster_risque(e):
    r = [x for x in e["resolus"] if not x.get("annule")]
    if len(r) - e["dernier_ajust"] < 20:
        return
    e["dernier_ajust"] = len(r)
    v = valeur(e)
    e["pic"] = max(e["pic"], v)
    rec = r[-50:]
    ecart = sum(x["gagne"] for x in rec) / len(rec) - sum(x["proba_bot"] for x in rec) / len(rec)
    f0 = e["fraction_kelly"]
    f1, raison = MI.ajuster_fraction(f0, v, e["pic"], len(rec), ecart)
    if raison:
        e["fraction_kelly"] = f1
        log(e, f"Prise de risque {f0:.3f} -> {f1:.3f} : {raison}")


# ---------------------------------------------------------------------------
# Étapes
# ---------------------------------------------------------------------------
def site_par_nom(nom):
    return next(s for s in TOUS if s.nom == nom)


def resoudre(e):
    t = maintenant()
    a_voir = [x for x in e["ouverts"] + e["observations"] if date_iso(x["fin"]) and date_iso(x["fin"]) <= t]
    deja, faits = set(), 0
    for x in a_voir:
        cle = (x["site"], x["id"])
        if cle in deja or faits >= CFG["resolutions_max"]:
            continue
        deja.add(cle)
        faits += 1
        try:
            r = site_par_nom(x["site"]).resultat(x)
        except Exception as err:
            log(e, f"[{x['site']}] résultat illisible pour {x['id']} : {err}")
            continue
        if r.get("contradiction"):
            log(e, f"[{x['site']}] résultat contradictoire, relu plus tard : {x['question'][:60]}")
        if r.get("fini"):
            appliquer_resultat(e, x["site"], x["id"], r)


def appliquer_resultat(e, site, mid, r):
    rembourse = r.get("rembourse", False)
    for o in [o for o in e["ouverts"] if (o["site"], o["id"]) == (site, mid)]:
        paiement = o["prix"] if rembourse else r["paiement"][o["idx"]]
        gain = o["mise"] * (paiement / o["prix"] - 1) - o["mise"] * o.get("frais", 0.0) * (not rembourse)
        annule = rembourse or 0.01 < paiement < 0.99
        e["cash"] += o["mise"] + gain
        e["ouverts"].remove(o)
        e["resolus"].append({**o, "gagne": int(paiement >= 0.99), "gain": round(gain, 2), "annule": annule,
                             "resolu_le": maintenant().isoformat(timespec="minutes")})
        etiquette = "Annulé" if annule else ("Gagné" if paiement >= 0.99 else "PERDU")
        log(e, f"[FICTIF][{site}] {etiquette} {gain:+.2f} € — {o['question'][:70]}")
    for o in [o for o in e["observations"] if (o["site"], o["id"]) == (site, mid)]:
        e["observations"].remove(o)
        if rembourse or 0.01 < r["paiement"][o["idx"]] < 0.99:
            log(e, f"[{site}] marché annulé ou partagé, exclu de l'apprentissage : {o['question'][:60]}")
            continue
        gagne = int(r["paiement"][o["idx"]] >= 0.99)
        e["obs_resolues"].append({**o, "gagne": gagne, "resolu_le": maintenant().isoformat(timespec="minutes")})
        if not gagne:
            log(e, f"[{site}] favori à {o['prix']:.1%} PERDANT : {o['question'][:70]}")
    e["obs_resolues"] = e["obs_resolues"][-20000:]


def preselection(e, site, marches):
    t = maintenant()
    deja = {(x["site"], x["id"]) for x in e["ouverts"] + e["observations"]}
    deja |= {(x["site"], x["id"]) for x in e["obs_resolues"][-20000:] + e["resolus"][-5000:]}
    out = []
    for m in marches:
        if (site.nom, m["id"]) in deja or not m.get("fin") or not (t < m["fin"] <= t + timedelta(days=CFG["jours_max"])):
            continue
        for idx, prix in enumerate(m["cotes"]):
            if CFG["seuil"] < prix < 1.0:
                out.append({**m, "idx": idx, "prix_liste": prix})
    out.sort(key=lambda m: m["fin"])           # les plus proches de la fin : résultats plus vite
    choisis, par_cat = [], {}
    for m in out:                              # variété : quelques-uns par catégorie
        if par_cat.get(m["cat"], 0) < CFG["max_par_categorie"]:
            par_cat[m["cat"]] = par_cat.get(m["cat"], 0) + 1
            choisis.append(m)
    return choisis[:CFG["verifs_max_par_site"]]


def verifier(site, m):
    """6 lectures (adresses différentes quand le site en propose), toutes doivent concorder."""
    lectures = []
    for url in site.adresses(m)[:CFG["lectures_min"]]:
        try:
            l = site.lire(url)
        except Exception:
            l = None
        if l and l["id"] == m["id"]:
            lectures.append(l)
        time.sleep(CFG["pause_lectures_s"])
    if len(lectures) < CFG["lectures_min"]:
        return None, f"seulement {len(lectures)}/{CFG['lectures_min']} lectures"
    i = m["idx"]
    cotes = [l["cotes"][i] for l in lectures]
    if max(cotes) - min(cotes) > CFG["ecart_lectures_max"]:
        return None, f"lectures discordantes {cotes}"
    if any(l["ferme"] for l in lectures):
        return None, "marché fermé"
    achats = [l["achat"][i] for l in lectures if l["achat"][i] is not None]
    if len(achats) >= CFG["lectures_min"] // 2 and max(achats) - min(achats) > CFG["ecart_lectures_max"]:
        return None, f"prix d'achat discordants {achats}"
    return {"cote": statistics.median(cotes),
            "achat": statistics.median(achats) if len(achats) >= CFG["lectures_min"] // 2 else None}, None


def traiter(e, site, m, v):
    obs = {"site": site.nom, "id": m["id"], "slug": m.get("slug", ""), "question": m["question"],
           "cote": m["issues"][m["idx"]], "idx": m["idx"], "prix": round(v["cote"], 4), "cat": m["cat"],
           "fin": m["fin"].isoformat(), "date": maintenant().isoformat(timespec="minutes")}
    e["observations"].append(obs)
    prix = v["achat"]
    if not site.argent_reel or prix is None or not 0 < prix < 1:
        return
    p, n_exp = proba_estimee(e, site.nom, m["cat"], prix)
    frais = site.frais(prix)
    esperance = p * (1 / prix - 1) - (1 - p) - frais
    if p <= CFG["seuil"] or esperance <= 0 or len(e["ouverts"]) >= CFG["max_paris_ouverts"]:
        return
    p_pru = MI.proba_prudente(p, n_exp, CFG["force_prior"])
    prix_net = min(0.9999, prix * (1 + frais))
    engage = sum(o["mise"] for o in e["ouverts"])
    montant = min(MI.mise(valeur(e), engage, MI.kelly_marche(p_pru, prix_net), e["fraction_kelly"]), e["cash"])
    if montant < 1:
        return
    pct = round(montant / valeur(e), 4)
    e["cash"] -= montant
    e["ouverts"].append({**obs, "prix": prix, "frais": round(frais, 5), "proba_bot": round(p, 4),
                         "p_prudent": round(p_pru, 4), "esperance": round(esperance, 5),
                         "mise": montant, "mise_pct": pct})
    log(e, f"[FICTIF][{site.nom}] Pari {montant:.2f} € ({pct:.1%}) sur « {obs['cote']} » — "
           f"{m['question'][:60]} (prix {prix}, proba bot {p:.1%})")


def passage():
    e = charger()
    e["passages"] += 1
    debut = maintenant()
    try:
        resoudre(e)
    except Exception:
        log(e, "Erreur pendant les résolutions : " + traceback.format_exc(limit=2))
    reapprendre(e)
    ajuster_risque(e)
    sauver(e)
    for site in TOUS:
        st = e["sites"].setdefault(site.nom, {"marches_vus": 0, "candidats": 0, "retenus": 0, "rejets": 0,
                                               "erreurs": 0, "dernier_ok": None})
        try:
            marches = site.candidats(CFG["jours_max"])
        except Exception as err:
            st["erreurs"] += 1
            log(e, f"[{site.nom}] liste des marchés illisible : {err}")
            continue
        st["marches_vus"] += len(marches)
        for m in preselection(e, site, marches):
            st["candidats"] += 1
            v, raison = verifier(site, m)
            if not v:
                st["rejets"] += 1
                e["rejets"] += 1
                log(e, f"[{site.nom}] rejet ({raison}) : {m['question'][:60]}")
                continue
            st["retenus"] += 1
            traiter(e, site, m, v)
        st["dernier_ok"] = maintenant().isoformat(timespec="minutes")
        sauver(e)                           # sauvegarde après chaque site
    e["dernier_passage"] = {"debut": debut.isoformat(timespec="minutes"),
                            "duree_s": round((maintenant() - debut).total_seconds())}
    sauver(e)
    print(bilan(e))


def bilan(e):
    r = [x for x in e["resolus"] if not x.get("annule")]
    o = e["obs_resolues"]
    lignes = [f"Bankroll fictive {valeur(e):.2f} € (départ {e['bankroll_depart']:.0f}) | paris ouverts "
              f"{len(e['ouverts'])} | résolus {len(r)}"
              + (f" dont gagnés {sum(x['gagne'] for x in r) / len(r):.1%}" if r else ""),
              f"Observations : {len(e['observations'])} en attente, {len(o)} résolues"
              + (f", favoris gagnants {sum(x['gagne'] for x in o) / len(o):.1%} pour une cote moyenne "
                 f"{sum(x['prix'] for x in o) / len(o):.1%}" if o else "")]
    for k, a in sorted(e["apprentissage"].items(), key=lambda kv: -kv[1]["n"])[:20]:
        lignes.append(f"  {k:<32} n={a['n']:<5} cote {a['prix_moy']:.3f} réel {a['taux_reel']:.3f}")
    return "\n".join(lignes)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bilan":
        print(bilan(charger()))
    else:
        passage()
