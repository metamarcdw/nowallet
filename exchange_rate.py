import logging
import asyncio
import json

from socks_http import urlopen

CURRENCIES = ["USD", "EUR", "GBP", "AUD", "CAD", "JPY", "CNY"]
async def fetch_exchange_rates(chain_1209k="btc"):
    scrape_page = \
        "https://apiv2.bitcoinaverage.com/indices/global/ticker/short?crypto={}"
    url = scrape_page.format(chain_1209k.upper())
    logging.info("Fetching rates from URL: %s", url)

    json_ = json.loads(await urlopen(url))
    rates = dict()
    for key, value in json_.items():
        symbol = key.replace(chain_1209k.upper(), "")
        if symbol in CURRENCIES:
            rates[symbol] = value["last"]
    return rates

def main():
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(fetch_exchange_rates())
    print(result)
    loop.close()

if __name__ == "__main__":
    main()
