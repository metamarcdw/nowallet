from functools import total_ordering

from connectrum.svr_info import ServerInfo
from connectrum.constants import DEFAULT_PORTS

from pycoin.tx.Tx import Tx
from pycoin.tx.TxOut import TxOut
from pycoin.tx.Spendable import Spendable
from pycoin.serialize import b2h

class MyServerInfo(ServerInfo):
    def get_port(self, for_protocol):
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
            except:
                pass
        port = port or DEFAULT_PORTS[for_protocol]
        use_ssl = for_protocol in ('s', 'g')
        return self['hostname'], port, use_ssl

@total_ordering
class LexTxOut(TxOut):
    def __init__(self, coin_value, script):
        super().__init__(coin_value, script)

    @staticmethod
    def demote(lexout):
        return TxOut(lexout.coin_value, lexout.script)
    
    def __eq__(self, other):
        return self.coin_value == other.coin_value and \
                self.script == other.script
    
    def __lt__(self, other):
        if self.coin_value == other.coin_value:
            return b2h(self.script) < b2h(self.script)
        else:
            return self.coin_value < other.coin_value

@total_ordering
class LexSpendable(Spendable):
    @classmethod
    def promote(cls, spendable):
        return cls.from_dict(spendable.as_dict())
    
    def __eq__(self, other):
        self_dict = self.as_dict()
        other_dict = other.as_dict()
        return self_dict["tx_hash_hex"] == other_dict["tx_hash_hex"] and \
                self_dict["tx_out_index"] == other_dict["tx_out_index"]
    
    def __lt__(self, other):
        self_dict = self.as_dict()
        other_dict = other.as_dict()
        if self_dict["tx_hash_hex"] == other_dict["tx_hash_hex"]:
            return self_dict["tx_out_index"] < other_dict["tx_out_index"]
        else:
            return self_dict["tx_hash_hex"] < other_dict["tx_hash_hex"]

def main():
    svr = MyServerInfo("onion",
                    hostname="fdkhv2bb7hqel2e7.onion",
                    ports=12345)
    print(svr.get_port("t"))
    
    hex =    ["01000000014f2eae2eadabe4e807fad4220a931991590ae31f223ba70bf1",
            "8dd16983005441010000006b483045022100ab33f14e1c3387b68942e1ab",
            "bd4ec0e2d94866529409464e262531c165cc75f0022034482cd3031bb779",
            "852baaedae91c43b61c84ca3eecad6220e91c24e1227e30a0121022798d6",
            "f62e0c4d01c16ef51599e9d9d60048f3930c03f0da8681b1884ce2b411ff",
            "ffffff02873e0800000000001976a914c8f91ed83b0e345751e62e392be8",
            "be0494d0617b88ac538e4c39000000001976a9149b004c3bdcfaa929c336",
            "8d221deb26303d7e72c788ac00000000"]
    tx_hex = "".join(hex)
    tx = Tx.from_hex(tx_hex)
    
    utxos = [LexSpendable.promote(utxo) for utxo in tx.tx_outs_as_spendable()]
    utxos.sort()
    print(utxos)
    
    txouts = [LexTxOut(txout.coin_value, txout.script) for txout in tx.txs_out]
    txouts.sort()
    print([str(txout) for txout in txouts])

if __name__ == "__main__":
    main()
