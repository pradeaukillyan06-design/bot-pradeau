"""Audit en direct (lecture seule) : pour chaque site, liste des marchés, relecture d'un échantillon,
cohérence liste/relecture, et lecture des résultats des observations échues. Ne modifie pas l'état."""
import json, sys, time, traceback
from datetime import datetime, timezone
sys.path.insert(0, ".")
from sites import TOUS
from sites.commun import date_iso

etat = json.load(open("etat/etat.json"))
maint = datetime.now(timezone.utc)
rapport = {}
for s in TOUS:
    r = {"argent_reel": s.argent_reel}
    t0 = time.time()
    try:
        c = s.candidats(21)
        r["candidats_s"] = round(time.time() - t0, 1)
        r["marches"] = len(c)
        hauts = [m for m in c if m.get("fin") and maint < m["fin"] and any(0.97 < p < 1 for p in m["cotes"])]
        r["au_dessus_97"] = len(hauts)
        r["ordre_issues_ok"] = all(len(m["cotes"]) == len(m["issues"]) == len(m["achat"]) for m in c)
        echantillon = []
        for m in (hauts or c)[:3]:
            e = {"id": m["id"], "question": m["question"][:80], "cotes": m["cotes"], "achat": m["achat"]}
            try:
                urls = s.adresses(m)
                e["nb_adresses"] = len(urls)
                l = s.lire(urls[0])
                e["lecture"] = None if l is None else {"id_ok": l["id"] == m["id"], "cotes": l["cotes"],
                                                       "achat": l["achat"], "ferme": l["ferme"]}
                if l:
                    e["ecart_max"] = round(max(abs(a - b) for a, b in zip(l["cotes"], m["cotes"])), 4)
            except Exception as x:
                e["erreur_lecture"] = repr(x)[:300]
            echantillon.append(e)
        r["echantillon"] = echantillon
    except Exception as x:
        r["erreur_liste"] = traceback.format_exc()[-600:]
    dus = [o for o in etat["observations"] + etat["ouverts"]
           if o["site"] == s.nom and (date_iso(o["fin"]) or maint) <= maint][:4]
    res = []
    for o in dus:
        try:
            res.append({"id": o["id"], "question": o["question"][:70], "idx": o["idx"], "prix": o["prix"],
                        "fin": o["fin"], "resultat": s.resultat(o)})
        except Exception as x:
            res.append({"id": o["id"], "erreur": repr(x)[:300]})
    r["resultats_echus"] = res
    r["duree_s"] = round(time.time() - t0, 1)
    rapport[s.nom] = r
    print(s.nom, r.get("marches"), r.get("au_dessus_97"), r["duree_s"], "s")
json.dump(rapport, open("audit_resultats.json", "w"), indent=1, ensure_ascii=False, default=str)
