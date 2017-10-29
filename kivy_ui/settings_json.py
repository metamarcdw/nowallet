import json
import sys
import os.path

sys.path.append(os.path.abspath( # Make sure we can import nowallet modules
    os.path.join(os.path.dirname(__file__), os.path.pardir, "nowallet")))
from exchange_rate import CURRENCIES

settings_json = json.dumps([
    {"type": "bool",
     "title": "RBF",
     "desc": "Use opt in replace by fee?",
     "section": "nowallet",
     "key": "rbf"},
    {"type": "options",
     "title": "Currency",
     "desc": "Fiat currency for exchange rates",
     "section": "nowallet",
     "key": "currency",
     "options": CURRENCIES}
])
