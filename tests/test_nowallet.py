import pytest
import decimal
import nowallet

@pytest.fixture
def dummy_connection(event_loop):
    server, port = "hsmithsxurybd7uh.onion", 53011
    return nowallet.Connection(event_loop, server, port, "t")

@pytest.fixture
def dummy_wallet(event_loop, dummy_connection):
    salt = "CORRECT HORSE"
    password = "BATTERY STAPLE"
    return nowallet.Wallet(salt, password,
                           dummy_connection, event_loop,
                           nowallet.TBTC)

def test_wallet_attributes(dummy_wallet):
    assert not dummy_wallet.history

def test_get_payable_from_BIP21URI():
    URI = "BiTCoiN:address?amount=0.123"
    with pytest.raises(ValueError):
        payable = nowallet.get_payable_from_BIP21URI(URI, "Litecoin")
    payable = nowallet.get_payable_from_BIP21URI(URI, "bitCOIN")
    assert isinstance(payable, tuple)
    assert len(payable) == 2
    addr, amount = payable
    assert isinstance(addr, str)
    assert isinstance(amount, decimal.Decimal) or amount is None
