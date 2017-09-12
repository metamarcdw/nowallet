import logging
import asyncio

from socks_http import urlopen
from bs4 import BeautifulSoup

async def scrape_onion_servers(chain_1209k="tbtc",
            scrape_page="https://1209k.com/bitcoin-eye/ele.php?chain={}"):
    url = scrape_page.format(chain_1209k)
    logging.info("Scraping URL: %s", url)

    page = await urlopen(url)
    soup = BeautifulSoup(page, "html.parser")
    table_data = soup.find_all("td")

    servers = list()
    for i, td in enumerate(table_data):
        if ".onion" in td.text:
            host = td.text
            port = int(table_data[i+1].text)
            is_running = table_data[i+7].text == "open"
            if is_running:
                servers.append((host, port))
    return servers

def main():
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(scrape_onion_servers())
    print(result)
    loop.close()

if __name__ == "__main__":
    main()
