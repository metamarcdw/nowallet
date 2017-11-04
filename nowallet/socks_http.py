import asyncio
import aiohttp
import aiosocks
from aiosocks.connector import ProxyConnector, ProxyClientRequest
from typing import Any

class SocksHTTPError(Exception):
    pass

async def urlopen(url: str) -> Any:
    auth5: aiosocks.Socks5Auth = aiosocks.Socks5Auth(
        'proxyuser1', password='pwd')
    conn: ProxyConnector = ProxyConnector(remote_resolve=False)

    try:
        with aiohttp.ClientSession(connector=conn,
                                   request_class=ProxyClientRequest) as session:
            async with session.get(url,     # Always connects through Tor.
                                   proxy='socks5://127.0.0.1:9050',
                                   proxy_auth=auth5) as resp:
                if resp.status == 200:
                    return await resp.text()
                else:
                    raise SocksHTTPError("HTTP response not OK")
    except aiohttp.ClientProxyConnectionError:
        # connection problem
        pass
    except aiosocks.SocksError:
        # communication problem
        pass

def main():
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    html: str = loop.run_until_complete(urlopen("https://github.com/"))
    print(html)
    loop.close()

if __name__ == '__main__':
    main()
