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
import math
import statistics
import sys
import time
from datetime import timedelta
from pathlib import Path

import mise as MI
from sites import TOUS
from sites.commun import date_iso, maintenant

ICI = Path(__file__).parent
ETAT = ICI / "etat" / "etat.json"
CFG = {
    "version": "chef-1.8",
    "seuil": 0.97,
    "lectures_min": 6,
    "ecart_lectures_max": 0.005,
    "pause_lectures_s": 0.5,
    "jours_max": 21,
    "verifs_max_par_site": 40,      # nouvelles cotes vérifiées par site et par passage
    "max_par_categorie": 5,         # variété : pas plus de 5 nouvelles cotes d'une même catégorie par passage
    "resolutions_max": 60,
    "force_prior": 30,
    "fraction_kelly": 0.25,
    "max_paris_ouverts": 60,
    "bankroll": 1000.0,
    "historique_par_site": 250,     # marchés terminés étudiés par site et par passage (expérience immédiate)
    "historique_heures_avant": 24,  # cote regardée 24 h avant la fin
    "prior_pertes": 3.0,            # prudence : le bot suppose d'abord que le marché a raison (3 pertes « fictives »)
    "z_prudence": 1.28,             # marge de sécurité sur le taux de pertes (≈ 90 %)
    "max_par_evenement": 0.10,      # au plus 10 % du capital sur un même événement (ex. tous les « Prix Nobel »)
    "budget_agent_s": 420,          # temps max d'un agent par passage (le passage doit finir avant 14 min)
}


# ---------------------------------------------------------------------------
# État
# ---------------------------------------------------------------------------
def etat_vide():
    return {"bankroll_depart": CFG["bankroll"], "cash": CFG["bankroll"], "ouverts": [], "resolus": [],
            "observations": [], "obs_resolues": [], "apprentissage": {}, "fraction_kelly": CFG["fraction_kelly"],
            "pic": CFG["bankroll"], "dernier_ajust": 0, "rejets": 0, "journal": [], "passages": 0, "sites": {},
            "historique": [], "curseurs": {}, "non_achetables": {}}


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
    for r in e["obs_resolues"] + e["resolus"] + e["historique"]:
        # un même marché, ou plusieurs marchés d'un même événement (ex. les 30 candidats au Nobel),
        # ne comptent qu'une fois : sinon un seul événement gonfle l'expérience
        cle_unique = (r["site"], "g:" + r["groupe"]) if r.get("groupe") else (r["site"], r["id"])
        if cle_unique in vus or (r["site"], r["id"]) in vus or r.get("annule"):
            continue
        vus.add(cle_unique)
        vus.add((r["site"], r["id"]))
        prix = r.get("cote_juste", r["prix"])
        for k in cles(r["site"], r["cat"], prix):
            a = app.setdefault(k, {"n": 0, "gagnes": 0, "somme_prix": 0.0})
            a["n"] += 1
            a["gagnes"] += r["gagne"]
            a["somme_prix"] += prix
    for a in app.values():
        a["prix_moy"] = round(a.pop("somme_prix") / a["n"], 5)
        a["taux_reel"] = round(a["gagnes"] / a["n"], 5)
    e["apprentissage"] = app


