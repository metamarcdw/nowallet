import pytest
import random

from pycoin.tx.TxOut import TxOut

from nowallet import subclasses

@pytest.fixture
def server():
    return subclasses.MyServerInfo("onion",
                                   hostname="fdkhv2bb7hqel2e7.onion",
                                   ports=12345)

def test_myserverinfo_class(server):
    assert isinstance(server, subclasses.MyServerInfo)
    assert server.get_port("t") == ("fdkhv2bb7hqel2e7.onion", 12345, False)

@pytest.fixture
def lextxout_small_coin_small_script():
    return subclasses.LexTxOut(0, b"\x00")
@pytest.fixture
def lextxout_large_coin_small_script():
    return subclasses.LexTxOut(10, b"\x00")
@pytest.fixture
def lextxout_small_coin_large_script():
    return subclasses.LexTxOut(0, b"\xFF")
@pytest.fixture
def lextxout_large_coin_large_script():
    return subclasses.LexTxOut(10, b"\xFF")

def test_lextxout_ordering(lextxout_small_coin_small_script,
                           lextxout_large_coin_small_script,
                           lextxout_small_coin_large_script,
                           lextxout_large_coin_large_script):
    assert lextxout_large_coin_large_script == subclasses.LexTxOut(10, b"\xFF")
    lextxout_list = [lextxout_small_coin_small_script,
                     lextxout_large_coin_small_script,
                     lextxout_small_coin_large_script,
                     lextxout_large_coin_large_script]
    random.shuffle(lextxout_list)
    assert lextxout_list[0] == lextxout_small_coin_small_script
    assert lextxout_list[1] == lextxout_small_coin_large_script
    assert lextxout_list[2] == lextxout_large_coin_small_script
    assert lextxout_list[3] == lextxout_large_coin_large_script

def test_lextxout_demote(lextxout_small_coin_small_script):
    txout = subclasses.LexTxOut.demote(lextxout_small_coin_small_script)
    assert isinstance(txout, TxOut)
    assert txout.coin_value == 0
    assert txout.script == b"\x00"

