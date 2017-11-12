import pytest
from context import socks_http

@pytest.mark.asyncio
async def test_socks_http_urlopen():
    url = "http://github.com/"
    html = await socks_http.urlopen(url)
    assert isinstance(html, str)
    assert "html" in html

@pytest.mark.asyncio
async def test_exception_on_404():
    url = "http://github.com/ballsagna"
    with pytest.raises(socks_http.SocksHTTPError):
        await socks_http.urlopen(url)
