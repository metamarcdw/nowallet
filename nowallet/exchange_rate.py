import logging
import asyncio
import json
from typing import Dict, List

from socks_http import urlopen

CURRENCIES: List[str] = ["USD", "EUR", "GBP", "AUD", "CAD", "JPY", "CNY"]
async def fetch_exchange_rates(chain_1209k: str="btc") -> Dict[str, float]:
    scrape_page: str = \
        "https://apiv2.bitcoinaverage.com/indices/global/ticker/short?crypto={}"
    url: str = scrape_page.format(chain_1209k.upper())
    logging.info("Fetching rates from URL: %s", url)

    json_: Dict[str, Dict] = json.loads(await urlopen(url))
    rates: Dict[str, float] = dict()
    for key, value in json_.items():
        symbol: str = key.replace(chain_1209k.upper(), "")
        if symbol in CURRENCIES:
            rates[symbol] = value["last"]
    return rates

def main():
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    result: Dict[str, float] = loop.run_until_complete(fetch_exchange_rates())
    print(result)
    loop.close()

if __name__ == "__main__":
    main()
