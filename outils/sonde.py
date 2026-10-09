"""Sonde : lit des adresses publiques candidates (lecture seule) et enregistre un échantillon de chaque réponse.
Sert à vérifier le format réel d'un nouveau site avant de l'ajouter au bot."""
import json, sys, urllib.request
UA = {"User-Agent": "BotPradeau/1.0 (paper trading, lecture seule)", "Accept": "application/json"}
def lire(url, corps=None):
    try:
        data = json.dumps(corps).encode() if corps else None
        h = dict(UA, **({"Content-Type": "application/json"} if corps else {}))
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]
    except Exception as e:
        return 0, repr(e)
out = {}
for l in json.load(open(sys.argv[1])):
    url, corps = (l, None) if isinstance(l, str) else (l["url"], l.get("corps"))
    n = 30000 if isinstance(l, str) else l.get("taille", 30000)
    s, t = lire(url, corps)
    out[url + (" POST" if corps else "")] = {"statut": s, "taille": len(t), "debut": t[:n]}
    print(s, len(t), url)
json.dump(out, open(sys.argv[2], "w"), indent=1, ensure_ascii=False)