def proba_estimee(e, site, cat, prix):
    """Probabilité de gagner = 1 - (risque annoncé par la cote) × (rapport pertes réelles / pertes annoncées).
    Le rapport part de 1 (le marché a raison) et ne s'en éloigne qu'avec beaucoup d'expérience. On travaille
    sur le RISQUE (1 - cote) et non sur la cote : une expérience faite à 97-99 % ne peut pas pousser une cote
    à 99,8 % jusqu'à 100 %. Renvoie (p, p_prudent, n)."""
    A, z = CFG["prior_pertes"], CFG["z_prudence"]
    rap, haut, n_max = [], [], 0
    for cle in cles(site, cat, prix):
        a = e["apprentissage"].get(cle)
        if a and a["n"]:
            attendues = a["n"] * (1 - a["prix_moy"])
            pertes = a["n"] - a["gagnes"]
            rap.append((pertes + A) / (attendues + A))
            haut.append((pertes + A + z * math.sqrt(pertes + A)) / (attendues + A))
            n_max = max(n_max, a["n"])
    if not rap:
        rap, haut = [1.0], [1 + z / math.sqrt(A)]
    r, r_haut = sum(rap) / len(rap), sum(haut) / len(haut)
    p = 1 - (1 - prix) * r
    p_pru = 1 - (1 - prix) * r_haut
    return max(0.0, min(0.9999, p)), max(0.0, min(0.9999, p_pru)), n_max


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


def appliquer_resultat(e, site, mid, r):
    rembourse = r.get("rembourse", False)
    concernes = [o for o in e["ouverts"] + e["observations"] if (o["site"], o["id"]) == (site, mid)]
    if not rembourse and any(o["idx"] >= len(r.get("paiement") or []) for o in concernes):
        log(e, f"[{site}] résultat incomplet (issues manquantes), relu plus tard : {mid}")
        return
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


def expirer(e, jours=30):
    """Résultat introuvable 30 jours après la fin : l'observation est abandonnée (sans rien apprendre) et
    un pari fictif est remboursé, pour ne pas bloquer l'argent ni la file des résultats."""
    limite = maintenant() - timedelta(days=jours)
    for o in [o for o in e["observations"] if (date_iso(o["fin"]) or limite) < limite]:
        e["observations"].remove(o)
        log(e, f"[{o['site']}] pas de résultat après {jours} jours, abandonné : {o['question'][:60]}")
    for o in [o for o in e["ouverts"] if (date_iso(o["fin"]) or limite) < limite]:
        e["ouverts"].remove(o)
        e["cash"] += o["mise"]
        e["resolus"].append({**o, "gagne": 0, "gain": 0.0, "annule": True,
                             "resolu_le": maintenant().isoformat(timespec="minutes")})
        log(e, f"[FICTIF][{o['site']}] pas de résultat après {jours} jours, mise rendue : {o['question'][:60]}")


def migrer(e):
    """Corrections ponctuelles de l'état, faites une seule fois."""
    faites = e.setdefault("migrations", [])
    if "historique_v2" not in faites:
        # l'ancien historique prenait la cote 24 h avant la FERMETURE du marché : pour un marché fermé tôt
        # (événement déjà arrivé) ou tard (résultat déjà connu), cette cote connaissait déjà la fin
        avant = len(e["historique"])
        e["historique"] = [h for h in e["historique"] if h["site"] not in ("polymarket", "manifold")]
        for s in ("polymarket", "manifold"):
            e["curseurs"][s] = 0
            if s in e["sites"]:
                e["sites"][s]["historique"] = 0
        # observations dont la cote relue était sous le seuil (avant la vérification ajoutée en chef-1.6)
        e["observations"] = [o for o in e["observations"] if o["prix"] > CFG["seuil"]]
        e["obs_resolues"] = [o for o in e["obs_resolues"] if o["prix"] > CFG["seuil"]]
        log(e, f"Historique refait avec une cote prise avant la fin PRÉVUE ({avant - len(e['historique'])} anciens "
               f"cas retirés) ; observations sous 97 % retirées")
        faites.append("historique_v2")
    if "paris_modele_v2" not in faites:
        # les paris ouverts avant chef-1.8 ont été dimensionnés avec un modèle trop sûr de lui (proba 99,99 %
        # sur des cotes à 99,8 %, historique biaisé) : annulés et mises rendues, leurs résultats restent appris
        for o in list(e["ouverts"]):
            e["ouverts"].remove(o)
            e["cash"] += o["mise"]
            e["resolus"].append({**o, "gagne": 0, "gain": 0.0, "annule": True, "raison": "ancien modèle",
                                 "resolu_le": maintenant().isoformat(timespec="minutes")})
            log(e, f"[FICTIF][{o['site']}] pari annulé (ancien modèle trop sûr de lui), mise rendue "
                   f"{o['mise']:.2f} € : {o['question'][:60]}")
        faites.append("paris_modele_v2")


