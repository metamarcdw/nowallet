import json
import sys
import os.path

sys.path.append(    # Make sure we can access nowallet in the parent directory
os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))
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
