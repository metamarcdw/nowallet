import pytest
from nowallet import subclasses

@pytest.fixture
def server():
    return subclasses.MyServerInfo("onion",
                                   hostname="fdkhv2bb7hqel2e7.onion",
                                   ports=12345)

def test_myserverinfo_class(server):
    assert isinstance(server, subclasses.MyServerInfo)
    assert server.get_port("t") == ("fdkhv2bb7hqel2e7.onion", 12345, False)
