#! /usr/bin/env python3

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

        loop.run_until_complete(self._do_connect())

    async def _do_connect(self):
        try:
            await self.connection
        except Exception as e:
            print("Unable to connect to server:", e)
            return -1

        print("\nConnected to server")

    async def listen_RPC(self, method, args):
        return await self.client.RPC(method, *args)

    async def listen_subscribe(self, method, args,
                        fut_cb=None, queue_cb=None):
        future, queue = self.client.subscribe(method, *args)
        result = await future
        if fut_cb:
            fut_cb(result)
        while True:
            result = await queue.get()
            if queue_cb:
                queue_cb(result)

class Chain:
    def __init__(self, netcode, chain_1209k, bip44):
        self.netcode = netcode
        self.chain_1209k = chain_1209k
        self.bip44 = bip44

BTC = Chain(netcode="BTC",
            chain_1209k="btc",
            bip44=0)
TBTC = Chain(netcode="XTN",
            chain_1209k="tbtc",
            bip44=1)

class Wallet:
    _COIN = decimal.Decimal("100000000")
    _GAP_LIMIT = 20

    def __init__(self, salt, passphrase, connection, chain, account=0):
        self.connection = connection

        (se, cc) = derive_key(salt, passphrase)
        self.mpk = BIP32Node(netcode=chain.netcode,
                                chain_code=cc, secret_exponent=se)
        path = "44H/{}H/{}H/".format(chain.bip44, account)
        self.root_spend_key = self.mpk.subkey_for_path("{}0".format(path))
        self.root_change_key = self.mpk.subkey_for_path("{}1".format(path))
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

    def get_next_unused_key(self, change=False):
        indicies = self.change_indicies if change else self.spend_indicies
        for i, is_used in enumerate(indicies):
            if not is_used:
                return self.get_key(i, change)

    def _get_history(self, loop, txids):
        method = "blockchain.transaction.get"
        futures = [self.connection.listen_RPC(method, [txid]) for txid in txids]
        results = loop.run_until_complete(asyncio.gather(*futures))
        txs = [Tx.from_hex(tx_hex) for tx_hex in results]
        return txs

    def _get_balance(self, loop, address):
        method = "blockchain.address.get_balance"
        future = self.connection.listen_RPC(method, [address])
        results = loop.run_until_complete(future)
        return decimal.Decimal(str(results["confirmed"])) / Wallet._COIN

    def _get_utxos(self, loop, address):
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

    def _interpret_history(self, loop, histories, change=False):
        indicies = self.change_indicies if change else self.spend_indicies
        is_empty = True
        for history in histories:
            if history:
                address = self.get_key(len(indicies), change).address()
                txids = [history[i]["tx_hash"] for i in range(len(history))]

                self.history[address] = self._get_history(loop, txids)
                self.balance += self._get_balance(loop, address)
                self.utxos.extend(self._get_utxos(loop, address))

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
            quit_flag = self._interpret_history(loop, result, change)
            current_index += Wallet._GAP_LIMIT

    def listen_to_addresses(self, loop, cb):
        method = "blockchain.address.subscribe"
        addrs = self.get_all_used_addresses()
        coros = [self.connection.listen_subscribe(method, [addr], queue_cb=cb)
                for addr in addrs]
        loop.run_until_complete(*coros)


def get_random_onion(chain):
    servers = scrape_onion_servers(chain_1209k=chain.chain_1209k)
    random.shuffle(servers)
    return servers.pop()

def print_result(result):
    print("DEEZ NUTS")
    print(result)

def main():
    loop = asyncio.get_event_loop()

    chain = TBTC
#    server, port = get_random_onion(chain)
#    connection = Connection(loop, server, port)
    connection = Connection(loop, "192.168.1.200", 50001)

    email = input("Enter email: ")
    passphrase = input("Enter passphrase: ")
    wallet = Wallet(email, passphrase, connection, chain)
    print("\nXPUB: " + wallet.get_xpub())

    wallet.discover_keys(loop)
    wallet.discover_keys(loop, change=True)
    print("History:\n", wallet.history)
    print("UTXOS:\n", wallet.utxos)
    print("Balance: {} TBTC".format(wallet.balance))
    wallet.listen_to_addresses(loop, print_result)

    loop.close()

if __name__ == '__main__':
    main()
