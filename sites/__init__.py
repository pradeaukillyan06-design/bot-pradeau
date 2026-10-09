from .azuro import Azuro
from .cboe import Cboe
from .espn import Espn
from .futuur import Futuur
from .gemini import Gemini
from .kalshi import Kalshi
from .limitless import Limitless
from .manifold import Manifold
from .options_crypto import Aevo, DeltaInde, DeltaMonde, Derive, Deribit, Gate, Okx, Thalex
from .polymarket import Polymarket
from .polymarket_us import PolymarketUs
from .smarkets import Smarkets
from .sxbet import SxBet

TOUS = [Polymarket(), Kalshi(), Manifold(), Limitless(), Gemini(), Smarkets(), Espn(), Futuur(), Azuro(), Deribit(), Okx(),
        DeltaInde(), Gate(), Aevo(), Thalex(), Derive(), Cboe(), SxBet(),
        DeltaMonde(), PolymarketUs()]
