from .azuro import Azuro
from .espn import Espn
from .futuur import Futuur
from .gemini import Gemini
from .kalshi import Kalshi
from .limitless import Limitless
from .manifold import Manifold
from .options_crypto import Aevo, DeltaInde, Deribit, Gate, Okx
from .polymarket import Polymarket
from .smarkets import Smarkets

TOUS = [Polymarket(), Kalshi(), Manifold(), Limitless(), Gemini(), Smarkets(), Espn(), Futuur(), Azuro(), Deribit(), Okx(),
        DeltaInde(), Gate(), Aevo()]
