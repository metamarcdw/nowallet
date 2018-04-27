# pylint: disable=W0621

import random
import pytest

from pycoin.serialize import b2h
from pycoin.tx.TxOut import TxOut
from pycoin.tx.Spendable import Spendable
from connectrum.svr_info import ServerInfo

from nowallet import bip49

@pytest.fixture
def server():
    return ServerInfo("onion",
                      hostname="fdkhv2bb7hqel2e7.onion",
                      ports=12345)

def test_serverinfo_class(server):
    assert isinstance(server, ServerInfo)
    assert server.get_port("t") == ("fdkhv2bb7hqel2e7.onion", 12345, False)

@pytest.fixture
def txout_small_coin_small_script():
    return TxOut(0, b"\x00")
@pytest.fixture
def txout_large_coin_small_script():
    return TxOut(10, b"\x00")
@pytest.fixture
def txout_small_coin_large_script():
    return TxOut(0, b"\xFF")
@pytest.fixture
def txout_large_coin_large_script():
    return TxOut(10, b"\xFF")

def test_txout_ordering(txout_small_coin_small_script,
                        txout_large_coin_small_script,
                        txout_small_coin_large_script,
                        txout_large_coin_large_script):
    a, b = txout_large_coin_large_script, TxOut(10, b"\xFF")
    assert (a.coin_value, b2h(a.script)) == (b.coin_value, b2h(b.script))

    txout_list = [txout_small_coin_small_script,
                  txout_large_coin_small_script,
                  txout_small_coin_large_script,
                  txout_large_coin_large_script]
    random.shuffle(txout_list)
    txout_list.sort(key=lambda txo: (txo.coin_value, b2h(txo.script)))

    assert txout_list[0] == txout_small_coin_small_script
    assert txout_list[1] == txout_small_coin_large_script
    assert txout_list[2] == txout_large_coin_small_script
    assert txout_list[3] == txout_large_coin_large_script

def test_txout(txout_small_coin_small_script):
    assert isinstance(txout_small_coin_small_script, TxOut)
    assert txout_small_coin_small_script.coin_value == 0
    assert txout_small_coin_small_script.script == b"\x00"

@pytest.fixture
def spendable_small_hex_small_vout(txout_small_coin_small_script):
    return Spendable.from_tx_out(txout_small_coin_small_script, b"\x00", 0)
@pytest.fixture
def spendable_large_hex_small_vout(txout_large_coin_small_script):
    return Spendable.from_tx_out(txout_large_coin_small_script, b"\xFF", 0)
@pytest.fixture
def spendable_small_hex_large_vout(txout_small_coin_large_script):
    return Spendable.from_tx_out(txout_small_coin_large_script, b"\x00", 10)
@pytest.fixture
def spendable_large_hex_large_vout(txout_large_coin_large_script):
    return Spendable.from_tx_out(txout_large_coin_large_script, b"\xFF", 10)

def test_spendable_ordering(txout_large_coin_large_script,
                            spendable_small_hex_small_vout,
                            spendable_large_hex_small_vout,
                            spendable_small_hex_large_vout,
                            spendable_large_hex_large_vout):
    spendable_list = [spendable_small_hex_small_vout,
                      spendable_large_hex_small_vout,
                      spendable_small_hex_large_vout,
                      spendable_large_hex_large_vout]
    random.shuffle(spendable_list)
    spendable_list.sort(key=lambda utxo: (utxo.as_dict()["tx_hash_hex"],
                                          utxo.as_dict()["tx_out_index"]))
    assert spendable_list[0] == spendable_small_hex_small_vout
    assert spendable_list[1] == spendable_small_hex_large_vout
    assert spendable_list[2] == spendable_large_hex_small_vout
    assert spendable_list[3] == spendable_large_hex_large_vout

def test_spendable(spendable_small_hex_small_vout):
    spendable = Spendable.from_tx_out(TxOut(0, b"\x00"), b"\x00", 0)
    assert isinstance(spendable, Spendable)
    assert spendable.tx_hash == b"\x00"
    assert spendable.tx_out_index == 0

@pytest.fixture
def segwitbip32node_from_chbs():
    secret = "CORRECT HORSE BATTERY STAPLE".encode("utf-8")
    return bip49.SegwitBIP32Node.from_master_secret(secret)

def test_segwitkey_script(segwitbip32node_from_chbs):
    script = segwitbip32node_from_chbs.p2wpkh_script()
    assert isinstance(script, bytes)
    assert script == (b"\x00\x14\xe5\xba\xc1f\xbd[\x9fb\x04" + \
                      b"\xb1\xb4?\xb3\xc6!\x99qd\xc7\xfe")

def test_segwitkey_script_hash(segwitbip32node_from_chbs):
    script_hash = segwitbip32node_from_chbs.p2wpkh_script_hash()
    assert isinstance(script_hash, bytes)
    assert script_hash == (b"H\x12\xe21\x90\x00:\xc2\xd2\xd7" + \
                           b"\xe3\x15\x99<\x96\x08\xaea\xac%")

def test_segwitkey_electrumx_spkhash(segwitbip32node_from_chbs):
    script_hash = segwitbip32node_from_chbs.electrumx_script_hash()
    assert isinstance(script_hash, str)
    assert script_hash == ("41d8dc340e750287f1ef920956e1f9ae" + \
                           "8a724efa9bb3772352118fe26372be97")

def test_segwitkey_address(segwitbip32node_from_chbs):
    address = segwitbip32node_from_chbs.p2sh_p2wpkh_address()
    assert isinstance(address, str)
    assert address == "38G7CQfoej3fZQbHHey7Z1XPUGpVpJv4em"

def test_bech32_segwitkey_address(segwitbip32node_from_chbs):
    address = segwitbip32node_from_chbs.bech32_p2wpkh_address()
    assert isinstance(address, str)
    assert address == "bc1pqq2wtwkpv674h8mzqjcmg0anccsejutycllqmc65qs"