def preselection(e, site, marches):
    t = maintenant()
    deja = {(x["site"], x["id"]) for x in e["ouverts"] + e["observations"]}
    deja |= {(x["site"], x["id"]) for x in e["obs_resolues"][-20000:] + e["resolus"][-5000:]}
    deja |= {tuple(k.split("|", 1)) for k in e.get("non_achetables", {})}
    out = []
    for m in marches:
        if (site.nom, m["id"]) in deja or not m.get("fin") or not (t < m["fin"] <= t + timedelta(days=CFG["jours_max"])):
            continue
        for idx, prix in enumerate(m["cotes"]):
            if CFG["seuil"] < prix < 1.0:
                out.append({**m, "idx": idx, "prix_liste": prix})
    # les plus proches de la fin d'abord (résultats plus vite) ; les cotes >= 99,9 % en dernier (souvent déjà jouées)
    out.sort(key=lambda m: (m["prix_liste"] >= 0.999, m["fin"]))
    choisis, par_cat = [], {}
    for m in out:                              # variété : quelques-uns par catégorie
        if par_cat.get(m["cat"], 0) < CFG["max_par_categorie"]:
            par_cat[m["cat"]] = par_cat.get(m["cat"], 0) + 1
            choisis.append(m)
    return choisis[:getattr(site, "verifs_max", CFG["verifs_max_par_site"])]


