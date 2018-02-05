import logging, sys
FORMAT = "%(asctime)s %(levelname)s: %(message)s"  # type: str

stdout_hdlr = logging.StreamHandler(sys.stdout)  # type: logging.StreamHandler
stdout_hdlr.setFormatter(logging.Formatter(FORMAT))
stdout_hdlr.setLevel(logging.INFO)

file_hdlr = logging.FileHandler(
    filename="nowallet.log", mode="w")  # type: logging.FileHandler
file_hdlr.setFormatter(logging.Formatter(FORMAT))
file_hdlr.setLevel(logging.DEBUG)

logging.basicConfig(level=logging.DEBUG,
                    handlers=[stdout_hdlr, file_hdlr])

import asyncio, io, random, collections, pprint, time
from decimal import Decimal
from functools import total_ordering
from urllib import parse
from typing import (Tuple, List, Set, Dict, KeysView, Any,
                    Union, Callable, Awaitable)

from connectrum.client import StratumClient
from connectrum.svr_info import ServerInfo
from pycoin.ui import standard_tx_out_script
from pycoin.tx.tx_utils import distribute_from_split_pool, sign_tx
from pycoin.tx.Tx import Tx
from pycoin.tx.TxIn import TxIn
from pycoin.tx.TxOut import TxOut
from pycoin.tx.Spendable import Spendable

from .subclasses import LexSpendable, LexTxOut, SegwitBIP32Node
from .keys import derive_key
from .scrape import scrape_onion_servers
#import exchange_rate

class Connection:
    """
    Connection object. Connects to an Electrum server, and handles all
        Stratum protocol messages.
    """
    def __init__(self,
                 loop: asyncio.AbstractEventLoop,
                 server: str,
                 port: int,
                 proto: str) -> None:
        """
        Connection object constructor.

        :param loop: an asyncio event loop
        :param server: a string containing a hostname
        :param port: port number that the server listens on
        :returns: A new Connection object
        """
        logging.info("Connecting...")

        self.server_info = ServerInfo(
            server, hostname=server, ports=port)  # type: MyServerInfo
        logging.info(str(self.server_info.get_port(proto)))
        self.client = StratumClient(loop)  # type: StratumClient
        self.connection = self.client.connect(
            self.server_info,
            proto_code=proto,
            use_tor=True,
            disable_cert_verify=True)  # type: asyncio.Future

        loop.run_until_complete(self._do_connect())
        self.queue = None  # type: asyncio.Queue

    async def _do_connect(self) -> None:
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

    async def listen_rpc(self, method: str, args: List) -> Any:
        """
        Coroutine. Sends a normal RPC message to the server and awaits response.

        :param method: The Electrum API method to use
        :param args: Params associated with current method
        :returns: Future. Response from server for this method(args)
        """
        return await self.client.RPC(method, *args)

    def listen_subscribe(self, method: str, args: List) -> None:
        """
        Sends a "subscribe" message to the server and adds to the queue.
        Throws away the immediate future containing the "history" hash.

        :param method: The Electrum API method to use
        :param args: Params associated with current method
        """
        t = self.client.subscribe(
            method, *args)  # type: Tuple[asyncio.Future, asyncio.Queue]
        self.queue = t[1]

    async def consume_queue(self, queue_func: \
        Callable[[List[str]], Awaitable[None]]) -> None:
        """
        Coroutine. Infinite loop that consumes the current subscription queue.

        :param queue_func: A function to call when new responses arrive
        """
        while True:
            result = await self.queue.get()  # type: List[str]
            await queue_func(result)

