from functools import total_ordering
from typing import Type, TypeVar, Tuple, List, Dict, Any

from connectrum.svr_info import ServerInfo
from connectrum.constants import DEFAULT_PORTS

from pycoin.tx.Tx import Tx
from pycoin.tx.TxOut import TxOut
from pycoin.tx.Spendable import Spendable
from pycoin.tx.pay_to.ScriptPayToAddressWit import ScriptPayToAddressWit
from pycoin.key.BIP32Node import BIP32Node
from pycoin.ui import address_for_pay_to_script
from pycoin.encoding import hash160
from pycoin.networks import bech32_hrp_for_netcode
from pycoin.contrib import segwit_addr

from pycoin.serialize import b2h

class MyServerInfo(ServerInfo):
    def get_port(self, for_protocol: str) -> Tuple[str, int, bool]:
        '''
            Return (hostname, port number, ssl) pair for the protocol.
            Assuming only one port per host.
        '''
        assert len(for_protocol) == 1, "expect single letter code"
        rv = [i for i in self['ports'] if i[0] == for_protocol]
        port = None
        if len(rv) < 2:
            try:
                port = int(rv[0][1:])
            except Exception:
                pass
        port = port or DEFAULT_PORTS[for_protocol]
        use_ssl = for_protocol in ('s', 'g')
        return self['hostname'], port, use_ssl

@total_ordering
class LexTxOut(TxOut):
    T = TypeVar("T", bound="LexTxOut")
    @staticmethod
    def demote(lexout: Type[T]) -> TxOut:
        return TxOut(lexout.coin_value, lexout.script)

    def __eq__(self, other) -> bool:
        return (self.coin_value, b2h(self.script)) == \
            (other.coin_value, b2h(other.script))

    def __lt__(self: T, other: Type[T]) -> bool:
        return (self.coin_value, b2h(self.script)) < \
            (other.coin_value, b2h(other.script))

@total_ordering
class LexSpendable(Spendable):
    T = TypeVar("T", bound="LexSpendable")
    @classmethod
    def promote(cls: Type[T], spendable: Spendable) -> T:
        return cls.from_dict(spendable.as_dict())

    def __eq__(self, other) -> bool:
        self_dict = self.as_dict()  # type: Dict[str, Any]
        other_dict = other.as_dict()  # type: Dict[str, Any]
        return (self_dict["tx_hash_hex"], self_dict["tx_out_index"]) == \
            (other_dict["tx_hash_hex"], other_dict["tx_out_index"])

    def __lt__(self: T, other: Type[T]) -> bool:
        self_dict = self.as_dict()  # type: Dict[str, Any]
        other_dict = other.as_dict()  # type: Dict[str, Any]
        return (self_dict["tx_hash_hex"], self_dict["tx_out_index"]) < \
            (other_dict["tx_hash_hex"], other_dict["tx_out_index"])

class SegwitBIP32Node(BIP32Node):
    def bech32_p2wpkh_address(self) -> str:
        hrp = bech32_hrp_for_netcode(self.netcode())
        witprog_version = 1
        p2aw_script = self.p2wpkh_script()
        return segwit_addr.encode(hrp, witprog_version, p2aw_script)

    def p2sh_p2wpkh_address(self) -> str:
        p2aw_script = self.p2wpkh_script()  # type: bytes
        return address_for_pay_to_script(p2aw_script, netcode=self.netcode())

    def p2wpkh_script_hash(self) -> bytes:
        p2aw_script = self.p2wpkh_script()  # type: bytes
        return hash160(p2aw_script)

    def p2wpkh_script(self) -> bytes:
        hash160_c = self.hash160(use_uncompressed=False)  # type: bytes
        return ScriptPayToAddressWit(b'\0', hash160_c).script()

def main():
    svr = MyServerInfo("onion",
                       hostname="fdkhv2bb7hqel2e7.onion",
                       ports=12345)  # type: MyServerInfo
    print(svr.get_port("t"))

    hex_ = [
        "01000000014f2eae2eadabe4e807fad4220a931991590ae31f223ba70bf1",
        "8dd16983005441010000006b483045022100ab33f14e1c3387b68942e1ab",
        "bd4ec0e2d94866529409464e262531c165cc75f0022034482cd3031bb779",
        "852baaedae91c43b61c84ca3eecad6220e91c24e1227e30a0121022798d6",
        "f62e0c4d01c16ef51599e9d9d60048f3930c03f0da8681b1884ce2b411ff",
        "ffffff02873e0800000000001976a914c8f91ed83b0e345751e62e392be8",
        "be0494d0617b88ac538e4c39000000001976a9149b004c3bdcfaa929c336",
        "8d221deb26303d7e72c788ac00000000"]  # type: List[str]
    tx_hex = "".join(hex_)  # type: str
    tx = Tx.from_hex(tx_hex)  # type: Tx

    utxos = [LexSpendable.promote(utxo)
             for utxo in tx.tx_outs_as_spendable()]  # type: List[LexSpendable]
    utxos.sort()
    print(utxos)

    txouts = [LexTxOut(txout.coin_value, txout.script)
              for txout in tx.txs_out]  # type: List[LexTxOut]
    txouts.sort()
    print([str(txout) for txout in txouts])

    secret = "CORRECT HORSE BATTERY STAPLE"  # type: str
    mpk = SegwitBIP32Node.from_master_secret(
        secret.encode("utf-8"))  # type: SegwitBIP32Node
    print(mpk.p2sh_p2wpkh_address())
    print(mpk.bech32_p2wpkh_address())

if __name__ == "__main__":
    main()
