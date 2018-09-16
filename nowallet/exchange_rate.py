import logging
import asyncio
import json
from typing import Dict, List, Any

from .socks_http import urlopen

CURRENCIES = [
    "USD", "EUR", "GBP", "AUD",
    "CAD", "JPY", "CNY"
]  # type: List[str]


async def fetch_from_api(base_url: str, chain_1209k: str, loop=None) -> Dict[str, Any]:
    fiats = ",".join(CURRENCIES)  # type: str
    url = base_url.format(chain_1209k.upper(), fiats)  # type: str
    logging.info("Fetching rates from URL: %s", url)

    return json.loads(await urlopen(url, loop=loop))


async def fetch_exchange_rates(chain_1209k: str = "btc", loop=None) -> Dict[str, Dict]:
    btcav_url = ("https://apiv2.bitcoinaverage.com/indices/" +
                 "global/ticker/short?crypto={}&fiat={}")  # type: str
    ccomp_url = ("https://min-api.cryptocompare.com/data/" +
                 "price?fsym={}&tsyms={}")  # type: str
    all_rates = {}  # type: Dict[str, Dict[str, Any]]

    btcav_json = await fetch_from_api(
        btcav_url, chain_1209k, loop=loop)  # type: Dict[str, Any]
    btcav_rates = {}  # type: Dict[str, float]
    for key, value in btcav_json.items():
        symbol = key.replace(chain_1209k.upper(), "")  # type: str
        if symbol in CURRENCIES:
            btcav_rates[symbol] = value["last"]
    all_rates["btcav"] = btcav_rates

    ccomp_json = await fetch_from_api(
        ccomp_url, chain_1209k, loop=loop)  # type: Dict[str, Any]
    all_rates["ccomp"] = ccomp_json
    return all_rates


def main():
    loop = asyncio.get_event_loop()  # type: asyncio.AbstractEventLoop
    result = loop.run_until_complete(
        fetch_exchange_rates())  # type: Dict[str, float]
    print(result)
    loop.close()


if __name__ == "__main__":
    main()
