import json
from nowallet.exchange_rate import CURRENCIES

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
