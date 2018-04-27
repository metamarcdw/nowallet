from pkg_resources import get_distribution

__version__ = get_distribution('nowallet').version  # type: str

from . import keys
from . import socks_http
from . import scrape
from . import exchange_rate
from . import bip49
from .nowallet import *
