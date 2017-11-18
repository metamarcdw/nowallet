import logging
import asyncio
import json
from typing import Dict, List

from socks_http import urlopen

CURRENCIES = ["USD", "EUR", "GBP", "AUD", "CAD", "JPY", "CNY"]  # type: List[str]
async def fetch_exchange_rates(chain_1209k: str="btc") -> Dict[str, float]:
    scrape_page = ("https://apiv2.bitcoinaverage.com/indices/" +
                   "global/ticker/short?crypto={}")  # type: str
    url = scrape_page.format(chain_1209k.upper())  # type: str
    logging.info("Fetching rates from URL: %s", url)

    json_ = json.loads(await urlopen(url))  # type: Dict[str, Dict]
    rates = dict()  # type: Dict[str, float]
    for key, value in json_.items():
        symbol = key.replace(chain_1209k.upper(), "")  # type: str
        if symbol in CURRENCIES:
            rates[symbol] = value["last"]
    return rates

def main():
    loop = asyncio.get_event_loop()  # type: asyncio.AbstractEventLoop
    result = loop.run_until_complete(
        fetch_exchange_rates())  # type: Dict[str, float]
    print(result)
    loop.close()

if __name__ == "__main__":
    main()