@total_ordering
class History:
    """
    History object. Holds data relevant to a piece of
        our transaction history.
    """

    def __init__(self,
                 tx_obj: Tx,
                 is_spend: bool,
                 value: Decimal,
                 height: int) -> None:
        """
        History object constructor.

        :param tx_obj: a pycoin.Tx object representing the tx data
        :param is_spend: boolean, was this tx a spend from our wallet?
        :param value: the coin_value of this tx
        :param height: the height of the block this tx is included in
        :returns: A new History object
        """
        self.tx_obj = tx_obj  # type: Tx
        self.is_spend = is_spend  # type: bool
        self.value = value  # type: Decimal
        self.height = height  # type: int
        self.timestamp = None  # type: str

    async def get_timestamp(self, connection: Connection) -> None:
        """
        Coroutine. Gets the timestamp for this Tx based on the given height.

        :param connection: a Connection object for getting a block header
            from the server
        """
        if self.height:
            block_header = await connection.listen_rpc(
                Wallet.methods["get_header"],
                [self.height])  # type: Dict[str, Any]
            self.timestamp = time.asctime(time.localtime(
                block_header["timestamp"]))
            logging.debug("Got timestamp %d from block at height %s",
                          self.height, self.timestamp)
        else:
            self.timestamp = time.asctime(time.localtime())

    def __eq__(self, other) -> bool:
        """
        Special method __eq__()
        Compares two History objects for equality.
        """
        return (self.height, str(self.tx_obj)) == \
            (other.height, str(other.tx_obj))

    def __lt__(self, other) -> bool:
        """
        Special method __lt__()
        Compares two History objects by height.
        """
        return self.height < other.height

    def __str__(self) -> str:
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
    def __repr__(self) -> str:
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
VTC = Chain(netcode="VTC",
            chain_1209k="vtc",
            bip44=28)

def log_time_elapsed(func: Callable) -> Callable:
    """
    Decorator. Times completion of function and logs at level INFO.
    """
    def inner(*args, **kwargs) -> None:
        """
        Decorator inner function.
        """
        start_derivation = time.time()  # type: float
        func(*args, **kwargs)
        end_derivation = time.time()  # type: float
        seconds = end_derivation - start_derivation  # type: float
        logging.info("Operation completed in {0:.3f} seconds".format(seconds))
    return inner

