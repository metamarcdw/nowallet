import pytest
import random

from pycoin.tx.TxOut import TxOut
from pycoin.tx.Spendable import Spendable

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
    lextxout_list.sort()
    assert lextxout_list[0] == lextxout_small_coin_small_script
    assert lextxout_list[1] == lextxout_small_coin_large_script
    assert lextxout_list[2] == lextxout_large_coin_small_script
    assert lextxout_list[3] == lextxout_large_coin_large_script

def test_lextxout_demote(lextxout_small_coin_small_script):
    txout = subclasses.LexTxOut.demote(lextxout_small_coin_small_script)
    assert isinstance(txout, TxOut)
    assert txout.coin_value == 0
    assert txout.script == b"\x00"

@pytest.fixture
def lexspendable_small_hex_small_vout(lextxout_small_coin_small_script):
    spend = Spendable.from_tx_out(lextxout_small_coin_small_script, b"\x00", 0)
    return subclasses.LexSpendable.promote(spend)
@pytest.fixture
def lexspendable_large_hex_small_vout(lextxout_large_coin_small_script):
    spend = Spendable.from_tx_out(lextxout_large_coin_small_script, b"\xFF", 0)
    return subclasses.LexSpendable.promote(spend)
@pytest.fixture
def lexspendable_small_hex_large_vout(lextxout_small_coin_large_script):
    spend = Spendable.from_tx_out(lextxout_small_coin_large_script, b"\x00", 10)
    return subclasses.LexSpendable.promote(spend)
@pytest.fixture
def lexspendable_large_hex_large_vout(lextxout_large_coin_large_script):
    spend = Spendable.from_tx_out(lextxout_large_coin_large_script, b"\xFF", 10)
    return subclasses.LexSpendable.promote(spend)

def test_lexspendable_ordering(lextxout_large_coin_large_script,
                               lexspendable_small_hex_small_vout,
                               lexspendable_large_hex_small_vout,
                               lexspendable_small_hex_large_vout,
                               lexspendable_large_hex_large_vout):
    spend = Spendable.from_tx_out(lextxout_large_coin_large_script, b"\xFF", 10)
    assert lexspendable_large_hex_large_vout == \
        subclasses.LexSpendable.promote(spend)
    lexspendable_list = [lexspendable_small_hex_small_vout,
                         lexspendable_large_hex_small_vout,
                         lexspendable_small_hex_large_vout,
                         lexspendable_large_hex_large_vout]
    random.shuffle(lexspendable_list)
    lexspendable_list.sort()
    assert lexspendable_list[0] == lexspendable_small_hex_small_vout
    assert lexspendable_list[1] == lexspendable_small_hex_large_vout
    assert lexspendable_list[2] == lexspendable_large_hex_small_vout
    assert lexspendable_list[3] == lexspendable_large_hex_large_vout

def test_lexspendable_promote(lexspendable_small_hex_small_vout):
    spendable = Spendable.from_tx_out(TxOut(0, b"\x00"), b"\x00", 0)
    lexspendable = subclasses.LexSpendable.promote(spendable)
    assert isinstance(lexspendable, subclasses.LexSpendable)
    assert lexspendable.tx_hash == b"\x00"
    assert lexspendable.tx_out_index == 0

@pytest.fixture
def segwitbip32node_from_chbs():
    secret = "CORRECT HORSE BATTERY STAPLE".encode("utf-8")
    return subclasses.SegwitBIP32Node.from_master_secret(secret)

def test_segwitkey_script(segwitbip32node_from_chbs):
    script = segwitbip32node_from_chbs.p2sh_p2wpkh_script()
    assert isinstance(script, bytes)
    assert script == (b"\x00\x14\xe5\xba\xc1f\xbd[\x9fb\x04" + \
                      b"\xb1\xb4?\xb3\xc6!\x99qd\xc7\xfe")

def test_segwitkey_script_hash(segwitbip32node_from_chbs):
    script_hash = segwitbip32node_from_chbs.p2sh_p2wpkh_script_hash()
    assert isinstance(script_hash, bytes)
    assert script_hash == (b"H\x12\xe21\x90\x00:\xc2\xd2\xd7" + \
                           b"\xe3\x15\x99<\x96\x08\xaea\xac%")

def test_segwitkey_address(segwitbip32node_from_chbs):
    address = segwitbip32node_from_chbs.p2sh_p2wpkh_address()
    assert isinstance(address, str)
    assert address == "38G7CQfoej3fZQbHHey7Z1XPUGpVpJv4em"

