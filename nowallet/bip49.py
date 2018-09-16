from typing import Type, TypeVar, Tuple, List, Dict, Any
from Crypto.Hash import SHA256

from pycoin.tx.pay_to.ScriptPayToAddressWit import ScriptPayToAddressWit
from pycoin.key.BIP32Node import BIP32Node
from pycoin.ui import address_for_pay_to_script, standard_tx_out_script
from pycoin.networks import bech32_hrp_for_netcode
from pycoin.contrib import segwit_addr
from pycoin.serialize import b2h_rev
from pycoin.encoding import hash160


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

    def electrumx_script_hash(self, bech32: bool = False) -> str:
        addr = self.bech32_p2wpkh_address() if bech32 \
            else self.p2sh_p2wpkh_address()  # type: str
        script = standard_tx_out_script(addr)  # type: bytes
        h = SHA256.new()
        h.update(script)
        return b2h_rev(h.digest())

    def p2wpkh_script(self) -> bytes:
        hash160_c = self.hash160(use_uncompressed=False)  # type: bytes
        return ScriptPayToAddressWit(b'\0', hash160_c).script()


def main():
    secret = "CORRECT HORSE BATTERY STAPLE"  # type: str
    mpk = SegwitBIP32Node.from_master_secret(
        secret.encode("utf-8"))  # type: SegwitBIP32Node
    print(mpk.p2sh_p2wpkh_address())
    print(mpk.bech32_p2wpkh_address())


if __name__ == "__main__":
    main()
