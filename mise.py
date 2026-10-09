"""
Mise autonome du Bot Pradeau (argent fictif).

Le bot choisit seul combien miser sur chaque pari :

1. Il estime une proba PRUDENTE : la proba la plus basse qui reste plausible vu son
   expérience. Moins il a d'expérience sur ce type de pari, plus il est méfiant.
2. Il calcule la mise idéale avec le critère de Kelly : la fraction du capital qui fait
   croître l'argent le plus vite à long terme. Kelly mise beaucoup quand le pari est
   sûr ET bien payé, peu quand il est risqué ou mal payé, et rien quand il perd en moyenne.
3. Il n'en joue qu'une fraction (au départ 1/4 de Kelly), car une proba un peu fausse
   avec Kelly complet peut ruiner un compte.
4. Il ajuste lui-même cette fraction : il la réduit après une grosse baisse du capital,
   et l'augmente doucement quand ses résultats confirment ses estimations.

Garde-fous fixes (le bot ne peut pas les changer) : jamais plus de 25 % du capital
sur un seul pari, jamais plus de 80 % du capital engagé en même temps.
"""
import math

GARDE_FOUS = {"mise_max_par_pari": 0.25, "exposition_max": 0.80,
              "fraction_min": 0.05, "fraction_max": 0.50}


def kelly_binaire(p, gain, perte):
    """Pari qui rapporte +gain (fraction de la mise) avec proba p, et coûte perte (>0) sinon.
    Renvoie la fraction de Kelly du capital (0 si le pari perd en moyenne)."""
    if gain <= 0 or perte <= 0:
        return 0.0
    f = p / perte - (1 - p) / gain
    return max(0.0, f)


def kelly_marche(p, prix):
    """Marché de prédiction : on achète à `prix`, on touche 1 si gagné, 0 sinon."""
    if not 0 < prix < 1:
        return 0.0
    return max(0.0, (p - prix) / (1 - prix))


def proba_prudente(p, n_experience, force=30, z=1.28):
    """Retire une marge d'incertitude qui diminue avec l'expérience (z=1,28 ~ 90 %)."""
    sd = math.sqrt(max(p * (1 - p), 1e-6) / (n_experience + force))
    return max(0.0, p - z * sd)


def mise(capital, engage, f_kelly, fraction):
    """Montant à miser, garde-fous compris."""
    f = min(f_kelly * fraction, GARDE_FOUS["mise_max_par_pari"])
    place = max(0.0, GARDE_FOUS["exposition_max"] * capital - engage)
    return round(max(0.0, min(f * capital, place)), 2)


def ajuster_fraction(fraction, capital, pic, nb_resultats, ecart_calibration):
    """
    Le bot règle seul sa prise de risque :
    - capital à plus de 15 % sous son plus haut -> il réduit (x0,8)
    - ses probas surestiment la réalité de plus de 2 points -> il réduit (x0,8)
    - nouveau plus haut, au moins 30 résultats, probas justes -> il ose un peu plus (x1,05)
    Renvoie (nouvelle_fraction, raison ou None).
    """
    nouv, raison = fraction, None
    if pic > 0 and capital < 0.85 * pic:
        nouv, raison = fraction * 0.8, "capital à plus de 15 % sous son plus haut"
    elif ecart_calibration is not None and ecart_calibration < -0.02:
        nouv, raison = fraction * 0.8, "ses probas étaient trop optimistes"
    elif capital >= pic and nb_resultats >= 30 and (ecart_calibration is None or ecart_calibration > -0.01):
        nouv, raison = fraction * 1.05, "nouveau plus haut et probas fiables"
    nouv = min(GARDE_FOUS["fraction_max"], max(GARDE_FOUS["fraction_min"], nouv))
    return round(nouv, 4), (raison if abs(nouv - fraction) > 1e-6 else None)
