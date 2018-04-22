import json
from nowallet.exchange_rate import CURRENCIES

def settings_json(coin="BTC"):
    return json.dumps(
        [
            {
                "type": "bool",
                "title": "RBF",
                "desc": "Use opt in replace by fee?",
                "section": "nowallet",
                "key": "rbf"
            }, {
                "type": "options",
                "title": "Coin Units",
                "desc": "Preferred Bitcoin denomination",
                "section": "nowallet",
                "key": "units",
                "options": [coin, "m{}".format(coin), "u{}".format(coin)]
            }, {
                "type": "options",
                "title": "Currency",
                "desc": "Fiat currency for exchange rates",
                "section": "nowallet",
                "key": "currency",
                "options": CURRENCIES
            }, {
                "type": "options",
                "title": "Block Explorer",
                "desc": "Preferred block explorer",
                "section": "nowallet",
                "key": "explorer",
                "options": ["blockcypher", "smartbit"]
            }, {
                "type": "options",
                "title": "Price Provider",
                "desc": "Preferred price provider",
                "section": "nowallet",
                "key": "price_api",
                "options": ["BitcoinAverage", "CryptoCompare"]
            }
        ]
    )
