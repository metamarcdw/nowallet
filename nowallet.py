#! /usr/bin/env python3

import logging, sys
format_ = "%(asctime)s %(levelname)s: %(message)s"

stdout_hdlr = logging.StreamHandler(sys.stdout)
stdout_hdlr.setFormatter(logging.Formatter(format_))
stdout_hdlr.setLevel(logging.INFO)

file_hdlr = logging.FileHandler(filename="nowallet.log", mode="w")
file_hdlr.setFormatter(logging.Formatter(format_))
file_hdlr.setLevel(logging.DEBUG)

logging.basicConfig(level=logging.DEBUG,
                    handlers=[stdout_hdlr, file_hdlr])

import asyncio, io, random, decimal, collections, getpass, pprint, time

from connectrum.client import StratumClient
from pycoin.ui import standard_tx_out_script
from pycoin.tx.tx_utils import distribute_from_split_pool, sign_tx
from pycoin.tx.Tx import Tx

from subclasses import MyServerInfo, LexSpendable, LexTxOut, SegwitKey, SegwitBIP32Node
from keys import derive_key
from scrape import scrape_onion_servers

class Connection:
    def __init__(self, loop, server, port):
        """
        Connection object constructor. Connects to an Electrum server.

        :param loop: an asyncio event loop
        :param server: a string containing a hostname
        :param port: port number that the server listens on
        :returns: A new Connection object
        """
        logging.info("Connecting...")

        self.server_info = MyServerInfo(server, hostname=server, ports=port)
        logging.info(self.server_info.get_port("t"))
        self.client = StratumClient()
        self.connection = self.client.connect(
            self.server_info,
            proto_code="t",
            use_tor=self.server_info.is_onion,
            disable_cert_verify=True)

        loop.run_until_complete(self._do_connect())
        self.queue = None

    async def _do_connect(self):
        """
        Coroutine. Establishes a persistent connection to an Electrum server.
        Awaits the connection because AFAIK an init method can't be async.
        """
        try:
            await self.connection
        except Exception:
            logging.error("Unable to connect to server:", exc_info=True)
            sys.exit(1)

        logging.info("Connected to server")

    async def listen_rpc(self, method, args):
        """
        Coroutine. Sends a normal RPC message to the server and awaits response.

        :param method: The Electrum API method to use
        :param args: Params associated with current method
        :returns: Future. Response from server for this method(args)
        """
        return await self.client.RPC(method, *args)

    def listen_subscribe(self, method, args):
        """
        Sends a "subscribe" message to the server and adds to the queue.
        Throws away the immediate future containing the "history" hash.

        :param method: The Electrum API method to use
        :param args: Params associated with current method
        """
        future, self.queue = self.client.subscribe(method, *args)

    async def consume_queue(self, queue_func):
        """
        Coroutine. Infinite loop that consumes the current subscription queue.

        :param queue_func: A function to call when new responses arrive
        """
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
    """
    Provides all functionality required for a fully functional and secure
    HD brainwallet based on the Warpwallet technique.
    """
    COIN = 100000000
    _GAP_LIMIT = 20
    _History = collections.namedtuple("_History", ["tx_obj", "is_spend", "value"])

    def __init__(self, salt, passphrase, connection, loop, chain, account=0):
        """
        Wallet object constructor. Use discover_keys() and listen_to_addresses()
        coroutine method to construct wallet data, and listen for new data from
        the server.

        :param salt: a string to use as a salt for key derivation
        :param passphrase: a string containing a secure passphrase
        :param connection: a Connection object
        :param loop: an asyncio event loop
        :param chain: a namedtuple containing chain-specific info
        :param account: account number, defaults to 0
        :returns: A new, empty Wallet object
        """
        self.connection = connection
        self.loop = loop
        self.chain = chain

        start_derivation = time.time()
        logging.info("Deriving keys...")

        secret_exp, chain_code = derive_key(salt, passphrase)
        self.mpk = SegwitBIP32Node(netcode=self.chain.netcode,
                                   chain_code=chain_code,
                                   secret_exponent=secret_exp)

        path = "49H/{}H/{}H".format(chain.bip44, account)
        self.account_master = self.mpk.subkey_for_path(path)
        self.root_spend_key = self.account_master.subkey(0)
        self.root_change_key = self.account_master.subkey(1)

        end_derivation = time.time()
        seconds = end_derivation - start_derivation
        logging.info("Keys derived in {0:.3f} seconds".format(seconds))

        # Boolean lists, True = used / False = unused
        self.spend_indicies = list()
        self.change_indicies = list()

        # All wallet TX info. (Does not persist!)
        self.utxos = list()
        self.spent_utxos = list()
        self.history = dict()
        self.balance = decimal.Decimal("0")
        self.new_history = False

    def get_xpub(self):
        """
        Returns this account's extended public key.

        :returns: a string containing the account's XPUB.
        """
        return self.account_master.hwif()

    def get_key(self, index, change=False):
        """
        Returns a specified pycoin.key object.

        :param index: The index of the desired key
        :param change: a boolean indicating which key root to use
        :returns: a key object associated with the given index
        """
        root_key = self.root_change_key if change else self.root_spend_key
        return root_key.subkey(index)

    def get_next_unused_key(self, change=False, using=False):
        """
        Returns the next unused key object in the sequence.

        :param change: a boolean indicating which key root to use
        :param using: a boolean indicating whether to mark key as used now
        :returns: a key object associated with the next unused index
        """
        indicies = self.change_indicies if change else self.spend_indicies
        for i, is_used in enumerate(indicies):
            if not is_used:
                if using:
                    indicies[i] = True
                return self.get_key(i, change)

    def get_all_known_addresses(self, change=False):
        """
        Returns a list of all addresses currently known to us.

        :param change: a boolean indicating which key root to use
        :returns: a list of address strings containing all addresses known
                    for the given root
        """
        indicies = self.change_indicies if change else self.spend_indicies
        addrs = [self.get_key(i, change).p2sh_p2wpkh_address()
                 for i in range(len(indicies))]
        return addrs

    def get_all_used_addresses(self):
        """
        Returns a list of all addresses that have been used previously.

        :returns: a list of address strings containing all used addresses
                    for the given root
        """
        return list(self.history.keys())

    async def _get_history(self, txids):
        """
        Returns a list of pycoin.tx.Tx objects associated
                    with the given txids

        :param txids: a list of txid strings to retrieve tx histories for
        :returns: Future, a list of Tx objects
        """
        method = "blockchain.transaction.get"
        results = list()
        for txid in txids:
            results.append(await self.connection.listen_rpc(method, [txid]))
        txs = [Tx.from_hex(tx_hex) for tx_hex in results]
        return txs

    async def _get_balance(self, address):
        """
        Returns the current balance associated with a given address.

        :param address: an address string to retrieve a balance for
        :returns: Future, a Decimal representing the balance
        """
        method = "blockchain.address.get_balance"
        result = await self.connection.listen_rpc(method, [address])
        return decimal.Decimal(str(result["confirmed"])) / Wallet.COIN

    async def _get_utxos(self, address):
        """
        Returns a list of pycoin.tx.Spendable objects for all
        UTXOS associated with the given address

        :param address: an address string to retrieve a balance for
        :returns: Future, a Decimal representing the balance
        """
        method = "blockchain.address.listunspent"
        result = await self.connection.listen_rpc(method, [address])
        utxos = list()
        for unspent in result:
            method = "blockchain.transaction.get"
            txid = unspent["tx_hash"]
            vout = unspent["tx_pos"]
            result = await self.connection.listen_rpc(method, [txid])
            spendables = Tx.from_hex(result).tx_outs_as_spendable()
            utxos.append(spendables[vout])
        return utxos

    def _get_spend_value(self, this_tx, address):
        """
        Finds the value of the txin/txout in the given Tx object that is
            associated with our address.

        :param this_tx: A Tx object given from our transaction history
        :param address: The address of ours that is associated with the
            given transaction
        :returns: The coin value associated with our input/output.
        """
        input_ = None
        for txin in this_tx.txs_in:
            key = SegwitKey.from_sec(
                txin.witness[1], netcode=self.chain.netcode)
            if key.p2sh_p2wpkh_address() == address:
                input_ = txin

        prev_tx = self.loop.run_until_complete(
            self._get_history([str(input_.previous_hash)])).pop()
        prev_txout = prev_tx.txs_out[input_.previous_index]
        return prev_txout.coin_value / Wallet.COIN

    def _process_history(self, history, address):
        """
        Creates a _History namedtuple from a given Tx object.

        :param history: A Tx object given from our transaction history
        :param address: The address of ours that is associated with the
            given transaction
        :returns: A new _History namedtuple for our history
        """
        value = None
        is_spend = False
        for txout in history.txs_out:
            if txout.address(netcode=self.chain.netcode) == address:
                value = txout.coin_value / Wallet.COIN
        if not value:
            is_spend = True
            value = self._get_spend_value(history, address)
        history_tuple = self._History(tx_obj=history,
                                      is_spend=is_spend,
                                      value=value)
        return history_tuple

    def _interpret_history(self, histories, change=False):
        """
        Populates the wallet's data structures based on a list of tx histories.
        Should only be called by discover_keys(),

        :param histories: a list of tx histories from the server
        :param change: a boolean indicating which key index list to use
        :returns: A boolean that is true if all given histories were empty
        """
        indicies = self.change_indicies if change else self.spend_indicies
        is_empty = True
        for history in histories:
            if history:
                key = self.get_key(len(indicies), change)
                address = key.p2sh_p2wpkh_address()
                txids = [tx["tx_hash"] for tx in history]

                if not change:
                    this_history = self.loop.run_until_complete(
                        self._get_history(txids))
                    this_history = [self._process_history(hist, address)
                        for hist in this_history]
                    self.history[address] = this_history
                self.balance += self.loop.run_until_complete(
                    self._get_balance(address))
                self.utxos.extend(self.loop.run_until_complete(
                    self._get_utxos(address)))

                indicies.append(True)
                is_empty = False
            else:
                indicies.append(False)
        return is_empty

    async def _interpret_new_history(self, address, history):
        """
        Coroutine, Populates the wallet's data structures based on a new
        new tx history. Should only be called by _dispatch_result(),

        :param address: the address associated with this new tx history
        :param history: a list of tx histories from the server
        :param change: a boolean indicating which key index list to use
        :returns: A boolean that is true if all given histories were empty
        """
        is_empty = True
        if history:
            txid = history["tx_hash"]

            new_history_list = await self._get_history([txid])
            new_history = new_history_list.pop()
            new_history = self._process_history(new_history, address)

            if address in self.history:
                if str(new_history.tx_obj) not in \
                        [str(hist.tx_obj) for hist in self.history[address]]:
                    self.history[address].append(new_history)
            else:
                self.history[address] = [new_history]

            new_utxos = await self._get_utxos(address)
            for utxo in new_utxos:
                if str(utxo) not in [str(spent) for spent in self.spent_utxos]:
                    self.utxos.append(utxo)
                    self.balance += await self._get_balance(address)

            for i in range(len(self.spend_indicies)):
                key = self.get_key(i, change=False)
                if key.p2sh_p2wpkh_address() == address:
                    self.spend_indicies[i] = True
                    break
            is_empty = False
        return is_empty

    def discover_keys(self, change=False):
        """
        Iterates through key indicies (_GAP_LIMIT) at a time and retrieves tx
        histories from the server, then populates our data structures using
        _interpret_history, Should be called manually once for each key root.

        :param change: a boolean indicating which key index list to use
        """
        logging.info("Discovering transaction history. change=%s", change)
        method = "blockchain.address.get_history"
        current_index = 0
        quit_flag = False
        while not quit_flag:
            futures = list()
            for i in range(current_index, current_index + Wallet._GAP_LIMIT):
                addr = self.get_key(i, change).p2sh_p2wpkh_address()
                futures.append(self.connection.listen_rpc(method, [addr]))

            result = self.loop.run_until_complete(asyncio.gather(*futures))
            quit_flag = self._interpret_history(result, change)
            current_index += Wallet._GAP_LIMIT
        self.new_history = True

    async def listen_to_addresses(self):
        """
        Coroutine, adds all known addresses to the subscription queue, and
        begins consuming the queue so we can recieve new tx histories from
        the server asynchronously.
        """
        method = "blockchain.address.subscribe"
        addrs = self.get_all_known_addresses()
        for addr in addrs:
            self.connection.listen_subscribe(method, [addr])

        await self.connection.consume_queue(self._dispatch_result)

    async def _dispatch_result(self, result):
        """
        Gets called by the Connection's consume_queue method when a new tx
        historiy is sent from the server, then populates data structures using
        _interpret_new_history.

        :param result: an address that has some new tx history
        """
        addr = result[0]
        method = "blockchain.address.get_history"
        history = await self.connection.listen_rpc(method, [addr])
        empty_flag = await self._interpret_new_history(addr, history[0])
        if not empty_flag:
            self.new_history = True

    @staticmethod
    def _calculate_vsize(tx):
        """
        Calculates the virtual size of tx in bytes.

        :param tx: a Tx object that we need to get the vsize for
        :returns: An int representing the vsize of the given Tx
        """
        def _total_size(tx):
            ins = len(tx.txs_in)
            outs = len(tx.txs_out)
            return (ins * 180 + outs * 34) + (10 + ins)
        def _base_size(tx):
            buffer = io.BytesIO()
            tx.stream(buffer)
            return len(buffer.getvalue())

        weight = 3 * _base_size(tx) + _total_size(tx)
        return weight // 4

    def _get_fee(self, tx):
        """
        Calculates the size of tx and gets a fee/kb estimate from the server.

        :param tx: a Tx object that we need to estimate a fee for
        :returns: An int representing the appropriate fee in satoshis
        """
        tx_kb_count = Wallet._calculate_vsize(tx) / 1024
        method = "blockchain.estimatefee"
        coin_per_kb = self.loop.run_until_complete(
            self.connection.listen_rpc(method, [6]))
        if coin_per_kb < 0:
            raise Exception("Cannot get a fee estimate")
        return int((tx_kb_count * coin_per_kb) * Wallet.COIN)

    def _mktx(self, out_addr, amount, version=1):
        """
        Builds a standard Bitcoin transaction - in the most naive way.
        Coin selection is basically random. Uses one output and one change
        address. Takes advantage of our subclasses to implement BIP69. Uses
        the server's fee estimation through our _get_fee() method.

        :param out_addr: an address to send to
        :param amount: a Decimal amount in whole BTC
        :param version: an int representing the Tx version
        :returns: A fully formaed and signed Tx object
        """
        amount *= Wallet.COIN
        fee_highball = 100000
        total_out = decimal.Decimal("0")

        spendables = list()
        in_addrs = set()
        del_indexes = list()
        for i, utxo in enumerate(self.utxos):
            if total_out < amount + fee_highball:
                self.spent_utxos.append(utxo)
                spendables.append(LexSpendable.promote(utxo))
                in_addrs.add(utxo.address(self.chain.netcode))
                del_indexes.append(i)
                total_out += utxo.coin_value
        spendables.sort()
        self.utxos = [utxo for i, utxo in enumerate(self.utxos)
                      if i not in del_indexes]

        change_key = self.get_next_unused_key(change=True, using=True)
        change_addr = change_key.p2sh_p2wpkh_address()
        payables = list()
        payables.append((out_addr, amount))
        payables.append((change_addr, 0))

        redeem_scripts = dict()
        wifs = list()
        for change in (True, False):
            indicies = self.change_indicies if change else self.spend_indicies
            for i, used in enumerate(indicies):
                key = self.get_key(i, change)
                if used and key.p2sh_p2wpkh_address() in in_addrs:
                    p2aw_script = key.p2sh_p2wpkh_script()
                    script_hash = key.p2sh_p2wpkh_script_hash()
                    redeem_scripts[script_hash] = p2aw_script
                    wifs.append(key.wif())

        txs_in = [spendable.tx_in() for spendable in spendables]
        txs_out = list()
        for payable in payables:
            bitcoin_address, coin_value = payable
            script = standard_tx_out_script(bitcoin_address)
            txs_out.append(LexTxOut(coin_value, script))
        txs_out.sort()
        txs_out = [LexTxOut.demote(txout) for txout in txs_out]

        chg_vout = None
        for i, txout in enumerate(txs_out):
            if txout.address(self.chain.netcode) == change_addr:
                chg_vout = i
                break

        tx = Tx(version=version, txs_in=txs_in, txs_out=txs_out)
        tx.set_unspents(spendables)

        fee = self._get_fee(tx)
        decimal_fee = decimal.Decimal(str(fee)) / Wallet.COIN
        if not amount / Wallet.COIN + decimal_fee <= self.balance:
            raise Exception("Insufficient funds to cover fee")

        distribute_from_split_pool(tx, fee)
        sign_tx(tx, wifs=wifs,
                netcode=self.chain.netcode,
                p2sh_lookup=redeem_scripts)
        return (tx, chg_vout, fee)

    def spend(self, address, amount):
        """
        Gets a new tx from _mktx() and sends it to the server to be broadcast,
        then inserts the new tx into our tx history and includes our change
        utxo, which is currently assumed to be the last output in the Tx.

        :param address: an address to send to
        :param amount: a Decimal amount in whole BTC
        :returns: The txid of our new tx, given after a successful broadcast
        """
        tx, chg_vout, fee = self._mktx(address, amount)
        method = "blockchain.transaction.broadcast"
        txid = self.loop.run_until_complete(
            self.connection.listen_rpc(method, [tx.as_hex()]))

        new_utxo = tx.tx_outs_as_spendable()[chg_vout]
        change_address = new_utxo.address(netcode=self.chain.netcode)

        history = self._History(tx_obj=tx, is_spend=True, value=amount)
        self.history[change_address] = [history]
        self.balance -= amount
        self.utxos.append(new_utxo)
        self.new_history = True

        method = "blockchain.address.subscribe"
        self.connection.listen_subscribe(method, [change_address])
        return (txid, fee)

    def __str__(self):
        """
        Special method __str__()

        :returns: The string representation of this wallet object
        """
        pprinter = pprint.PrettyPrinter(indent=4)
        str_ = list()
        str_.append("\nXPUB: {}".format(self.get_xpub()))
        str_.append("\nHistory:\n{}".format(
            pprinter.pformat(self.history)))
        str_.append("\nUTXOS:\n{}".format(
            pprinter.pformat(self.utxos)))
        str_.append("\nBalance: {} {}".format(
            self.balance, self.chain.chain_1209k.upper()))
        str_.append("\nYour current address: {}".format(
            self.get_next_unused_key().p2sh_p2wpkh_address()))
        return "".join(str_)

