import logging
import asyncio
from typing import List, Tuple

from bs4 import BeautifulSoup
from .socks_http import urlopen


async def scrape_electrum_servers(chain_1209k: str = "tbtc",
                                  loop=None) -> List[Tuple[str, int, str]]:
    scrape_page = "https://1209k.com/bitcoin-eye/ele.php?chain={}"  # type: str
    url = scrape_page.format(chain_1209k)  # type: str
    logging.info("Scraping URL: %s", url)

    page = await urlopen(url, loop=loop)  # type: str
    soup = BeautifulSoup(page, "html.parser")  # type: BeautifulSoup
    table_data = soup.find_all("td")  # type: List
    testnet_blacklist = (
        "electrum.akinbo.org",
        "testnet.hsmiths.com",
        "testnet.qtornado.com"
    )

    servers = list()  # type: List[Tuple[str, int, str]]
    for i, data in enumerate(table_data):
        if i % 11 == 0 and "." in data.text:  # Every new URL
            host = data.text  # type: str
            port = int(table_data[i+1].text)  # type: int
            proto = None  # type: str

            if table_data[i+2].text == "ssl":
                proto = "s"
            elif table_data[i+2].text == "tcp":
                proto = "t"

            is_running = table_data[i+7].text == "open"  # type: bool
            if is_running:
                if chain_1209k == "tbtc" and host in testnet_blacklist:
                    continue
                servers.append((host, port, proto))
    return servers


def main():
    loop = asyncio.get_event_loop()  # type: asyncio.AbstractEventLoop
    result = loop.run_until_complete(
        scrape_electrum_servers())  # type: List[Tuple[str, int, str]]
    print(result)
    loop.close()


if __name__ == "__main__":
    main()
