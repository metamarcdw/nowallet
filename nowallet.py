#! /usr/bin/env python3
#
# Subscribe to any message stream that the server supports.
#
import asyncio, random, decimal

from connectrum.client import StratumClient
from connectrum.svr_info import ServerInfo
from pycoin.key.BIP32Node import BIP32Node
from pycoin.tx.Tx import Tx

from keys import derive_key
from scrape import scrape_onion_servers

class Connection:
    def __init__(self, loop, server, port):
        print("Connecting...")

        # convert to our datastruct about servers.
        self.server_info = ServerInfo(server, hostname=server, ports=port)
        print(self.server_info.get_port("t"))
        self.client = StratumClient()
        self.connection = self.client.connect(
                            self.server_info,
                            proto_code="t",
                            use_tor=self.server_info.is_onion,
                            disable_cert_verify=True)

        loop.run_until_complete(self.do_connect())

    async def do_connect(self):
        try:
            await self.connection
        except Exception as e:
            print("Unable to connect to server:", e)
            return -1

        print("\nConnected to server")

    async def listen_RPC(self, method, args):
        return await self.client.RPC(method, *args)

    async def listen_subscribe(self, method, args, cb, queue_cb):
        future, queue = self.client.subscribe(method, *args)
        result = await future
        if cb:
            cb(result)
        while True:
            result = await queue.get()
            queue_cb(result)

class Wallet:
    _COIN = decimal.Decimal("100000000")
    _GAP_LIMIT = 20

    def __init__(self, salt, passphrase, connection):
        self.connection = connection

        (se, cc) = derive_key(salt, passphrase)
        self.mpk = BIP32Node(netcode="XTN", chain_code=cc, secret_exponent=se)
        self.root_spend_key = self.mpk.subkey_for_path("44H/1H/0H/0")
        self.root_change_key = self.mpk.subkey_for_path("44H/1H/0H/1")
        self.balance = decimal.Decimal("0")

        # Boolean lists, True = used / False = unused
        self.spend_indicies = list()
        self.change_indicies = list()

        # All wallet TX info. (Does not persist!)
        self.utxos = list()
        self.history = dict()

    def get_xpub(self):
        return self.mpk.hwif()

    def get_all_used_addresses(self):
        return list(self.history.keys())

    def get_key(self, index, change=False):
        if change:
            return self.root_change_key.subkey(index)
        else:
            return self.root_spend_key.subkey(index)

    def get_history(self, loop, txids):
        method = "blockchain.transaction.get"
        futures = [self.connection.listen_RPC(method, [txid]) for txid in txids]
        results = loop.run_until_complete(asyncio.gather(*futures))
        txs = [Tx.from_hex(tx_hex) for tx_hex in results]
        return txs

    def get_balance(self, loop, address):
        method = "blockchain.address.get_balance"
        future = self.connection.listen_RPC(method, [address])
        results = loop.run_until_complete(future)
        return decimal.Decimal(str(results["confirmed"])) / Wallet._COIN

    def get_utxos(self, loop, address):
        method = "blockchain.address.listunspent"
        future = self.connection.listen_RPC(method, [address])
        result = loop.run_until_complete(future)
        utxos = list()
        for unspent in result:
            method = "blockchain.transaction.get"
            txid = unspent["tx_hash"]
            vout = unspent["tx_pos"]
            future = self.connection.listen_RPC(method, [txid])
            result = loop.run_until_complete(future)
            spendables = Tx.from_hex(result).tx_outs_as_spendable()
            utxos.append(spendables[vout])
        return utxos

    def interpret_history(self, loop, histories, change=False):
        indicies = self.change_indicies if change else self.spend_indicies
        is_empty = True
        for history in histories:
            if history:
                address = self.get_key(len(indicies), change).address()
                txids = [history[i]["tx_hash"] for i in range(len(history))]

                self.history[address] = self.get_history(loop, txids)
                self.balance += self.get_balance(loop, address)
                self.utxos.extend(self.get_utxos(loop, address))

                indicies.append(True)
                is_empty = False
            else:
                indicies.append(False)
        return is_empty

    def discover_keys(self, loop, change=False):
        method = "blockchain.address.get_history"
        current_index = 0
        quit_flag = False
        while not quit_flag:
            futures = list()
            for i in range(current_index, current_index + Wallet._GAP_LIMIT):
                addr = self.get_key(i, change).address()
                futures.append(self.connection.listen_RPC(method, [addr]))

            result = loop.run_until_complete(asyncio.gather(*futures))
            quit_flag = self.interpret_history(loop, result, change)
            current_index += Wallet._GAP_LIMIT

    def subscribe_to_addresses(self):
        pass

    def future_callback(self):
        pass

    def query_callback(self):
        pass

def get_random_onion():
    servers = scrape_onion_servers()
    random.shuffle(servers)
    return servers.pop()

def main():
    loop = asyncio.get_event_loop()

#    server, port = get_random_onion()
#    connection = Connection(loop, server, port)
    connection = Connection(loop, "192.168.1.200", 50001)

    email = input("Enter email: ")
    passphrase = input("Enter passphrase: ")
    wallet = Wallet(email, passphrase, connection)
    print("\nXPUB: " + wallet.get_xpub())

    wallet.discover_keys(loop)
    print("History:\n", wallet.history)
    print("UTXOS:\n", wallet.utxos)
    print("Balance: {} TBTC".format(wallet.balance))

    loop.close()

if __name__ == '__main__':
    main()