def verifier(site, m):
    """6 lectures (adresses différentes quand le site en propose), toutes doivent concorder."""
    lectures = []
    for url in site.adresses(m)[:CFG["lectures_min"]]:
        try:
            l = site.lire(url)
        except Exception:
            l = None
        if l and l["id"] == m["id"] and len(l["cotes"]) == len(m["cotes"]) and len(l["achat"]) == len(m["cotes"]):
            lectures.append(l)
        else:
            break                                 # il faut les 6 : inutile de continuer (gain de temps)
        time.sleep(getattr(site, "pause_lectures", CFG["pause_lectures_s"]) if CFG["pause_lectures_s"] else 0)
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
    if statistics.median(cotes) <= CFG["seuil"]:
        return None, f"cote relue {statistics.median(cotes):.3f}, sous le seuil"
    return {"cote": statistics.median(cotes),
            "achat": statistics.median(achats) if len(achats) >= CFG["lectures_min"] // 2 else None}, None


def traiter(e, site, m, v):
    obs = {"site": site.nom, "id": m["id"], "slug": m.get("slug", ""), "question": m["question"],
           "cote": m["issues"][m["idx"]], "idx": m["idx"], "prix": round(v["cote"], 4), "cat": m["cat"],
           "fin": m["fin"].isoformat(), "date": maintenant().isoformat(timespec="minutes")}
    if m.get("groupe"):
        obs["groupe"] = m["groupe"]
    prix = v["achat"]
    if prix is None or not 0 < prix < 1:
        # personne ne vend ce côté (souvent un match déjà joué) : on ne l'apprend pas, ça fausserait tout
        e.setdefault("non_achetables", {})[f"{site.nom}|{m['id']}"] = m["fin"].isoformat()
        log(e, f"[{site.nom}] ignoré (pas achetable, souvent déjà joué) : {m['question'][:60]}")
        return
    e["observations"].append(obs)
    if not site.argent_reel:
        return
    # l'apprentissage compare la cote juste (sans marge) au résultat : on l'interroge avec cette cote,
    # puis l'espérance se calcule avec le prix réellement payé
    p, p_pru, n_exp = proba_estimee(e, site.nom, m["cat"], v["cote"])
    frais = site.frais(prix)
    esperance = p * (1 / prix - 1) - (1 - p) - frais
    if p <= CFG["seuil"] or esperance <= 0 or len(e["ouverts"]) >= CFG["max_paris_ouverts"]:
        return
    prix_net = min(0.9999, prix * (1 + frais))
    engage = sum(o["mise"] for o in e["ouverts"])
    montant = min(MI.mise(valeur(e), engage, MI.kelly_marche(p_pru, prix_net), e["fraction_kelly"]),
                  e["cash"] / (1 + frais))
    groupe = m.get("groupe")
    if groupe:                                   # paris liés au même événement : plafond commun
        deja = sum(o["mise"] for o in e["ouverts"] if o["site"] == site.nom and o.get("groupe") == groupe)
        montant = min(montant, max(0.0, CFG["max_par_evenement"] * valeur(e) - deja))
    montant = round(montant, 2)
    if montant < 1:
        return
    pct = round(montant / valeur(e), 4)
    e["cash"] -= montant
    e["ouverts"].append({**obs, "prix": prix, "cote_juste": obs["prix"], "frais": round(frais, 5),
                         "proba_bot": round(p, 4), "version": CFG["version"],
                         "p_prudent": round(p_pru, 4), "esperance": round(esperance, 5),
                         "mise": montant, "mise_pct": pct})
    log(e, f"[FICTIF][{site.nom}] Pari {montant:.2f} € ({pct:.1%}) sur « {obs['cote']} » — "
           f"{m['question'][:60]} (prix {prix}, proba bot {p:.1%})")


def agent(site, e):
    """Travail d'UN site, fait en parallèle des autres (un agent par site). L'agent ne modifie
    jamais l'état : il rapporte ce qu'il a trouvé, et c'est le chef qui écrit (un seul écrivain)."""
    rap = {"site": site.nom, "resultats": [], "verifies": [], "rejets": [], "historique": [],
           "marches_vus": 0, "candidats": 0, "erreurs": [], "curseur": e["curseurs"].get(site.nom, 0)}
    t = maintenant()
    chrono = time.time()
    # 1) résultats des paris et observations terminés de ce site
    dus = {(x["id"]): x for x in e["ouverts"] + e["observations"]
           if x["site"] == site.nom and date_iso(x["fin"]) and date_iso(x["fin"]) <= t}
    # les moins récemment essayés d'abord : un résultat bloqué ne bloque pas les suivants
    for x in sorted(dus.values(), key=lambda x: x.get("dernier_essai", ""))[:CFG["resolutions_max"]]:
        try:
            rap["resultats"].append((x["id"], site.resultat(x) or {"fini": False}, x["question"]))
        except Exception as err:
            rap["erreurs"].append(f"résultat illisible pour {x['id']} : {err}")
    # 2) nouveaux marchés > 97 %, vérifiés 6 fois
    try:
        marches = site.candidats(CFG["jours_max"])
        rap["marches_vus"] = len(marches)
        for m in preselection(e, site, marches):
            if time.time() - chrono > CFG["budget_agent_s"]:
                rap["erreurs"].append("temps écoulé, vérifications reportées au passage suivant")
                break
            rap["candidats"] += 1
            v, raison = verifier(site, m)
            (rap["verifies"].append((m, v)) if v else rap["rejets"].append((m["question"], raison)))
    except Exception as err:
        rap["erreurs"].append(f"liste des marchés illisible : {err}")
    # 3) expérience immédiate : marchés déjà terminés (si le site le permet)
    if hasattr(site, "historique") and time.time() - chrono < CFG["budget_agent_s"]:
        try:
            h, rap["curseur"] = site.historique(rap["curseur"], CFG["historique_par_site"],
                                                CFG["historique_heures_avant"])
            rap["historique"] = h
        except Exception as err:
            rap["erreurs"].append(f"historique illisible : {err}")
    return rap


def passage():
    from concurrent.futures import ThreadPoolExecutor
    e = charger()
    e["passages"] += 1
    debut = maintenant()
    migrer(e)
    na = e["non_achetables"]
    for k in [k for k, fin in na.items() if (date_iso(fin) or debut) < debut]:
        del na[k]                                   # nettoyage : marchés terminés
    # les agents travaillent en même temps, un par site
    with ThreadPoolExecutor(max_workers=len(TOUS)) as pool:
        rapports = list(pool.map(lambda s: agent(s, e), TOUS))
    # le chef applique tout, dans l'ordre, seul à écrire.
    # Étape A : résultats et historique -> il apprend AVANT de décider de nouveaux paris
    deja_hist = {(h["site"], h["id"], h["idx"]) for h in e["historique"]}
    for rap in rapports:
        site = site_par_nom(rap["site"])
        st = e["sites"].setdefault(site.nom, {"marches_vus": 0, "candidats": 0, "retenus": 0, "rejets": 0,
                                               "erreurs": 0, "dernier_ok": None, "historique": 0})
        st.setdefault("historique", 0)
        for err in rap["erreurs"]:
            st["erreurs"] += 1
            log(e, f"[{site.nom}] {err}")
        for mid, r, question in rap["resultats"]:
            if r.get("contradiction"):
                log(e, f"[{site.nom}] résultat contradictoire, relu plus tard : {question[:60]}")
            if r.get("fini"):
                try:
                    appliquer_resultat(e, site.nom, mid, r)
                except Exception as err:               # un résultat bizarre ne fait pas tomber tout le passage
                    log(e, f"[{site.nom}] résultat inutilisable pour {mid} : {err}")
            for x in e["ouverts"] + e["observations"]:
                if (x["site"], x["id"]) == (site.nom, mid):
                    x["dernier_essai"] = maintenant().isoformat(timespec="minutes")
        nouveaux = [h for h in rap["historique"] if (h["site"], h["id"], h["idx"]) not in deja_hist]
        deja_hist |= {(h["site"], h["id"], h["idx"]) for h in nouveaux}
        e["historique"].extend(nouveaux)
        st["historique"] += len(nouveaux)
        e["curseurs"][site.nom] = rap["curseur"]
    e["historique"] = e["historique"][-20000:]
    expirer(e)
    reapprendre(e)
    ajuster_risque(e)
    # Étape B : nouvelles cotes vérifiées -> observations et paris fictifs
    for rap in rapports:
        site = site_par_nom(rap["site"])
        st = e["sites"][site.nom]
        for question, raison in rap["rejets"]:
            st["rejets"] += 1
            e["rejets"] += 1
            log(e, f"[{site.nom}] rejet ({raison}) : {question[:60]}")
        st["marches_vus"] += rap["marches_vus"]
        st["candidats"] += rap["candidats"]
        for m, v in rap["verifies"]:
            st["retenus"] += 1
            try:
                traiter(e, site, m, v)
            except Exception as err:
                log(e, f"[{site.nom}] cote inutilisable ({err}) : {m.get('question', '')[:60]}")
        if not rap["erreurs"]:
            st["dernier_ok"] = maintenant().isoformat(timespec="minutes")
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
    h = e.get("historique", [])
    if h:
        lignes.append(f"Historique étudié : {len(h)} favoris > 97 % la veille de la fin, gagnants "
                      f"{sum(x['gagne'] for x in h) / len(h):.1%} pour une cote moyenne {sum(x['prix'] for x in h) / len(h):.1%}")
    for k, a in sorted(e["apprentissage"].items(), key=lambda kv: -kv[1]["n"])[:20]:
        lignes.append(f"  {k:<32} n={a['n']:<5} cote {a['prix_moy']:.3f} réel {a['taux_reel']:.3f}")
    return "\n".join(lignes)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bilan":
        print(bilan(charger()))
    else:
        passage()
