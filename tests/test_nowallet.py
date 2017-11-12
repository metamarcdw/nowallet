import pytest
import nowallet.nowallet as nowallet

@pytest.fixture
def dummy_connection(event_loop):
    server, port = 'hsmithsxurybd7uh.onion', 53011
    return nowallet.Connection(event_loop, server, port)

@pytest.fixture
def dummy_wallet(event_loop, dummy_connection):
    salt = "CORRECT HORSE"
    password = "BATTERY STAPLE"
    return nowallet.Wallet(salt, password,
                           dummy_connection, event_loop,
                           nowallet.TBTC)

def test_wallet_attributes(dummy_wallet):
    assert not dummy_wallet.history
