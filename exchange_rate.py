import logging
import asyncio
import json

from socks_http import urlopen

async def fetch_exchange_rates(chain_1209k="btc"):
    scrape_page = \
        "https://apiv2.bitcoinaverage.com/indices/global/ticker/short?crypto={}"
    url = scrape_page.format(chain_1209k.upper())
    logging.info("Scraping URL: %s", url)

    json_ = json.loads(await urlopen(url))
    return json_

def main():
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(fetch_exchange_rates())
    print(result)
    loop.close()

if __name__ == "__main__":
    main()
