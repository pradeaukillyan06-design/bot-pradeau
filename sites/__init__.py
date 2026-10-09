from .espn import Espn
from .gemini import Gemini
from .kalshi import Kalshi
from .limitless import Limitless
from .manifold import Manifold
from .polymarket import Polymarket
from .smarkets import Smarkets

TOUS = [Polymarket(), Kalshi(), Manifold(), Limitless(), Gemini(), Smarkets(), Espn()]
