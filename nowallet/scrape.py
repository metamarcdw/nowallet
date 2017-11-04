import logging
import asyncio
from typing import List, Tuple, Any

from socks_http import urlopen
from bs4 import BeautifulSoup

async def scrape_onion_servers(chain_1209k: str="tbtc") -> \
    List[Tuple[str, int]]:
    scrape_page: str = "https://1209k.com/bitcoin-eye/ele.php?chain={}"
    url: str = scrape_page.format(chain_1209k)
    logging.info("Scraping URL: %s", url)

    page: str = await urlopen(url)
    soup: BeautifulSoup = BeautifulSoup(page, "html.parser")
    table_data: List[Any] = soup.find_all("td")

    servers: List[Tuple[str, int]] = list()
    for i, data in enumerate(table_data):
        if ".onion" in data.text:
            host: str = data.text
            port: int = int(table_data[i+1].text)
            is_running: bool = table_data[i+7].text == "open"
            if is_running:
                servers.append((host, port))
    return servers

def main():
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    result: List[Tuple[str, int]] = loop.run_until_complete(scrape_onion_servers())
    print(result)
    loop.close()

if __name__ == "__main__":
    main()
