import asyncio
import aiohttp
import aiosocks
from aiosocks.connector import ProxyConnector, ProxyClientRequest


class SocksHTTPError(Exception):
    pass


async def urlopen(url: str, bauth_tuple=None, loop=None) -> str:
    bauth = None
    if bauth_tuple:
        login, password = bauth_tuple
        bauth = aiohttp.BasicAuth(login, password=password, encoding='latin1')
    auth5 = aiosocks.Socks5Auth(
        'proxyuser1', password='pwd')  # type: aiosocks.Socks5Auth
    conn = ProxyConnector(
        remote_resolve=True, loop=loop)  # type: ProxyConnector

    try:
        async with aiohttp.ClientSession(
            connector=conn,
            auth=bauth,
            request_class=ProxyClientRequest
        ) as session:
            async with session.get(
                url,
                proxy='socks5://127.0.0.1:9050',
                proxy_auth=auth5
            ) as resp:

                if resp.status == 200:
                    return await resp.text()
                else:
                    message = "HTTP response not OK: {}".format(resp.status)
                    raise SocksHTTPError(message)

    except aiohttp.ClientProxyConnectionError:
        # connection problem
        pass
    except aiosocks.SocksError:
        # communication problem
        pass
    return ""  # Should never happen


def main():
    loop = asyncio.get_event_loop()  # type: asyncio.AbstractEventLoop
    html = loop.run_until_complete(urlopen("https://github.com/"))  # type: str
    print(html)
    loop.close()


if __name__ == '__main__':
    main()