class Wallet:
    """
    Provides all functionality required for a fully functional and secure
    HD brainwallet based on the Warpwallet technique.
    """
    COIN = 100000000  # type: int
    _GAP_LIMIT = 20  # type: int

    methods = {
        "get": "blockchain.transaction.get",
        "get_balance": "blockchain.scripthash.get_balance",
        "listunspent": "blockchain.scripthash.listunspent",
        "get_history": "blockchain.scripthash.get_history",
        "get_header": "blockchain.block.get_header",
        "subscribe": "blockchain.scripthash.subscribe",
        "estimatefee": "blockchain.estimatefee",
        "broadcast": "blockchain.transaction.broadcast"
    }  # type: Dict[str, str]

    def __init__(self,
                 salt: str,
                 passphrase: str,
                 connection: Connection,
                 loop: asyncio.AbstractEventLoop,
                 chain) -> None:
        """
        Wallet object constructor. Use discover_keys() and listen_to_addresses()
        coroutine method to construct wallet data, and listen for new data from
        the server.

        :param salt: a string to use as a salt for key derivation
        :param passphrase: a string containing a secure passphrase
        :param connection: a Connection object
        :param loop: an asyncio event loop
        :param chain: a namedtuple containing chain-specific info
        :returns: A new, empty Wallet object
        """
        @log_time_elapsed
        def create_root_keys(salt: str,
                             passphrase: str,
                             account: int = 0) -> None:
            """
            Derives master key from salt/passphrase and initializes all
            master key attributes.

            :param salt: a string to use as a salt for key derivation
            :param passphrase: a string containing a secure passphrase
            :param account: account number, defaults to 0
            """
            logging.info("Deriving keys...")
            t = derive_key(
                salt, passphrase)  # type: Union[int, Tuple[int, bytes]]
            assert isinstance(t, tuple), "Should never fail"
            secret_exp, chain_code = t
            self.mpk = SegwitBIP32Node(
                netcode=self.chain.netcode,
                chain_code=chain_code,
                secret_exponent=secret_exp)  # type: SegwitBIP32Node

            path = "49H/{}H/{}H".format(self.chain.bip44, account)  # type: str
            self.account_master = \
                self.mpk.subkey_for_path(path)  # type: SegwitBIP32Node
            self.root_spend_key = \
                self.account_master.subkey(0)  # type: SegwitBIP32Node
            self.root_change_key = \
                self.account_master.subkey(1)  # type: SegwitBIP32Node

        self.connection = connection  # type: Connection
        self.loop = loop  # type: asyncio.AbstractEventLoop
        self.chain = chain
        self.bech32 = False

        self.mpk = None  # type: SegwitBIP32Node
        self.account_master = None  # type: SegwitBIP32Node
        self.root_spend_key = None  # type: SegwitBIP32Node
        self.root_change_key = None  # type: SegwitBIP32Node
        create_root_keys(salt, passphrase)

        # Boolean lists, True = used / False = unused
        self.spend_indicies = list()  # type: List[bool]
        self.change_indicies = list()  # type: List[bool]

        # All wallet TX info. (Does not persist!)
        self.utxos = list()  # type: List[Spendable]
        self.spent_utxos = list()  # type: List[Spendable]
        self.history = dict()  # type: Dict[str, List[History]]
        self.balance = Decimal("0")  # type: Decimal
        self.zeroconf_balance = Decimal("0")  # type: Decimal
        self.new_history = False  # type: bool

    @property
    def ypub(self) -> str:
        """
        Returns this account's extended public key.

        :returns: a string containing the account's XPUB.
        """
        return self.account_master.hwif()

    def get_key(self, index: int, change: bool = False) -> SegwitBIP32Node:
        """
        Returns a specified pycoin.key object.

        :param index: The index of the desired key
        :param change: a boolean indicating which key root to use
        :returns: a key object associated with the given index
        """
        root_key = self.root_change_key if change \
            else self.root_spend_key  # type: SegwitBIP32Node
        return root_key.subkey(index)

    def get_next_unused_key(self,
                            change: bool = False,
                            using: bool = False) -> SegwitBIP32Node:
        """
        Returns the next unused key object in the sequence.

        :param change: a boolean indicating which key root to use
        :param using: a boolean indicating whether to mark key as used now
        :returns: a key object associated with the next unused index
        """
        indicies = self.change_indicies if change \
            else self.spend_indicies  # type: List[bool]
        for i, is_used in enumerate(indicies):
            if not is_used:
                if using:
                    indicies[i] = True
                return self.get_key(i, change)
        return None

    def get_address(self, key: SegwitBIP32Node, addr=False) -> str:
        """
        Returns the segwit address for a given key.

        :param key: any given SegwitBIP32Node key
        :returns: A segwit (P2WPKH) address, either P2SH or bech32.
        """
        if not addr:
            return key.electrumx_script_hash(bech32=self.bech32)
        else:
            return key.p2sh_p2wpkh_address() if not self.bech32 \
                else key.bech32_p2wpkh_address()

    def get_all_known_addresses(self,
                                change: bool = False,
                                addr: bool=False) -> List[str]:
        """
        Returns a list of all addresses currently known to us.

        :param change: a boolean indicating which key root to use
        :returns: a list of address strings containing all addresses known
                    for the given root
        """
        indicies = self.change_indicies if change \
            else self.spend_indicies  # type: List[bool]
        addrs = [self.get_address(self.get_key(i, change=change), addr=addr)
                 for i in range(len(indicies))]  # type: List[str]
        return addrs

    def get_all_used_addresses(self) -> KeysView[str]:
        """
        Returns all addresses that have been used previously.

        :returns: address strings containing all used
            addresses for the given root
        """
        return self.history.keys()

    def get_tx_history(self) -> List[History]:
        """
        Returns a list of all History objects in our history, ordered
            by height/timestamp.

        :returns: an ordered list of History objects.
        """
        history = list()  # type: List[History]
        for value in self.history.values():
            history.extend(value)
        history.sort()
        return history

    async def _get_history(self, txids: List[str]) -> List[Tx]:
        """
        Coroutine. Returns a list of pycoin.tx.Tx objects associated
                    with the given txids

        :param txids: a list of txid strings to retrieve tx histories for
        :returns: Future, a list of Tx objects
        """
        results = list()  # type: List[str]
        for txid in txids:
            hex_ = await self.connection.listen_rpc(
                self.methods["get"], [txid])  # type: str
            results.append(hex_)
            logging.debug("Retrieved Tx hex: %s", hex_)
        txs = [Tx.from_hex(tx_hex) for tx_hex in results]  # type: List[Tx]
        return txs

    async def _get_balance(self, address: str) -> Tuple[Decimal, Decimal]:
        """
        Coroutine. Returns the current balance associated with a given address.

        :param address: an address string to retrieve a balance for
        :returns: Future, a Decimal representing the balance
        """
        result = await self.connection.listen_rpc(
            self.methods["get_balance"], [address])  # type: Dict[str, Any]
        logging.debug("Retrieved a balance for address: %s", address)
        confirmed = \
            Decimal(str(result["confirmed"])) / Wallet.COIN  # type: Decimal
        zeroconf = \
            Decimal(str(result["unconfirmed"])) / Wallet.COIN  # type: Decimal
        return confirmed, zeroconf

    async def _get_utxos(self, address: str) -> List[Spendable]:
        """
        Coroutine. Returns a list of pycoin.tx.Spendable objects for all
        UTXOS associated with the given address

        :param address: an address string to retrieve a balance for
        :returns: Future, a list of pycoin Spendable objects.
        """
        result = await self.connection.listen_rpc(
            self.methods["listunspent"], [address])  # type: Dict
        logging.debug("Retrieving utxos for address %s", address)
        utxos = list()  # type: List[Spendable]
        for unspent in result:
            txid = unspent["tx_hash"]  # type: str
            vout = unspent["tx_pos"]  # type: int
            get_result = await self.connection.listen_rpc(
                self.methods["get"], [txid])  # type: str
            tx = Tx.from_hex(get_result)  # type: Tx
            spendables = tx.tx_outs_as_spendable()  # type: List[Spendable]
            utxos.append(spendables[vout])
            logging.debug("Retrieved utxo: %s", spendables[vout])
        return utxos

    def _get_spend_value(self, this_tx: Tx) -> int:
        """
        Finds the value of the txout in the given Tx object that is
            associated with our spend.

        :param this_tx: A Tx object given from our transaction history
        :returns: The coin value associated with our spend output.
        """
        change_addrs = \
            self.get_all_known_addresses(change=True)  # type: List[str]
        chg_vout = None  # type: int
        for i, txout in enumerate(this_tx.txs_out):
            address = txout.address(netcode=self.chain.netcode)  # type: str
            if address in change_addrs:
                chg_vout = i
        spend_vout = 0 if chg_vout == 1 else 1  # type: int
        return this_tx.txs_out[spend_vout].coin_value

    async def _process_history(self,
                               history: Tx,
                               address: str,
                               height: int) -> History:
        """
        Coroutine. Creates a _History namedtuple from a given Tx object.

        :param history: A Tx object given from our transaction history
        :param address: The address of ours that is associated with the
            given transaction
        :returns: A new _History namedtuple for our history
        """
        value = None  # type: int
        is_spend = False  # type: bool
        for txout in history.txs_out:
            if txout.address(netcode=self.chain.netcode) == address:
                value = txout.coin_value
        if not value:
            is_spend = True
            value = self._get_spend_value(history)

        decimal_value = Decimal(str(value)) / Wallet.COIN  # type: Decimal
        history_obj = History(tx_obj=history,
                              is_spend=is_spend,
                              value=decimal_value,
                              height=height)  # type: History
        await history_obj.get_timestamp(self.connection)
        logging.debug("Processed history object: %s", history_obj)
        return history_obj

    def _interpret_history(self,
                           histories: List[Dict],
                           change: bool = False) -> bool:
        """
        Populates the wallet's data structures based on a list of tx histories.
        Should only be called by discover_keys(),

        :param histories: a list of tx histories from the server
        :param change: a boolean indicating which key index list to use
        :returns: A boolean that is true if all given histories were empty
        """
        indicies = self.change_indicies if change \
            else self.spend_indicies  # type: List[bool]
        is_empty = True  # type: bool
        # Each iteration represents one key index
        for history in histories:
            if history:
                # Get key/address for current index
                key = self.get_key(len(indicies), change)  # type: SegwitBIP32Node
                address = self.get_address(key)  # type: str
                # Reassign historic info for this index
                txids = [tx["tx_hash"] for tx in history]  # type: List[str]
                heights = [tx["height"] for tx in history]  # type: List[int]

                # Get Tx objects
                this_history = self.loop.run_until_complete(
                    self._get_history(txids))  # type: List[Tx]

                # Process all Txs into our History objects
                futures = list()  # type: List[Awaitable[History]]
                for i, hist in enumerate(this_history):
                    futures.append(self._process_history(
                        hist, address, heights[i]))
                processed_history = self.loop.run_until_complete(
                    asyncio.gather(*futures, loop=self.loop))  # type: List[History]

                # Delete Txs that are just recieving change
                if change:
                    del_indexes = list()  # type: List[int]
                    for i, hist in enumerate(processed_history):
                        if not hist.is_spend:
                            del_indexes.append(i)
                    processed_history = [hist for i, hist
                                         in enumerate(processed_history)
                                         if i not in del_indexes]
                if processed_history:
                    self.history[address] = processed_history

                # Adjust our balances for this index
                t = self.loop.run_until_complete(self._get_balance(
                    address))  # type: Tuple[Decimal, Decimal]
                confirmed, zeroconf = t
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

    async def _interpret_new_history(self,
                                     address: str,
                                     history: Dict[str, Any]) -> bool:
        """
        Coroutine, Populates the wallet's data structures based on a new
        new tx history. Should only be called by _dispatch_result(),

        :param address: the address associated with this new tx history
        :param history: a history message from the server
        :param change: a boolean indicating which key index list to use
        :returns: A boolean that is true if all given histories were empty
        """
        is_empty = True  # type: bool
        if history:
            spend_addrs = self.get_all_known_addresses()
            # Reassign historic info for new history
            txid = history["tx_hash"]  # type: str
            height = history["height"]  # type: int

            # Get Tx object and process into our History object
            tx_list = await self._get_history([txid])  # type: List[Tx]
            new_history = await self._process_history(
                tx_list.pop(), address, height)  # type: History

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
            new_utxos = await self._get_utxos(address)  # type: List[Spendable]
            for utxo in new_utxos:
                if str(utxo) not in [str(spent) for spent in self.spent_utxos]:
                    self.utxos.append(utxo)

            # If address is found to belong to a spend index, mark it as used
            for i in range(len(self.spend_indicies)):
                key = self.get_key(i, change=False)  # type: SegwitBIP32Node
                if self.get_address(key) == address:
                    self.spend_indicies[i] = True
                    break
            is_empty = False
        return is_empty

    def _discover_keys(self, change: bool = False) -> None:
        """
        Iterates through key indicies (_GAP_LIMIT) at a time and retrieves tx
        histories from the server, then populates our data structures using
        _interpret_history, Should be called once for each key root.

        :param change: a boolean indicating which key index list to use
        """
        logging.info("Discovering transaction history. change=%s", change)
        current_index = 0  # type: int
        quit_flag = False  # type: bool
        while not quit_flag:
            futures = list()  # type: List[Awaitable]
            for i in range(current_index, current_index + Wallet._GAP_LIMIT):
                addr = self.get_address(self.get_key(i, change)) # type: str
                futures.append(self.connection.listen_rpc(
                    self.methods["get_history"], [addr]))

            result = self.loop.run_until_complete(
                asyncio.gather(*futures, loop=self.loop))  # type: List[Dict[str, Any]]
            quit_flag = self._interpret_history(result, change)
            current_index += Wallet._GAP_LIMIT
        self.new_history = True

    @log_time_elapsed
    def discover_all_keys(self) -> None:
        """
        Calls discover_keys for change and spend keys.
        """
        logging.info("Begin discovering tx history...")
        for change in (False, True):
            self._discover_keys(change=change)

    async def listen_to_addresses(self) -> None:
        """
        Coroutine, adds all known addresses to the subscription queue, and
        begins consuming the queue so we can recieve new tx histories from
        the server asynchronously.
        """
        addrs = self.get_all_known_addresses()  # type: List[str]
        for addr in addrs:
            self.connection.listen_subscribe(self.methods["subscribe"], [addr])
        logging.debug("Listening for updates involving any known address...")
        await self.connection.consume_queue(self._dispatch_result)

    async def _dispatch_result(self, result: List[str]) -> None:
        """
        Gets called by the Connection's consume_queue method when a new tx
        history is sent from the server, then populates data structures using
        _interpret_new_history.

        :param result: an address that has some new tx history
        """
        addr = result[0]  # type: str
        logging.debug("Dispatched a new history for address %s", addr)
        history = await self.connection.listen_rpc(
            self.methods["get_history"], [addr])  # type: List[Dict[str, Any]]
        empty_flag = await self._interpret_new_history(
            addr, history[0])  # type: bool
        if not empty_flag:
            self.new_history = True

    @staticmethod
    def _calculate_vsize(tx: Tx) -> int:
        """
        Calculates the virtual size of tx in bytes.

        :param tx: a Tx object that we need to get the vsize for
        :returns: An int representing the vsize of the given Tx
        """
        def _total_size(tx: Tx) -> int:
            ins = len(tx.txs_in)  # type: int
            outs = len(tx.txs_out)  # type: int
            return (ins * 180 + outs * 34) + (10 + ins)
        def _base_size(tx: Tx) -> int:
            buffer = io.BytesIO()  # type: io.BytesIO
            tx.stream(buffer)
            return len(buffer.getvalue())

        weight = 3 * _base_size(tx) + _total_size(tx)  # type: int
        return weight // 4

    @staticmethod
    def satb_to_coinkb(satb: int) -> float:
        """
        Converts a fee rate from satoshis per byte to coins per KB.

        :param satb: An int representing a fee rate in satoshis per byte
        :returns: A float representing the rate in coins per KB
        """
        return (satb * 1000) / Wallet.COIN

    @staticmethod
    def coinkb_to_satb(coinkb: float) -> int:
        """
        Converts a fee rate from coins per KB to satoshis per byte.

        :param coinkb: A float representing a fee rate in coins per KB
        :returns: An int representing the rate in satoshis per byte
        """
        return int((coinkb / 1000) * Wallet.COIN)

    def get_fee_estimation(self):
        """
        Gets a fee estimate from the server.

        :returns: A float representing the appropriate fee in coins per KB
        :raise: Raises a base Exception when the server returns -1
        """
        coin_per_kb = self.loop.run_until_complete(self.connection.listen_rpc(
            self.methods["estimatefee"], [6]))  # type: float
        if coin_per_kb < 0:
            raise Exception("Cannot get a fee estimate")
        logging.info("Fee estimate from server is %f %s/KB",
                     coin_per_kb, self.chain.chain_1209k.upper())
        return coin_per_kb

    @staticmethod
    def _get_fee(tx, coin_per_kb: float) -> Tuple[int, int]:
        """
        Calculates the size of tx based on a given estimate from the server.

        :param tx: a Tx object that we need to estimate a fee for
        :param coin_per_kb: Fee estimation in whole coins per KB
        :returns: An int representing the appropriate fee in satoshis
        :raise: Raises a ValueError if given fee rate is over 1000 satoshi/B
        """
        if coin_per_kb > Wallet.satb_to_coinkb(2000):
            raise ValueError("Given fee rate is extraordinarily high.")
        tx_vsize = Wallet._calculate_vsize(tx)  # type: int
        tx_kb_count = tx_vsize / 1000  # type: float
        fee = int((tx_kb_count * coin_per_kb) * Wallet.COIN)  # type: int

        # Make sure our fee is at least the default minrelayfee
        # https://bitcoin.org/en/developer-guide#transaction-fees-and-change
        MINRELAYFEE = 1000  # type: int
        if fee < MINRELAYFEE:
            fee = MINRELAYFEE
        return fee, tx_vsize


    def _mktx(self,
              out_addr: str,
              dec_amount: Decimal,
              rbf: bool = False) -> Tuple[Tx, Set[str], int]:
        """
        Builds a standard Bitcoin transaction - in the most naive way.
        Coin selection is basically random. Uses one output and one change
        address. Takes advantage of our subclasses to implement BIP69.

        :param out_addr: an address to send to
        :param amount: a Decimal amount in whole BTC
        :param rbf: A boolean that says whether to mark Tx as replaceable
        :returns: A not-fully-formed and unsigned Tx object
        """
        amount = int(dec_amount * Wallet.COIN)  # type: int
        fee_highball = 100000  # type: int
        total_out = 0  # type: int

        spendables = list()  # type: List[LexSpendable]
        in_addrs = set()  # type: Set[str]
        del_indexes = list()  # type: List[int]

        # Collect enough utxos for this spend
        # Add them to spent list and delete them from utxo list
        for i, utxo in enumerate(self.utxos):
            if total_out < amount + fee_highball:
                self.spent_utxos.append(utxo)
                spendables.append(LexSpendable.promote(utxo))
                in_addrs.add(utxo.address(self.chain.netcode))
                del_indexes.append(i)
                total_out += utxo.coin_value
        self.utxos = [utxo for i, utxo in enumerate(self.utxos)
                      if i not in del_indexes]

        # Get change address, mark index as used, and create payables list
        change_key = self.get_next_unused_key(
            change=True, using=True)  # type: SegwitBIP32Node
        change_addr = self.get_address(change_key, addr=True)  # type: str
        payables = list()  # type: List[Tuple[str, int]]
        payables.append((out_addr, amount))
        payables.append((change_addr, 0))

        tx = Wallet._create_bip69_tx(spendables, payables, rbf)  # type: Tx

        # Search for change output index after lex sort
        chg_vout = None  # type: int
        for i, txout in enumerate(tx.txs_out):
            if txout.address(self.chain.netcode) == change_addr:
                chg_vout = i
                break

        # Create pycoin Tx object from inputs/outputs
        return tx, in_addrs, chg_vout

    @staticmethod
    def _create_bip69_tx(spendables: List[LexSpendable],
                         payables: List[Tuple[str, int]],
                         rbf: bool,
                         version: int = 1) -> Tx:
        spendables.sort()

        # Create input list from utxos
        # Set sequence numbers to zero if using RBF.
        txs_in = [spendable.tx_in()
                  for spendable in spendables]  # type: List[TxIn]
        if rbf:
            logging.info("Spending with opt-in Replace by Fee! (RBF)")
            for txin in txs_in:
                txin.sequence = 0

        # Create output list from payables
        txs_out = list()  # type: List[LexTxOut]
        for payable in payables:
            bitcoin_address, coin_value = payable
            script = standard_tx_out_script(bitcoin_address)  # type: bytes
            txs_out.append(LexTxOut(coin_value, script))
        txs_out.sort()
        txs_out = [LexTxOut.demote(txout)
                   for txout in txs_out]  # type List[TxOut]

        tx = Tx(version=version, txs_in=txs_in, txs_out=txs_out)  # type: Tx
        tx.set_unspents(spendables)
        return tx

    def _signtx(self, unsigned_tx: Tx, in_addrs: Set[str], fee: int) -> None:
        """
        Signs Tx and redistributes outputs to include the miner fee.

        :param unsigned_tx: an unsigned Tx to sign and add fee to
        :param in_addrs: a list of our addresses that have recieved coins
        :param fee: an int representing the desired Tx fee
        """
        redeem_scripts = dict()  # type: Dict[bytes, bytes]
        wifs = list()  # type: List[str]

        # Search our indicies for keys used, given in in_addrs list
        # Populate lists with our privkeys and redeemscripts
        for change in (True, False):
            addresses = self.get_all_known_addresses(change, addr=True)
            for i, addr in enumerate(addresses):
                key = self.get_key(i, change)  # type: SegwitBIP32Node
                if addr in in_addrs:
                    p2aw_script = key.p2wpkh_script()  # type: bytes
                    script_hash = key.p2wpkh_script_hash()  # type: bytes
                    redeem_scripts[script_hash] = p2aw_script
                    wifs.append(key.wif())

        # Include our total fee and sign the Tx
        distribute_from_split_pool(unsigned_tx, fee)
        sign_tx(unsigned_tx, wifs=wifs,
                netcode=self.chain.netcode,
                p2sh_lookup=redeem_scripts)

    def _create_replacement_tx(self,
                               hist_obj: History,
                               version: int = 1) -> Tuple[Tx, Set[str], int]:
        """
        Builds a replacement Bitcoin transaction based on a given History
        object in order to implement opt in Replace-By-Fee.

        :param hist_obj: a History object from our tx history data
        :param version: an int representing the Tx version
        :returns: A not-fully-formed and unsigned replacement Tx object
        :raise: Raises a ValueError if tx not a spend or is already confirmed
        """
        if hist_obj.height == 0 and hist_obj.is_spend:
            old_tx = hist_obj.tx_obj  # type: Tx
            spendables = old_tx.unspents  # type: List[Spendable]
            chg_vout = None  # type: int

            in_addrs = set()  # type: Set[str]
            for utxo in spendables:
                in_addrs.add(utxo.address(self.chain.netcode))

            txs_out = list()  # type: List[TxOut]
            for i, txout in enumerate(old_tx.txs_out):
                value = None  # type: int
                if txout.coin_value / Wallet.COIN == hist_obj.value:
                    value = txout.coin_value
                else:
                    value = 0
                    chg_vout = i
                txs_out.append(TxOut(value, txout.script))

            new_tx = Tx(version=version,
                        txs_in=old_tx.txs_in,
                        txs_out=txs_out)  # type: Tx
            new_tx.set_unspents(spendables)
            return new_tx, in_addrs, chg_vout
        else:
            raise ValueError("This transaction is not replaceable")

    def spend(self,
              address: str,
              amount: Decimal,
              coin_per_kb: float,
              rbf: bool = False) -> Tuple[str, Decimal, int]:
        """
        Gets a new tx from _mktx() and sends it to the server to be broadcast,
        then inserts the new tx into our tx history and includes our change
        utxo, which is currently assumed to be the last output in the Tx.

        :param address: an address to send to
        :param amount: a Decimal amount in whole BTC
        :param coin_per_kb: a fee rate given in whole coins per KB
        :param rbf: a boolean saying whether to mark the tx as replaceable
        :returns: The txid of our new tx, given after a successful broadcast
        :raise: Raises a base Exception if we can't afford the fee
        """
        t = self._mktx(address, amount, rbf=rbf)  # type: Tuple[Tx, Set[str], int]
        tx, in_addrs, chg_vout = t
        t = self._get_fee(tx, coin_per_kb)  # type: Tuple[int, int]
        fee, tx_vsize = t

        decimal_fee = Decimal(str(fee)) / Wallet.COIN  # type: Decimal
        if not amount + decimal_fee <= self.balance:
            raise Exception("Insufficient funds to cover fee")

        self._signtx(tx, in_addrs, fee)
        txid = self.loop.run_until_complete(self.connection.listen_rpc(
            self.methods["broadcast"], [tx.as_hex()]))  # type: str

        change_out = tx.txs_out[chg_vout]  # type: TxOut
        coin_in = Decimal(str(tx.total_in())) / Wallet.COIN  # type: Decimal
        change = Decimal(str(change_out.coin_value)) / Wallet.COIN  # type: Decimal

        self.balance -= coin_in
        self.zeroconf_balance += change
        self.new_history = True

        change_address = change_out.address(
            netcode=self.chain.netcode)  # type:str
        self.connection.listen_subscribe(
            self.methods["subscribe"], [change_address])
        return txid, decimal_fee, tx_vsize

    def replace_by_fee(self, hist_obj: History, coin_per_kb: float) -> str:
        """
        Gets a replacement tx from _create_replacement_tx() and sends it to
        the server to be broadcast, then replaces the tx in our tx history and
        subtracts the difference in fees from our balance.

        :param hist_obj: a History object from our tx history data
        :param coin_per_kb: a new fee rate given in whole coins per KB
        :returns: The txid of our new tx, given after a successful broadcast
        """
        t = self._create_replacement_tx(hist_obj)  # type: Tuple[Tx, Set[str], int]
        tx, in_addrs = t[:2]
        new_fee = self._get_fee(tx, coin_per_kb)  # type: int

        self._signtx(tx, in_addrs, new_fee)
        txid = self.loop.run_until_complete(self.connection.listen_rpc(
            self.methods["broadcast"], [tx.as_hex()]))  # type: str

        fee_diff = new_fee - hist_obj.tx_obj.fee()  # type: int
        self.balance -= fee_diff
        hist_obj.tx_obj = tx
        return txid

    def __str__(self) -> str:
        """
        Special method __str__()

        :returns: The string representation of this wallet object
        """
        pprinter = pprint.PrettyPrinter(indent=4)  # type: pprint.PrettyPrinter
        str_ = list()  # type: List[str]
        str_.append("\nYPUB: {}".format(self.ypub))
        str_.append("\nHistory:\n{}".format(
            pprinter.pformat(self.get_tx_history())))
        str_.append("\nUTXOS:\n{}".format(
            pprinter.pformat(self.utxos)))
        str_.append("\nBalance: {} ({} unconfirmed) {}".format(
            float(self.balance), float(self.zeroconf_balance),
            self.chain.chain_1209k.upper()))
        str_.append("\nYour current address: {}".format(
            self.get_address(self.get_next_unused_key(), addr=True)))
        return "".join(str_)

