#! /usr/bin/env python3

import logging, sys
FORMAT = "%(asctime)s %(levelname)s: %(message)s"

stdout_hdlr = logging.StreamHandler(sys.stdout)
stdout_hdlr.setFormatter(logging.Formatter(FORMAT))
stdout_hdlr.setLevel(logging.INFO)

file_hdlr = logging.FileHandler(filename="nowallet.log", mode="w")
file_hdlr.setFormatter(logging.Formatter(FORMAT))
file_hdlr.setLevel(logging.DEBUG)

logging.basicConfig(level=logging.DEBUG,
                    handlers=[stdout_hdlr, file_hdlr])

import asyncio, io, random, decimal, collections, getpass, pprint, time
from functools import total_ordering

from connectrum.client import StratumClient
from pycoin.ui import standard_tx_out_script
from pycoin.tx.tx_utils import distribute_from_split_pool, sign_tx
from pycoin.tx.Tx import Tx
from pycoin.tx.TxOut import TxOut

from subclasses import MyServerInfo, LexSpendable, LexTxOut, SegwitBIP32Node
from keys import derive_key
from scrape import scrape_onion_servers
#import exchange_rate

class Connection:
    """
    Connection object. Connects to an Electrum server, and handles all
        Stratum protocol messages.
    """
    def __init__(self, loop, server, port):
        """
        Connection object constructor.

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

@total_ordering
class History:
    """
    History object. Holds data relevant to a piece of
        our transaction history.
    """
    def __init__(self, tx_obj, is_spend, value, height):
        """
        History object constructor.

        :param tx_obj: a pycoin.Tx object representing the tx data
        :param is_spend: boolean, was this tx a spend from our wallet?
        :param value: the coin_value of this tx
        :param height: the height of the block this tx is included in
        :returns: A new History object
        """
        self.tx_obj = tx_obj
        self.is_spend = is_spend
        self.value = value
        self.height = height
        self.timestamp = None

    async def get_timestamp(self, connection):
        """
        Coroutine. Gets the timestamp for this Tx based on the given height.

        :param connection: a Connection object for getting a block header
            from the server
        """
        if self.height:
            block_header = await connection.listen_rpc(
                Wallet.methods["get_header"], [self.height])
            self.timestamp = time.asctime(time.localtime(
                block_header["timestamp"]))
            logging.debug("Got timestamp %d from block at height %s",
                           self.height, self.timestamp)
        else:
            self.timestamp = time.asctime(time.localtime())

    def __eq__(self, other):
        """
        Special method __eq__()
        Compares two History objects for equality.
        """
        return self.height == other.height and \
            str(self.tx_obj) == str(other.tx_obj)

    def __lt__(self, other):
        """
        Special method __lt__()
        Compares two History objects by height.
        """
        return self.height < other.height

    def __str__(self):
        """
        Special method __str__()

        :returns: The string representation of this History object
        """
        return ("<History: TXID:{} is_spend:{} " + \
            "value:{} height:{} timestamp:{}>").format(self.tx_obj.id(),
                                                       self.is_spend,
                                                       self.value,
                                                       self.height,
                                                       self.timestamp)
    def __repr__(self):
        return str(self)

Chain = collections.namedtuple("Chain",
                               ["netcode", "chain_1209k", "bip44"])
BTC = Chain(netcode="BTC",
            chain_1209k="btc",
            bip44=0)
TBTC = Chain(netcode="XTN",
             chain_1209k="tbtc",
             bip44=1)
LTC = Chain(netcode="LTC",
            chain_1209k="ltc",
            bip44=2)
#VTC = Chain(netcode="VTC",
#            chain_1209k="vtc",
#            bip44=28)

class Wallet:
    """
    Provides all functionality required for a fully functional and secure
    HD brainwallet based on the Warpwallet technique.
    """
    COIN = 100000000
    _GAP_LIMIT = 20

    methods = {"get": "blockchain.transaction.get",
               "get_balance": "blockchain.address.get_balance",
               "listunspent": "blockchain.address.listunspent",
               "get_history": "blockchain.address.get_history",
               "get_header": "blockchain.block.get_header",
               "subscribe": "blockchain.address.subscribe",
               "estimatefee": "blockchain.estimatefee",
               "broadcast": "blockchain.transaction.broadcast"}

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
        self.zeroconf_balance = decimal.Decimal("0")
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

    def get_tx_history(self):
        """
        Returns a list of all History objects in our history, ordered
            by height/timestamp.

        :returns: an ordered list of History objects.
        """
        history = list()
        for value in self.history.values():
            history.extend(value)
        history.sort()
        return history

    async def _get_history(self, txids):
        """
        Coroutine. Returns a list of pycoin.tx.Tx objects associated
                    with the given txids

        :param txids: a list of txid strings to retrieve tx histories for
        :returns: Future, a list of Tx objects
        """
        results = list()
        for txid in txids:
            future = self.connection.listen_rpc(self.methods["get"], [txid])
            hex_ = await future
            results.append(hex_)
            logging.debug("Retrieved Tx hex: %s", hex_)
        txs = [Tx.from_hex(tx_hex) for tx_hex in results]
        return txs

    async def _get_balance(self, address):
        """
        Coroutine. Returns the current balance associated with a given address.

        :param address: an address string to retrieve a balance for
        :returns: Future, a Decimal representing the balance
        """
        future = self.connection.listen_rpc(
            self.methods["get_balance"], [address])
        result = await future
        logging.debug("Retrieved a balance for address: %s", address)
        confirmed = decimal.Decimal(str(result["confirmed"])) / Wallet.COIN
        zeroconf = decimal.Decimal(str(result["unconfirmed"])) / Wallet.COIN
        return confirmed, zeroconf

    async def _get_utxos(self, address):
        """
        Coroutine. Returns a list of pycoin.tx.Spendable objects for all
        UTXOS associated with the given address

        :param address: an address string to retrieve a balance for
        :returns: Future, a list of pycoin Spendable objects.
        """
        future = self.connection.listen_rpc(
            self.methods["listunspent"], [address])
        result = await future
        logging.debug("Retrieving utxos for address %s", address)
        utxos = list()
        for unspent in result:
            txid = unspent["tx_hash"]
            vout = unspent["tx_pos"]
            future = self.connection.listen_rpc(self.methods["get"], [txid])
            result = await future
            spendables = Tx.from_hex(result).tx_outs_as_spendable()
            utxos.append(spendables[vout])
            logging.debug("Retrieved utxo: %s", spendables[vout])
        return utxos

    def _get_spend_value(self, this_tx):
        """
        Finds the value of the txout in the given Tx object that is
            associated with our spend.

        :param this_tx: A Tx object given from our transaction history
        :returns: The coin value associated with our spend output.
        """
        change_addrs = self.get_all_known_addresses(change=True)
        chg_vout = None
        for i, txout in enumerate(this_tx.txs_out):
            address = txout.address(netcode=self.chain.netcode)
            if address in change_addrs:
                chg_vout = i
        spend_vout = 0 if chg_vout == 1 else 1
        return this_tx.txs_out[spend_vout].coin_value

    async def _process_history(self, history, address, height):
        """
        Coroutine. Creates a _History namedtuple from a given Tx object.

        :param history: A Tx object given from our transaction history
        :param address: The address of ours that is associated with the
            given transaction
        :returns: A new _History namedtuple for our history
        """
        value = None
        is_spend = False
        for txout in history.txs_out:
            if txout.address(netcode=self.chain.netcode) == address:
                value = txout.coin_value
        if not value:
            is_spend = True
            value = self._get_spend_value(history)

        decimal_value = decimal.Decimal(str(value)) / Wallet.COIN
        history_obj = History(tx_obj=history,
                              is_spend=is_spend,
                              value=decimal_value,
                              height=height)
        await history_obj.get_timestamp(self.connection)
        logging.debug("Processed history object: %s", history_obj)
        return history_obj

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
        # len(histories) == Wallet._GAP_LIMIT
        # Each iteration represents one key index
        for history in histories:
            if history:
                # Get key/address for current index
                key = self.get_key(len(indicies), change)
                address = key.p2sh_p2wpkh_address()
                # Reassign historic info for this index
                txids = [tx["tx_hash"] for tx in history]
                heights = [tx["height"] for tx in history]

                # Get Tx objects
                this_history = self.loop.run_until_complete(
                    self._get_history(txids))

                # Process all Txs into our History objects
                futures = list()
                for i, hist in enumerate(this_history):
                    future = self._process_history(hist, address, heights[i])
                    futures.append(future)
                processed_history = self.loop.run_until_complete(
                    asyncio.gather(*futures))

                # Delete Txs that are just recieving change
                if change:
                    del_indexes = list()
                    for i, hist in enumerate(processed_history):
                        if not hist.is_spend:
                            del_indexes.append(i)
                    processed_history = [hist for i, hist
                                         in enumerate(processed_history)
                                         if i not in del_indexes]
                if processed_history:
                    self.history[address] = processed_history

                # Adjust our balances for this index
                confirmed, zeroconf = self.loop.run_until_complete(
                    self._get_balance(address))
                self.balance += confirmed
                self.zeroconf_balance += zeroconf

                # Add utxos to our list
                self.utxos.extend(self.loop.run_until_complete(
                    self._get_utxos(address)))

                # Mark this index as used since it has a history
                indicies.append(True)
                is_empty = False
            else:
                # Otherwise mark this index as unused
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
            spend_addrs = self.get_all_known_addresses()
            # Reassign historic info for new history
            txid = history["tx_hash"]
            height = history["height"]

            # Get Tx object and process into our History object
            tx_list = await self._get_history([txid])
            new_history = await self._process_history(
                tx_list.pop(), address, height)

            if address in self.history:
                if str(new_history.tx_obj) not in \
                        [str(hist.tx_obj) for hist in self.history[address]]:
                    self.history[address].append(new_history)
                else:
                    # tx confirming
                    if not new_history.is_spend:
                        self.balance += new_history.value
                        self.zeroconf_balance -= new_history.value
            else:
                # recieving coins
                self.history[address] = [new_history]
                if not new_history.is_spend and address in spend_addrs:
                    self.zeroconf_balance += new_history.value

            # Add new utxo to our list if not already spent
            new_utxos = await self._get_utxos(address)
            for utxo in new_utxos:
                if str(utxo) not in [str(spent) for spent in self.spent_utxos]:
                    self.utxos.append(utxo)

            # If address is found to belong to a spend index, mark it as used
            for i in range(len(self.spend_indicies)):
                key = self.get_key(i, change=False)
                if key.p2sh_p2wpkh_address() == address:
                    self.spend_indicies[i] = True
                    break
            is_empty = False
        return is_empty

    def _discover_keys(self, change=False):
        """
        Iterates through key indicies (_GAP_LIMIT) at a time and retrieves tx
        histories from the server, then populates our data structures using
        _interpret_history, Should be called manually once for each key root.

        :param change: a boolean indicating which key index list to use
        """
        logging.info("Discovering transaction history. change=%s", change)
        current_index = 0
        quit_flag = False
        while not quit_flag:
            futures = list()
            for i in range(current_index, current_index + Wallet._GAP_LIMIT):
                addr = self.get_key(i, change).p2sh_p2wpkh_address()
                future = self.connection.listen_rpc(
                    self.methods["get_history"], [addr])
                futures.append(future)

            result = self.loop.run_until_complete(asyncio.gather(*futures))
            quit_flag = self._interpret_history(result, change)
            current_index += Wallet._GAP_LIMIT
        self.new_history = True

    def discover_all_keys(self):
        """
        Calls discover_keys for change and spend keys.
        """
        start_discovering = time.time()
        for change in (False, True):
            self._discover_keys(change=change)
        end_discovering = time.time()
        seconds = end_discovering - start_discovering
        logging.info("Discovered history in {0:.3f} seconds".format(seconds))

    async def listen_to_addresses(self):
        """
        Coroutine, adds all known addresses to the subscription queue, and
        begins consuming the queue so we can recieve new tx histories from
        the server asynchronously.
        """
        addrs = self.get_all_known_addresses()
        for addr in addrs:
            self.connection.listen_subscribe(self.methods["subscribe"], [addr])
        logging.debug("Listening for updates involving any known address...")
        await self.connection.consume_queue(self._dispatch_result)

    async def _dispatch_result(self, result):
        """
        Gets called by the Connection's consume_queue method when a new tx
        historiy is sent from the server, then populates data structures using
        _interpret_new_history.

        :param result: an address that has some new tx history
        """
        addr = result[0]
        logging.debug("Dispatched a new history for address %s", addr)
        future = self.connection.listen_rpc(self.methods["get_history"], [addr])
        history = await future
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

    @staticmethod
    def satb_to_coinkb(satb):
        """
        Converts a fee rate from satoshis per byte to coins per KB.

        :param satb: An int representing a fee rate in satoshis per byte
        :returns: An float representing the rate in coins per KB
        """
        return (satb * 1000) / Wallet.COIN

    @staticmethod
    def coinkb_to_satb(coinkb):
        """
        Converts a fee rate from coins per KB to satoshis per byte.

        :param coinkb: A float representing a fee rate in coins per KB
        :returns: An int representing the rate in satoshis per byte
        """
        return int((coinkb / 1000) * Wallet.COIN)

    def get_fee_estimation(self):
        """
        Gets a fee estimate from the server.

        :returns: An int representing the appropriate fee in coins per KB
        """
        coin_per_kb = self.loop.run_until_complete(
            self.connection.listen_rpc(self.methods["estimatefee"], [6]))
        if coin_per_kb < 0:
            raise Exception("Cannot get a fee estimate")
        logging.info("Current fee estimate from server is %f %s/KB",
            coin_per_kb, self.chain.chain_1209k.upper())
        return coin_per_kb

    @staticmethod
    def _get_fee(tx, coin_per_kb):
        """
        Calculates the size of tx based on a given estimate from the server.

        :param tx: a Tx object that we need to estimate a fee for
        :param coin_per_kb: Fee estimation in whole coins per KB
        :returns: An int representing the appropriate fee in satoshis
        """
        if coin_per_kb > Wallet.satb_to_coinkb(1000):
            raise ValueError("Given fee rate is extraordinarily high.")
        tx_kb_count = Wallet._calculate_vsize(tx) / 1000
        return int((tx_kb_count * coin_per_kb) * Wallet.COIN)

    def _mktx(self, out_addr, amount, version=1, rbf=False):
        """
        Builds a standard Bitcoin transaction - in the most naive way.
        Coin selection is basically random. Uses one output and one change
        address. Takes advantage of our subclasses to implement BIP69. Uses
        the server's fee estimation through our _get_fee() method.

        :param out_addr: an address to send to
        :param amount: a Decimal amount in whole BTC
        :param version: an int representing the Tx version
        :param rbf: A boolean that says whether to mark Tx as replaceable
        :returns: A not-fully-formed and unsigned Tx object
        """
        amount *= Wallet.COIN
        fee_highball = 100000
        total_out = decimal.Decimal("0")

        spendables = list()
        in_addrs = set()
        del_indexes = list()
        # Collect enough utxos for this spend
        # Add them to spent list and delete them from utxo list
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

        # Get change address, mark index as used, and create payables list
        change_key = self.get_next_unused_key(change=True, using=True)
        change_addr = change_key.p2sh_p2wpkh_address()
        payables = list()
        payables.append((out_addr, amount))
        payables.append((change_addr, 0))

        # Create input list from utxos
        # Set sequence numbers to zero if using RBF.
        txs_in = [spendable.tx_in() for spendable in spendables]
        if rbf:
            logging.info("Spending with opt-in Replace by Fee! (RBF)")
            for txin in txs_in:
                txin.sequence = 0

        # Create output list from payables
        txs_out = list()
        for payable in payables:
            bitcoin_address, coin_value = payable
            script = standard_tx_out_script(bitcoin_address)
            txs_out.append(LexTxOut(coin_value, script))
        txs_out.sort()
        txs_out = [LexTxOut.demote(txout) for txout in txs_out]

        # Search for change output index after lex sort
        chg_vout = None
        for i, txout in enumerate(txs_out):
            if txout.address(self.chain.netcode) == change_addr:
                chg_vout = i
                break

        # Create pycoin Tx object from inputs/outputs
        tx = Tx(version=version, txs_in=txs_in, txs_out=txs_out)
        tx.set_unspents(spendables)
        return tx, in_addrs, chg_vout

    def _signtx(self, unsigned_tx, in_addrs, fee):
        """
        Signs Tx and redistributes outputs to include the miner fee.

        :param unsigned_tx: an unsigned Tx to sign and add fee to
        :param in_addrs: a list of our addresses that have recieved coins
        :param fee: an int representing the desired Tx fee
        """
        redeem_scripts = dict()
        wifs = list()
        # Search our indicies for keys used, given in in_addrs list
        # Populate lists with our privkeys and redeemscripts
        for change in (True, False):
            for i, addr in enumerate(self.get_all_known_addresses(change)):
                key = self.get_key(i, change)
                if addr in in_addrs:
                    p2aw_script = key.p2sh_p2wpkh_script()
                    script_hash = key.p2sh_p2wpkh_script_hash()
                    redeem_scripts[script_hash] = p2aw_script
                    wifs.append(key.wif())

        # Include our total fee and sign the Tx
        distribute_from_split_pool(unsigned_tx, fee)
        sign_tx(unsigned_tx, wifs=wifs,
                netcode=self.chain.netcode,
                p2sh_lookup=redeem_scripts)

    def _create_replacement_tx(self, hist_obj, version=1):
        if hist_obj.height == 0 and hist_obj.is_spend:
            old_tx = hist_obj.tx_obj
            spendables = old_tx.unspents
            chg_vout = None

            in_addrs = set()
            for utxo in spendables:
                in_addrs.add(utxo.address(self.chain.netcode))

            txs_out = list()
            for i, txout in enumerate(old_tx.txs_out):
                if txout.coin_value / Wallet.COIN == hist_obj.value:
                    value = txout.coin_value
                else:
                    value = 0
                    chg_vout = i
                txs_out.append(TxOut(value, txout.script))

            new_tx = Tx(version=version, txs_in=old_tx.txs_in, txs_out=txs_out)
            new_tx.set_unspents(spendables)
            return new_tx, in_addrs, chg_vout
        else:
            raise ValueError("This transaction is not replaceable")

    def spend(self, address, amount, coin_per_kb, rbf=False):
        """
        Gets a new tx from _mktx() and sends it to the server to be broadcast,
        then inserts the new tx into our tx history and includes our change
        utxo, which is currently assumed to be the last output in the Tx.

        :param address: an address to send to
        :param amount: a Decimal amount in whole BTC
        :param coin_per_kb: a fee rate given in whole coins per KB
        :param rbf: a boolean saying whether to mark the tx as replaceable
        :returns: The txid of our new tx, given after a successful broadcast
        """
        tx, in_addrs, chg_vout = self._mktx(address, amount, rbf=rbf)

        fee = self._get_fee(tx, coin_per_kb)
        decimal_fee = decimal.Decimal(str(fee)) / Wallet.COIN
        if not amount + decimal_fee <= self.balance:
            raise Exception("Insufficient funds to cover fee")

        self._signtx(tx, in_addrs, fee)
        txid = self.loop.run_until_complete(
            self.connection.listen_rpc(
                self.methods["broadcast"], [tx.as_hex()]))

        change_out = tx.txs_out[chg_vout]
        coin_in = decimal.Decimal(str(tx.total_in())) / Wallet.COIN
        change = decimal.Decimal(str(change_out.coin_value)) / Wallet.COIN

        self.balance -= coin_in
        self.zeroconf_balance += change
        self.new_history = True

        change_address = change_out.address(netcode=self.chain.netcode)
        self.connection.listen_subscribe(
            self.methods["subscribe"], [change_address])
        return txid, decimal_fee

    def replace_by_fee(self, hist_obj, coin_per_kb):
        tx, in_addrs, chg_vout = self._create_replacement_tx(hist_obj)
        new_fee = self._get_fee(tx, coin_per_kb)

        self._signtx(tx, in_addrs, new_fee)
        txid = self.loop.run_until_complete(
            self.connection.listen_rpc(
                self.methods["broadcast"], [tx.as_hex()]))

        fee_diff = new_fee - hist_obj.tx_obj.fee()
        self.balance -= fee_diff
        hist_obj.tx_obj = tx
        return txid

    def __str__(self):
        """
        Special method __str__()

        :returns: The string representation of this wallet object
        """
        pprinter = pprint.PrettyPrinter(indent=4)
        str_ = list()
        str_.append("\nXPUB: {}".format(self.get_xpub()))
        str_.append("\nHistory:\n{}".format(
            pprinter.pformat(self.get_tx_history())))
        str_.append("\nUTXOS:\n{}".format(
            pprinter.pformat(self.utxos)))
        str_.append("\nBalance: {} ({} unconfirmed) {}".format(
            float(self.balance), float(self.zeroconf_balance),
            self.chain.chain_1209k.upper()))
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
    return random.choice(servers)

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
#    from pycoin.networks.network import Network
#    from pycoin.networks import register_network
#    vtc_net = Network('VTC', 'Vertcoin', 'mainnet',
#        wif=b'\x80', address=b'\x47', pay_to_script=b'\x05',
#        prv32=b'\x04358394', pub32=b'\x043587cf')
#    register_network(vtc_net)

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
    wallet.discover_all_keys()

    if len(sys.argv) > 1 and sys.argv[1].lower() == "spend":
        print("\nConfirmed balance: {} {}".format(
            wallet.balance, chain.chain_1209k.upper()))
        print("Enter a destination address:")
        spend_addr = input("> ")
        print("Enter an amount to spend:")
        spend_amount = decimal.Decimal(input("> "))
        assert spend_addr and spend_amount, \
                "Spend address and/or amount were blank"
        assert spend_amount <= wallet.balance, "Insufficient funds"

        use_rbf = False
        if len(sys.argv) > 2 and sys.argv[2].lower() == "rbf":
            use_rbf = True
        coin_per_kb = wallet.get_fee_estimation()

        txid, decimal_fee = wallet.spend(spend_addr,
                                         spend_amount,
                                         coin_per_kb,
                                         rbf=use_rbf)

        print("Added a miner fee of: {} {}".format(
            decimal_fee, chain.chain_1209k.upper()))
        print("Transaction sent!\nID: {}".format(txid))

    asyncio.ensure_future(wallet.listen_to_addresses())
    asyncio.ensure_future(print_loop(wallet))

    loop.run_forever()
    loop.close()

if __name__ == '__main__':
    main()