def get_random_onion(loop, chain):
    """
    Grabs a random onion server from a list that it gets from our
    scrape_onion_servers function.

    :param chain: Our current chain info
    :returns: A server info tuple for a random .onion Electrum server
    """
    servers = loop.run_until_complete(
        scrape_onion_servers(chain_1209k=chain.chain_1209k))
    if not servers:
        raise Exception("No electrum servers found!")
    random.shuffle(servers)
    return servers.pop()

async def print_loop(wallet):
    """
    Coroutine. Prints the wallet's string representation to stdout if
    wallet.new_history is True. Checks every second.

    :param wallet: a wallet object
    """
    while True:
        await asyncio.sleep(1)
        if wallet.new_history:
            print(wallet)
            wallet.new_history = False

def main():
    """
    Builds a wallet object, discovers keys and listens to addresses.
    Also handles all user IO with help from the print_loop() coroutine function.
    """
    chain = TBTC
    loop = asyncio.get_event_loop()

    server, port = get_random_onion(loop, chain)
    connection = Connection(loop, server, port)
#    connection = Connection(loop, "192.168.1.200", 50001)

    email = input("Enter email: ")
    passphrase = getpass.getpass("Enter passphrase: ")
    confirm = getpass.getpass("Confirm your passphrase: ")
    assert passphrase == confirm, "Passphrase and confirmation did not match"
    assert email and passphrase, "Email and/or passphrase were blank"
    wallet = Wallet(email, passphrase, connection, loop, chain)

    wallet.discover_keys()
    wallet.discover_keys(change=True)

    if len(sys.argv) > 1 and sys.argv[1] == "spend":
        print("\nBalance: {} {}".format(
            wallet.balance, chain.chain_1209k.upper()))
        print("Enter a destination address:")
        spend_addr = input("> ")
        print("Enter an amount to spend:")
        spend_amount = decimal.Decimal(input("> "))
        assert spend_addr and spend_amount, \
                "Spend address and/or amount were blank"
        assert spend_amount <= wallet.balance, "Insufficient funds"

        txid, fee = wallet.spend(spend_addr, spend_amount)
        decimal_fee = decimal.Decimal(str(fee)) / Wallet.COIN
        print("Added a miner fee of: {} {}".format(
            decimal_fee, chain.chain_1209k.upper()))
        print("Transaction sent!\nID: {}".format(txid))

    asyncio.ensure_future(wallet.listen_to_addresses())
    asyncio.ensure_future(print_loop(wallet))

    loop.run_forever()
    loop.close()

if __name__ == '__main__':
    main()
