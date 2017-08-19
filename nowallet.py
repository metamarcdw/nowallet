#! /usr/bin/env python3

import sys, asyncio, random, decimal, collections, getpass

from connectrum.client import StratumClient
from pycoin.key.BIP32Node import BIP32Node
from pycoin.tx.Tx import Tx

from subclasses import MyServerInfo
from keys import derive_key
from scrape import scrape_onion_servers

class Connection:
    def __init__(self, loop, server, port):
        print("Connecting...")

        # convert to our datastruct about servers.
        self.server_info = MyServerInfo(server, hostname=server, ports=port)
        print(self.server_info.get_port("t"))
        self.client = StratumClient()
        self.connection = self.client.connect(
                            self.server_info,
                            proto_code="t",
                            use_tor=self.server_info.is_onion,
                            disable_cert_verify=True)

        loop.run_until_complete(self._do_connect())
        self.queue = None

    async def _do_connect(self):
        try:
            await self.connection
        except Exception as e:
            print("Unable to connect to server:", e)
            sys.exit(1)

        print("\nConnected to server")

    async def listen_RPC(self, method, args):
        return await self.client.RPC(method, *args)

    def listen_subscribe(self, method, args):
        future, self.queue = self.client.subscribe(method, *args)

    async def consume_queue(self, queue_func):
        while True:
            result = await self.queue.get()
            await queue_func(result)

Chain = collections.namedtuple("Chain", ["netcode", "chain_1209k", "bip44"])
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
        self.chain = chain

        (se, cc) = derive_key(salt, passphrase)
        self.mpk = BIP32Node(netcode=self.chain.netcode,
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
        self.result_cache = dict()

    def get_xpub(self):
        return self.mpk.hwif()

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

    def get_all_known_addresses(self, change=False):
        indicies = self.change_indicies if change else self.spend_indicies
        addrs = [self.get_key(i, change).address()
                for i in range(len(indicies))]
        return addrs

    def get_all_used_addresses(self):
        return list(self.history.keys())

    async def _get_history(self, txids):
        method = "blockchain.transaction.get"
        results = list()
        for txid in txids:
            results.append(await self.connection.listen_RPC(method, [txid]))
        txs = [Tx.from_hex(tx_hex) for tx_hex in results]
        return txs

    async def _get_balance(self, address):
        method = "blockchain.address.get_balance"
        result = await self.connection.listen_RPC(method, [address])
        return decimal.Decimal(str(result["confirmed"])) / Wallet._COIN

    async def _get_utxos(self, address):
        method = "blockchain.address.listunspent"
        result = await self.connection.listen_RPC(method, [address])
        utxos = list()
        for unspent in result:
            method = "blockchain.transaction.get"
            txid = unspent["tx_hash"]
            vout = unspent["tx_pos"]
            result = await self.connection.listen_RPC(method, [txid])
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

                self.history[address] = loop.run_until_complete(
                                            self._get_history(txids))
                self.balance += loop.run_until_complete(
                                            self._get_balance(address))
                self.utxos.extend(loop.run_until_complete(
                                            self._get_utxos(address)))

                indicies.append(True)
                is_empty = False
            else:
                indicies.append(False)
        return is_empty

    async def _interpret_new_history(self, address, history, change=False):
        indicies = self.change_indicies if change else self.spend_indicies
        is_empty = True
        if history:
            txid = history["tx_hash"]

            self.history[address] = await self._get_history([txid])
            self.balance += await self._get_balance(address)
            self.utxos.extend(await self._get_utxos(address))

            for i, used in enumerate(indicies):
                if self.get_key(i, change).address() == address:
                    indicies[i] = True
                    break
            else:
                indicies.append(True)
            is_empty = False
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
        self.new_history = True

    async def listen_to_addresses(self):
        method = "blockchain.address.subscribe"
        addrs = self.get_all_known_addresses()
        for addr in addrs:
            self.connection.listen_subscribe(method, [addr])

        await self.connection.consume_queue(self.dispatch_result)

    async def dispatch_result(self, result):
        addr = result[0]
        method = "blockchain.address.get_history"
        history = await self.connection.listen_RPC(method, [addr])
        empty_flag = await self._interpret_new_history(addr, history[0])
        if not empty_flag:
            self.new_history = True

    def mktx(self, out_addr, amount):
#        inputs = list()
#        outputs = list()
#        in_addrs = list()
#        total_out = decimal.Decimal("0")
        pass

    def spend(self, loop, address, amount):
        tx = self.mktx(address, amount)
        method = "blockchain.transaction.broadcast"
        txid = loop.run_until_complete(
                    self.connection.listen_RPC(method, [tx.as_hex()]))
        self.balance -= amount
        self.history[address] = loop.run_until_complete(
                                    self._get_history([txid]))

    def __str__(self):
        str_ = list()
        str_.append("\nXPUB: {}".format(self.get_xpub()))
        str_.append("\nHistory:\n{}".format(self.history))
        str_.append("\nUTXOS:\n{}".format(self.utxos))
        str_.append("\nBalance: {} {}".format(
                        self.balance, self.chain.chain_1209k.upper()))
        str_.append("\nYour current address: {}".format(
                    self.get_next_unused_key().address()))
        return "".join(str_)

def get_random_onion(chain):
    servers = scrape_onion_servers(chain_1209k=chain.chain_1209k)
    assert servers, "No electrum servers found!"
    random.shuffle(servers)
    return servers.pop()

async def user_io(wallet):
    while True:
        await asyncio.sleep(1)
        if wallet.new_history:
            print(wallet)
            wallet.new_history = False

def main():
    chain = TBTC
    loop = asyncio.get_event_loop()

    server, port = get_random_onion(chain)
    connection = Connection(loop, server, port)
#    connection = Connection(loop, "192.168.1.200", 50001)

    email = input("Enter email: ")
    passphrase = getpass.getpass("Enter passphrase: ")
    assert email and passphrase, "Email and/or passphrase were blank"
    wallet = Wallet(email, passphrase, connection, chain)

    wallet.discover_keys(loop)
    wallet.discover_keys(loop, change=True)

    if len(sys.argv) > 1 and sys.argv[1] == "spend":
        print("\nBalance: {} {}".format(
                wallet.balance, chain.chain_1209k.upper()))
        print("Enter a destination address:")
        spend_addr = input("> ")
        print("Enter an amount to spend:")
        spend_amount = decimal.Decimal(input("> "))
        wallet.spend(spend_amount, spend_addr)

    asyncio.ensure_future(wallet.listen_to_addresses()),
    asyncio.ensure_future(user_io(wallet))

    loop.run_forever()
    loop.close()

if __name__ == '__main__':
    main()