def get_random_onion(loop: asyncio.AbstractEventLoop,
                     chain) -> Tuple[str, int, str]:
    """
    Grabs a random onion server from a list that it gets from our
    scrape_onion_servers function.

    :param chain: Our current chain info
    :returns: A server info tuple for a random .onion Electrum server
    :raise: Raises s base Exception if there are no servers up on 1209k
    """
    servers = loop.run_until_complete(scrape_onion_servers(
        chain_1209k=chain.chain_1209k))  # type: List[Tuple[str, int]]
    if not servers:
        raise Exception("No electrum servers found!")
    return random.choice(servers)

def get_payable_from_BIP21URI(uri: str,
                              proto: str="bitcoin") -> Tuple[str, Decimal]:
    """
    Computes a 'payable' tuple from a given BIP21 encoded URI.

    :param uri: The BIP21 URI to decode
    :param proto: The expected protocol/scheme (case insensitive)
    :returns: A payable (address, amount) corresponding to the given URI
    :raise: Raises s ValueError if there is no address given or if the
        protocol/scheme doesn't match what is expected
    """
    obj = parse.urlparse(uri)  # type: parse.ParseResult
    if not obj.path or obj.scheme.upper() != proto.upper():
        raise ValueError("Malformed URI")
    if not obj.query:
        return obj.path, None
    query = parse.parse_qs(obj.query)  # type: Dict
    return obj.path, Decimal(query["amount"][0])
