import logging
import sys
import os
FORMAT = "%(asctime)s %(levelname)s: %(message)s"  # type: str

stdout_hdlr = logging.StreamHandler(sys.stdout)  # type: logging.StreamHandler
stdout_hdlr.setFormatter(logging.Formatter(FORMAT))
stdout_hdlr.setLevel(
    logging.ERROR if os.environ.get("NW_LOG") == "ERR" else logging.INFO)

file_hdlr = logging.FileHandler(
    filename="nowallet.log", mode="w")  # type: logging.FileHandler
file_hdlr.setFormatter(logging.Formatter(FORMAT))
file_hdlr.setLevel(logging.DEBUG)

logging.basicConfig(level=logging.DEBUG, handlers=[stdout_hdlr, file_hdlr])

import asyncio
import io
import random
import collections
import pprint
import time
import json
from decimal import Decimal
from functools import wraps
from urllib import parse
from typing import (
    Tuple, List, Set, Dict, KeysView, Any,
    Union, Callable, Awaitable
)

from pycoin.serialize import b2h
from pycoin.ui import standard_tx_out_script
from pycoin.tx.tx_utils import distribute_from_split_pool, sign_tx
from pycoin.tx.Tx import Tx
from pycoin.tx.TxIn import TxIn
from pycoin.tx.TxOut import TxOut
from pycoin.tx.Spendable import Spendable
from connectrum.client import StratumClient
from connectrum.svr_info import ServerInfo

from .bip49 import SegwitBIP32Node
from .keys import derive_key
from .socks_http import urlopen

from connectrum import ElectrumErrorResponse

class Connection:
    """ Connection object. Connects to an Electrum server, and handles all
    Stratum protocol messages.
    """

    #  pylint: disable=E1111
    def __init__(self,
                 loop: asyncio.AbstractEventLoop,
                 server: str,
                 port: int,
                 proto: str) -> None:
        """ Connection object constructor.

        :param loop: an asyncio event loop
        :param server: a string containing a hostname
        :param port: port number that the server listens on
        :returns: A new Connection object
        """
        logging.info("Connecting...")

        self.server_info = ServerInfo(
            server, hostname=server, ports=port)  # type: ServerInfo

        logging.info(str(self.server_info.get_port(proto)))

        self.client = StratumClient(loop)  # type: StratumClient
        self.connection = self.client.connect(
                self.server_info,
                proto_code=proto,
                use_tor=True,
                disable_cert_verify=(proto != "s")
            )  # type: asyncio.Future

        self.queue = None  # type: asyncio.Queue

    async def do_connect(self) -> None:
        """ Coroutine. Establishes a persistent connection to an Electrum server.
        Awaits the connection because AFAIK an init method can't be async.
        """
        await self.connection
        logging.info("Connected to server")

    async def listen_rpc(self, method: str, args: List) -> Any:
        """ Coroutine. Sends a normal RPC message to the server and awaits response.

        :param method: The Electrum API method to use
        :param args: Params associated with current method
        :returns: Future. Response from server for this method(args)
        """
        #return await self.client.RPC(method, *args)
        return await self.client.RPC(method, *args)

    def listen_subscribe(self, method: str, args: List) -> None:
        """ Sends a "subscribe" message to the server and adds to the queue.
        Throws away the immediate future containing the "history" hash.

        :param method: The Electrum API method to use
        :param args: Params associated with current method
        """
        t = self.client.subscribe(
            method, *args
        )  # type: Tuple[asyncio.Future, asyncio.Queue]
        future, queue = t

        self.queue = queue
        return future

    async def consume_queue(self, queue_func: Callable[[List[str]], Awaitable[None]]) -> None:
        """ Coroutine. Infinite loop that consumes the current subscription queue.
        :param queue_func: A function to call when new responses arrive
        """
        while True:
            logging.info("Awaiting queue..")
            result = await self.queue.get()  # type: List[str]
            await queue_func(result)


class History:
    """ History object. Holds data relevant to a piece of
    our transaction history.
    """

    def __init__(self, tx_obj: Tx, is_spend: bool, value: Decimal, height: int) -> None:
        """ History object constructor.

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
        """ Coroutine. Gets the timestamp for this Tx based on the given height.
        :param connection: a Connection object for getting a block header
            from the server
        """
        if self.height > 0:
            try:
                block_header = await connection.listen_rpc(
                    Wallet.methods["get_header"],
                    [self.height]
                )  # type: Dict[str, Any]
            except ElectrumErrorResponse as e:
                print(e)
                return

            block_time = block_header["timestamp"]
            self.timestamp = block_time

            logging.debug("Got timestamp %d from block at height %s",
                          self.height, self.timestamp)
        else:
            self.timestamp = int(time.time())

    def as_dict(self) -> Dict[str, Any]:
        """ Transforms this History object into a dictionary.
        :returns: A dictionary representation of this History object
        """
        return {
            "txid": self.tx_obj.id(),
            "is_spend": self.is_spend,
            "value": str(self.value),
            "height": self.height,
            "timestamp": self.timestamp
        }

    def __str__(self) -> str:
        """ Special method __str__()
        :returns: The string representation of this History object
        """
        return (
            "<History: TXID:{} is_spend:{} " +
            "value:{} height:{} timestamp:{}>"
        ).format(self.tx_obj.id(), self.is_spend,
                 self.value, self.height, time.asctime(time.localtime(self.timestamp)))

    def __repr__(self) -> str:
        return str(self)

    def __hash__(self) -> int:
        return hash(self.tx_obj.id())

    def __eq__(self, other) -> bool:
        return self.tx_obj.id() == other.tx_obj.id()


Chain = collections.namedtuple("Chain", ["netcode", "chain_1209k", "bip44"])
BTC = Chain(netcode="BTC", chain_1209k="btc", bip44=0)
TBTC = Chain(netcode="XTN", chain_1209k="tbtc", bip44=1)
LTC = Chain(netcode="LTC", chain_1209k="ltc", bip44=2)
VTC = Chain(netcode="VTC", chain_1209k="vtc", bip44=28)


def log_time_elapsed(func: Callable) -> Callable:
    """ Decorator. Times completion of function and logs at level INFO. """

    @wraps(func)
    def inner(*args, **kwargs) -> None:
        """ Decorator inner function. """
        start_time = time.time()  # type: float
        func(*args, **kwargs)
        end_time = time.time()  # type: float
        seconds = end_time - start_time  # type: float
        logging.info("Operation completed in {0:.3f} seconds".format(seconds))

    return inner


class Wallet:
    """ Provides all functionality required for a fully functional and secure
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
                 chain,
                 bech32=False) -> None:
        """ Wallet object constructor. Use discover_keys() and listen_to_addresses()
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
        def create_root_keys(salt: str, passphrase: str, account: int = 0) -> None:
            """ Derives master key from salt/passphrase and initializes all
            master key attributes.

            :param salt: a string to use as a salt for key derivation
            :param passphrase: a string containing a secure passphrase
            :param account: account number, defaults to 0
            """
            logging.info("Deriving keys...")

            t = derive_key(
                salt, passphrase
            )  # type: Union[int, Tuple[int, bytes]]
            assert isinstance(t, tuple), "Should never fail"
            secret_exp, chain_code = t

            self.mpk = SegwitBIP32Node(
                netcode=self.chain.netcode,
                chain_code=chain_code,
                secret_exponent=secret_exp
            )  # type: SegwitBIP32Node

            bip = 84 if bech32 else 49  # type: int
            path = "{}H/{}H/{}H".format(
                bip, self.chain.bip44, account
            )  # type: str

            self.account_master = \
                self.mpk.subkey_for_path(path)  # type: SegwitBIP32Node
            self.root_spend_key = \
                self.account_master.subkey(0)  # type: SegwitBIP32Node
            self.root_change_key = \
                self.account_master.subkey(1)  # type: SegwitBIP32Node

        self.connection = connection  # type: Connection
        self.loop = loop  # type: asyncio.AbstractEventLoop
        self.chain = chain
        self.bech32 = bech32

        self.mpk = None  # type: SegwitBIP32Node
        self.account_master = None  # type: SegwitBIP32Node
        self.root_spend_key = None  # type: SegwitBIP32Node
        self.root_change_key = None  # type: SegwitBIP32Node
        create_root_keys(salt, passphrase)

        # Boolean lists, True = used / False = unused
        self.spend_indicies = []  # type: List[bool]
        self.change_indicies = []  # type: List[bool]

        # All wallet TX info. (MUST not persist!)
        self.utxos = []  # type: List[Spendable]
        self.spent_utxos = []  # type: List[Spendable]

        self.history = {}  # type: Dict[Any]
        self.change_history = {}  # type: Dict[Any]

        self.balance = Decimal("0")  # type: Decimal
        self.zeroconf_balance = Decimal("0")  # type: Decimal

        self.new_history = False  # type: bool

    @property
    def ypub(self) -> str:
        """ Returns this account's extended public key.
        :returns: a string containing the account's XPUB.
        """
        return self.account_master.hwif()

    def get_key(self, index: int, change: bool) -> SegwitBIP32Node:
        """ Returns a specified pycoin.key object.

        :param index: The index of the desired key
        :param change: a boolean indicating which key root to use
        :returns: a key object associated with the given index
        """
        root_key = self.root_change_key if change else self.root_spend_key  # type: SegwitBIP32Node
        return root_key.subkey(index)

    def get_next_unused_key(self, change: bool = False, using: bool = False) -> SegwitBIP32Node:
        """ Returns the next unused key object in the sequence.

        :param change: a boolean indicating which key root to use
        :param using: a boolean indicating whether to mark key as used now
        :returns: a key object associated with the next unused index
        """
        indicies = self.change_indicies if change else self.spend_indicies  # type: List[bool]
        for i, is_used in enumerate(indicies):
            if not is_used:
                if using:
                    indicies[i] = True
                return self.get_key(i, change)
        return None

    def get_address(self, key: SegwitBIP32Node, addr=False) -> str:
        """ Returns the segwit address for a given key.

        :param key: any given SegwitBIP32Node key
        :returns: A segwit (P2WPKH) address, either P2SH or bech32.
        """
        if not addr:
            return key.electrumx_script_hash(bech32=self.bech32)
        return key.bech32_p2wpkh_address() if self.bech32 else key.p2sh_p2wpkh_address()

    def get_all_known_addresses(self, change: bool = False, addr: bool = False) -> List[str]:
        """ Returns a list of all addresses currently known to us.

        :param change: a boolean indicating which key root to use
        :returns: a list of address strings containing all addresses known
            for the given root
        """
        indicies = self.change_indicies if change else self.spend_indicies  # type: List[bool]
        return [self.get_address(self.get_key(i, change), addr=addr)
                for i in range(len(indicies))]  # type: List[str]

    def get_all_used_addresses(self) -> List[str]:
        """ Returns all addresses that have been used previously.

        :returns: address strings containing all used
            addresses for the given root
        """
        return list(self.history.keys()) + list(self.change_history.keys())

    def search_for_index(self, search, addr=False, change=False) -> int:
        """ Returns the index associated with a given address
        if it is currently known to us, otherwise returns None.

        :param search: the address to search for
        :returns: a key index associated with the given address.
        """
        addresses = self.get_all_known_addresses(change, addr=addr)
        for i, addr in enumerate(addresses):
            if addr == search:
                return i
        return None

    def search_for_key(self, search, addr=True, change=False) -> SegwitBIP32Node:
        """ Returns the key associated with a given address
        if it is currently known to us, otherwise returns None.

        :param search: the address to search for
        :returns: a SegWitBIP32Node associated with the given address.
        """
        index = self.search_for_index(search, addr=addr, change=change)
        if index:
            return self.get_key(index, change)
        return None

    def _update_wallet_balance(self):
        """ Updates main balance numbers in Wallet object,
        by introspection of history dicts.
        """
        balance, zeroconf_balance = Decimal(0), Decimal(0)
        for hist_dict in (self.history, self.change_history):
            balance += sum(
                map(lambda h: h["balance"]["confirmed"], hist_dict.values()))
            zeroconf_balance += sum(
                map(lambda h: h["balance"]["zeroconf"], hist_dict.values()))
        self.balance, self.zeroconf_balance = balance, zeroconf_balance

    def get_tx_history(self) -> List[History]:
        """ Returns a list of all History objects in our non-change history,
        ordered by height/timestamp.

        :returns: an ordered list of History objects.
        """
        history = []  # type: List[History]
        for value in self.history.values():
            history.extend(value["txns"])
        for value in self.change_history.values():
            history.extend(filter(lambda t: t.is_spend, value["txns"]))
        history = list(set(history))  # Dedupe
        history.sort(reverse=True, key=lambda h: h.timestamp)
        return history

    async def _get_history(self, txids: List[str]) -> List[Tx]:
        """ Coroutine. Returns a list of pycoin.tx.Tx objects
        associated with the given txids.

        :param txids: a list of txid strings to retrieve tx histories for
        :returns: Future, a list of Tx objects
        """
        futures = [self.connection.listen_rpc(
            self.methods["get"], [txid]) for txid in txids]  # type: str
#        results = await asyncio.gather(*futures, loop=self.loop)
        results = await asyncio.gather(*futures)
        txs = [Tx.from_hex(tx_hex) for tx_hex in results]  # type: List[Tx]
        logging.debug("Retrieved Txs: %s", txs)
        return txs

    async def _get_balance(self, address: str) -> Tuple[Decimal, Decimal]:
        """ Coroutine. Returns the current balance associated with a given address.

        :param address: an address string to retrieve a balance for
        :returns: Future, a tuple of Decimals representing the balances.
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
        """ Coroutine. Returns a list of pycoin.tx.Spendable objects for all
        UTXOS associated with the given address

        :param address: an address string to retrieve a balance for
        :returns: Future, a list of pycoin Spendable objects.
        """
        logging.debug("Retrieving utxos for address %s", address)

        result = await self.connection.listen_rpc(
            self.methods["listunspent"], [address])  # type: Dict
        pos_map = {unspent["tx_hash"]: unspent["tx_pos"]
                   for unspent in result}  # type: Dict[str, int]
        futures = [self.connection.listen_rpc(self.methods["get"], [unspent["tx_hash"]])
                   for unspent in result]  # type: List[asyncio.Future]
#         txs = await asyncio.gather(*futures, loop=self.loop)  # type: List[str]
        txs = await asyncio.gather(*futures)  # type: List[str]
        utxos = []  # type: List[Spendable]
        for tx_hex in txs:
            tx = Tx.from_hex(tx_hex)  # type: Tx
            vout = pos_map[tx.id()]  # type: int
            spendable = tx.tx_outs_as_spendable()[vout]  # type: Spendable
            utxos.append(spendable)
            logging.debug("Retrieved utxo: %s", spendable)
        return utxos

    def _get_spend_value(self, tx: Tx) -> int:
        """ Finds the value of the txout in the given Tx object that is
        associated with our spend.

        :param tx: A Tx object given from our transaction history
        :returns: The coin value associated with our spend output.
        """
        change_addrs = \
            self.get_all_known_addresses(change=True)  # type: List[str]
        chg_vout = None  # type: int
        for i, txout in enumerate(tx.txs_out):
            address = txout.address(netcode=self.chain.netcode)  # type: str
            if address in change_addrs:
                chg_vout = i
        # spend_vout = 0 if chg_vout == 1 else 1  # type: int
        # for debugging purposes
        spend_vout = 1 if chg_vout == 1 else 0 # type: int
        return tx.txs_out[spend_vout].coin_value

    async def _process_history(self, history: Tx, address: str, height: int) -> History:
        """ Coroutine. Creates a _History namedtuple from a given Tx object.

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

    async def _interpret_history(self, statuses: List[str], change: bool = False) -> bool:
        """ Populates the wallet's data structures based on a list of tx histories.
        Should only be called by discover_keys(),

        :param statuses: a list of address statuses from the server
        :param change: a boolean indicating which key index list to use
        :returns: A boolean that is true if all given histories were empty
        """
        indicies = self.change_indicies if change else self.spend_indicies  # type: List[bool]
        history_dict = self.change_history if change \
            else self.history  # type: Dict[Any]

        is_empty = True  # type: bool
        # Each iteration represents one key index
        for status in statuses:
            if not status:
                # Mark this index as unused
                indicies.append(False)
                continue

            index = len(indicies)
            # Get key/address for current index
            key = self.get_key(index, change)  # type: SegwitBIP32Node
            scripthash = self.get_address(key)  # type: str
            address = self.get_address(key, addr=True)  # type: str

            history = await self.connection.listen_rpc(
                    self.methods["get_history"], [scripthash])  # type: List[Any]

            # Reassign historic info for this index
            txids = [tx["tx_hash"] for tx in history]  # type: List[str]
            heights = [tx["height"] for tx in history]  # type: List[int]

            # Get Tx objects
            this_history = await self._get_history(txids)  # type: List[Tx]

            # Process all Txs into our History objects
            futures = [self._process_history(hist, address, heights[i])
                       for i, hist in enumerate(this_history)]  # type: List[Awaitable[History]]
            
            processed_history = await asyncio.gather(
#                 *futures, loop=self.loop)  # type: List[History]
                *futures)  # type: List[History]

            if processed_history:
                # Get balance information
                t = await self._get_balance(scripthash)  # type: Tuple[Decimal, Decimal]
                confirmed, zeroconf = t

                history_dict[index] = {
                    "balance": {
                        "confirmed": confirmed,
                        "zeroconf": zeroconf
                    },
                    "txns": processed_history
                }

            # Add utxos to our list
            self.utxos.extend(await self._get_utxos(scripthash))

            # Mark this index as used since it has a history
            indicies.append(True)
            is_empty = False

        # Adjust our balances
        self._update_wallet_balance()

        return is_empty

    async def _interpret_new_history(self, scripthash: str, history: Dict[str, Any]) -> bool:
        """ Coroutine, Populates the wallet's data structures based on a new
        new tx history. Should only be called by _dispatch_result(),

        :param address: the address associated with this new tx history
        :param history: a history message from the server
        :param change: a boolean indicating which key index list to use
        :returns: A boolean that is true if all given histories were empty
        """
        change = False  # type: bool
        is_empty = True  # type: bool

        if history:
            logging.info("Interpreting new history..")
            index = self.search_for_index(scripthash)  # type: int
            if index is None:
                change = True
                index = self.search_for_index(scripthash, change=change)
                assert index is not None, "Recieving to unknown address. CRITICAL ERROR"
            address = self.get_address(self.get_key(index, change), addr=True)

            logging.info("New history is for address: {}".format(address))
            logging.info("New history is for change: {}".format(change))

            indicies = self.change_indicies if change \
                else self.spend_indicies  # type: List[int]
            hist_dict = self.change_history if change \
                else self.history  # type: Dict[str, Any]
            address = self.get_address(
                self.get_key(index, change), addr=True)  # type: str

            # Reassign historic info for new history
            txid = history["tx_hash"]  # type: str
            height = history["height"]  # type: int

            # Get Tx object and process into our History object
            tx_list = await self._get_history([txid])  # type: List[Tx]
            new_history = await self._process_history(
                tx_list.pop(), address, height)  # type: History

            # Add History object to our history dict
            if index in hist_dict:
                hist_list = hist_dict[index]["txns"]
                did_match = False
                for i, hist in enumerate(hist_list):
                    if str(new_history.tx_obj) == str(hist.tx_obj):
                        hist_list[i] = new_history
                        did_match = True
                if not did_match:
                    hist_list.append(new_history)
            else:
                hist_dict[index] = {
                    "balance": {
                        "confirmed": None,
                        "zeroconf": None
                    },
                    "txns": [new_history]
                }

            # Get/update balance for this index, then for the wallet
            conf, zconf = await self._get_balance(scripthash)
            current_balance = hist_dict[index]["balance"]
            current_balance["confirmed"] = conf
            current_balance["zeroconf"] = zconf
            self._update_wallet_balance()

            # Add new utxo to our list if not already spent
            # type: List[Spendable]
            new_utxos = await self._get_utxos(scripthash)
            spents_str = [str(spent) for spent in self.spent_utxos]
            for utxo in new_utxos:
                if str(utxo) not in spents_str:
                    self.utxos.append(utxo)

            # Mark this index as used
            indicies[index] = True

            is_empty = False
        return is_empty

    async def _discover_keys(self, change: bool = False) -> None:
        """ Iterates through key indicies (_GAP_LIMIT) at a time and retrieves tx
        histories from the server, then populates our data structures using
        _interpret_history, Should be called once for each key root.

        :param change: a boolean indicating which key index list to use
        """
        logging.info("Discovering transaction history. change=%s", change)
        current_index = 0  # type: int
        quit_flag = False  # type: bool
        while not quit_flag:
            futures = []  # type: List[Awaitable]
            for i in range(current_index, current_index + Wallet._GAP_LIMIT):
                addr = self.get_address(self.get_key(i, change))  # type: str
                futures.append(self.connection.listen_subscribe(
                    self.methods["subscribe"], [addr]))

            result = await asyncio.gather(
#                *futures, loop=self.loop)  # type: List[Dict[str, Any]]
                *futures) # type: List[Dict[str, Any]]
            quit_flag = await self._interpret_history(result, change)
            current_index += Wallet._GAP_LIMIT
        self.new_history = True

    # @log_time_elapsed  TODO: Figure out how to use a decorator on a coroutine method
    async def discover_all_keys(self) -> None:
        """ Calls discover_keys for change and spend keys. """
        logging.info("Begin discovering tx history...")
        for change in (False, True):
            await self._discover_keys(change=change)

    async def listen_to_addresses(self) -> None:
        """ Coroutine, adds all known addresses to the subscription queue, and
        begins consuming the queue so we can recieve new tx histories from
        the server asynchronously.
        """
        logging.debug("Listening for updates involving any known address...")
        await self.connection.consume_queue(self._dispatch_result)

    async def _dispatch_result(self, result: List[str]) -> None:
        """ Gets called by the Connection's consume_queue method when a new tx
        history is sent from the server, then populates data structures using
        _interpret_new_history().

        :param result: an address that has some new tx history
        """
        addr = result[0]  # type: str
        history = await self.connection.listen_rpc(
            self.methods["get_history"], [addr])  # type: List[Dict[str, Any]]
        for tx in history:
            empty_flag = await self._interpret_new_history(
                addr, tx)  # type: bool
            if not empty_flag:
                self.new_history = True
                logging.info("Dispatched a new history for address %s", addr)

    @staticmethod
    def _calculate_vsize(tx: Tx) -> int:
        """ Calculates the virtual size of tx in bytes.

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
        """ Converts a fee rate from satoshis per byte to coins per KB.

        :param satb: An int representing a fee rate in satoshis per byte
        :returns: A float representing the rate in coins per KB
        """
        return (satb * 1000) / Wallet.COIN

    @staticmethod
    def coinkb_to_satb(coinkb: float) -> int:
        """ Converts a fee rate from coins per KB to satoshis per byte.

        :param coinkb: A float representing a fee rate in coins per KB
        :returns: An int representing the rate in satoshis per byte
        """
        return int((coinkb / 1000) * Wallet.COIN)

    async def get_fee_estimation(self):
        """ Gets a fee estimate from the server.

        :returns: A float representing the appropriate fee in coins per KB
        :raise: Raises a base Exception when the server returns -1
        """
        coin_per_kb = await self.connection.listen_rpc(
            self.methods["estimatefee"], [6])  # type: float
        if coin_per_kb < 0:
            raise Exception("Cannot get a fee estimate")
        logging.info("Fee estimate from server is %f %s/KB",
                     coin_per_kb, self.chain.chain_1209k.upper())
        return coin_per_kb

    @staticmethod
    def _get_fee(tx, coin_per_kb: float) -> Tuple[int, int]:
        """ Calculates the size of tx based on a given estimate from the server.

        :param tx: a Tx object that we need to estimate a fee for
        :param coin_per_kb: Fee estimation in whole coins per KB
        :returns: An Tuple with two ints representing the appropriate fee
            in satoshis, and the tx's virtual size
        :raise: Raises a ValueError if given fee rate is over 1000 satoshi/B
        """
        if coin_per_kb > Wallet.satb_to_coinkb(2000):
            raise ValueError("Given fee rate is extraordinarily high.")
        tx_vsize = Wallet._calculate_vsize(tx)  # type: int
        tx_kb_count = tx_vsize / 1000  # type: float
        int_fee = int((tx_kb_count * coin_per_kb) * Wallet.COIN)  # type: int

        # Make sure our fee is at least the default minrelayfee
        # https://bitcoin.org/en/developer-guide#transaction-fees-and-change
        MINRELAYFEE = 1000  # type: int
        fee = int_fee if int_fee < MINRELAYFEE else MINRELAYFEE
        return fee, tx_vsize

    def _mktx(self, out_addr: str, dec_amount: Decimal,
              is_high_fee: bool, rbf: bool = False) -> Tuple[Tx, Set[str], int]:
        """ Builds a standard Bitcoin transaction - in the most naive way.
        Coin selection is basically random. Uses one output and one change
        address. Takes advantage of our subclasses to implement BIP69.

        :param out_addr: an address to send to
        :param amount: a Decimal amount in whole BTC
        :param is_high_fee: A boolean which tells whether the current fee rate
            is above a certain threshold
        :param rbf: A boolean that says whether to mark Tx as replaceable
        :returns: A not-fully-formed and unsigned Tx object
        """
        amount = int(dec_amount * Wallet.COIN)  # type: int
        fee_highball = 100000  # type: int
        total_out = 0  # type: int

        spendables = []  # type: List[Spendable]
        in_addrs = set()  # type: Set[str]
        del_indexes = []  # type: List[int]

        # Sort utxos based on current fee rate before coin selection
        self.utxos.sort(key=lambda utxo: utxo.coin_value,
                        reverse=not is_high_fee)

        # Collect enough utxos for this spend
        # Add them to spent list and delete them from utxo list
        for i, utxo in enumerate(self.utxos):
            if total_out < amount + fee_highball:
                self.spent_utxos.append(utxo)
                spendables.append(utxo)
                in_addrs.add(utxo.address(self.chain.netcode))
                del_indexes.append(i)
                total_out += utxo.coin_value
        self.utxos = [utxo for i, utxo in enumerate(self.utxos)
                      if i not in del_indexes]

        # Get change address, mark index as used, and create payables list
        change_key = self.get_next_unused_key(
            change=True, using=True)  # type: SegwitBIP32Node
        change_addr = self.get_address(change_key, addr=True)  # type: str
        payables = []  # type: List[Tuple[str, int]]
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
    def _create_bip69_tx(spendables: List[Spendable], payables: List[Tuple[str, int]],
                         rbf: bool, version: int = 1) -> Tx:
        """ Create tx inputs and outputs from spendables and payables.
        Sort lexicographically and return unsigned Tx object.

        :param spendables: A list of Spendable objects
        :param payables: A list of payable tuples
        :param rbf: Replace by fee flag
        :param version: Tx format version
        :returns: Fully formed but unsigned Tx object
        """
        spendables.sort(key=lambda utxo: (utxo.as_dict()["tx_hash_hex"],
                                          utxo.as_dict()["tx_out_index"]))

        # Create input list from utxos
        # Set sequence numbers to zero if using RBF.
        txs_in = [spendable.tx_in()
                  for spendable in spendables]  # type: List[TxIn]
        if rbf:
            logging.info("Spending with opt-in Replace by Fee! (RBF)")
            for txin in txs_in:
                txin.sequence = 0

        # Create output list from payables
        txs_out = []  # type: List[TxOut]
        for payable in payables:
            bitcoin_address, coin_value = payable
            script = standard_tx_out_script(bitcoin_address)  # type: bytes
            txs_out.append(TxOut(coin_value, script))
        txs_out.sort(key=lambda txo: (txo.coin_value, b2h(txo.script)))

        tx = Tx(version=version, txs_in=txs_in, txs_out=txs_out)  # type: Tx
        tx.set_unspents(spendables)
        return tx

    def _signtx(self, unsigned_tx: Tx, in_addrs: Set[str], fee: int) -> None:
        """ Signs Tx and redistributes outputs to include the miner fee.

        :param unsigned_tx: an unsigned Tx to sign and add fee to
        :param in_addrs: a list of our addresses that have recieved coins
        :param fee: an int representing the desired Tx fee
        """
        redeem_scripts = {}  # type: Dict[bytes, bytes]
        wifs = []  # type: List[str]

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

    def _create_replacement_tx(self, hist_obj: History,
                               version: int = 1) -> Tuple[Tx, Set[str], int]:
        """ Builds a replacement Bitcoin transaction based on a given History
        object in order to implement opt in Replace-By-Fee.

        :param hist_obj: a History object from our tx history data
        :param version: an int representing the Tx version
        :returns: A not-fully-formed and unsigned replacement Tx object,
            a list of addresses used as inputs, and the index of the change output
        :raise: Raises a ValueError if tx not a spend or is already confirmed
        """
        if hist_obj.height == 0 and hist_obj.is_spend:
            old_tx = hist_obj.tx_obj  # type: Tx
            spendables = old_tx.unspents  # type: List[Spendable]
            chg_vout = None  # type: int

            in_addrs = set()  # type: Set[str]
            for utxo in spendables:
                in_addrs.add(utxo.address(self.chain.netcode))

            txs_out = []  # type: List[TxOut]
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

    async def spend(self, address: str, amount: Decimal, coin_per_kb: float,
                    rbf: bool = False, broadcast: bool = True) -> Tuple[Any]:
        """ Gets a new tx from _mktx() and sends it to the server to be broadcast,
        then inserts the new tx into our tx history and includes our change
        utxo, which is currently assumed to be the last output in the Tx.

        :param address: an address to send to
        :param amount: a Decimal amount in whole BTC
        :param coin_per_kb: a fee rate given in whole coins per KB
        :param rbf: a boolean saying whether to mark the tx as replaceable
        :param broadcast: a boolean saying whether to broadcast the tx
        :returns: (The txid of) our new tx, the total fee, and the vsize
        :raise: Raises a base Exception if we can't afford the fee
        """
        is_high_fee = Wallet.coinkb_to_satb(coin_per_kb) > 100

        # type: Tuple[Tx, Set[str], int]
        t1 = self._mktx(address, amount, is_high_fee, rbf=rbf)
        tx, in_addrs, chg_vout = t1
        t2 = self._get_fee(tx, coin_per_kb)  # type: Tuple[int, int]
        fee, tx_vsize = t2

        decimal_fee = Decimal(str(fee)) / Wallet.COIN  # type: Decimal
        total_out = amount + decimal_fee
        if total_out > self.balance:
            raise Exception("Insufficient funds.")

        self._signtx(tx, in_addrs, fee)
        if not broadcast:
            return tx.as_hex(), chg_vout, decimal_fee, tx_vsize

        chg_out = tx.txs_out[chg_vout]  # type: TxOut
        txid = await self.broadcast(tx.as_hex(), chg_out)  # type: str
        return txid, decimal_fee, tx_vsize

    async def broadcast(self, tx_hex: str, chg_out: TxOut) -> str:
        txid = await self.connection.listen_rpc(
            self.methods["broadcast"], [tx_hex])  # type: str

        change_address = chg_out.address(
            netcode=self.chain.netcode)  # type:str
        change_key = self.search_for_key(change_address, change=True)
        scripthash = self.get_address(change_key)

        logging.info("Subscribing to new change address...")
        self.connection.listen_subscribe(
            self.methods["subscribe"], [scripthash])
        logging.info("Finished subscribing to new change address...")
        return txid

    async def replace_by_fee(self, hist_obj: History, coin_per_kb: float) -> str:
        """ Gets a replacement tx from _create_replacement_tx() and sends it to
        the server to be broadcast, then replaces the tx in our tx history and
        subtracts the difference in fees from our balance.

        :param hist_obj: a History object from our tx history data
        :param coin_per_kb: a new fee rate given in whole coins per KB
        :returns: The txid of our new tx, given after a successful broadcast
        """
        t = self._create_replacement_tx(
            hist_obj)  # type: Tuple[Tx, Set[str], int]
        tx, in_addrs = t[:2]
        new_fee = self._get_fee(tx, coin_per_kb)[0]  # type: int

        self._signtx(tx, in_addrs, new_fee)
        txid = await self.connection.listen_rpc(
                self.methods["broadcast"], [tx.as_hex()])  # type: str

        fee_diff = new_fee - hist_obj.tx_obj.fee()  # type: int
        self.balance -= fee_diff
        hist_obj.tx_obj = tx
        return txid

    def __str__(self) -> str:
        """ Special method __str__()
        :returns: The string representation of this wallet object
        """
        pprinter = pprint.PrettyPrinter(indent=4)  # type: pprint.PrettyPrinter
        str_ = []  # type: List[str]
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


async def get_random_server(loop: asyncio.AbstractEventLoop,
                            use_api: bool = False) -> List[Any]:
    """ Grabs a random Electrum server from a list that it
    gets from our REST api.

    :param chain: Our current chain info
    :param use_api: Should we try using the API to get servers?
    :returns: A server info list for a random Electrum server
    :raise: Raises a base Exception if there are no servers up on 1209k
    """
    servers = None
    if use_api:
        logging.info("Fetching server list from REST api.")
        with open("api_password_dev.txt", "r") as infile:
            api_password = infile.read().strip()
        bauth = ("nowallet", api_password)

        result = await urlopen(
            "http://y2yrbptubnrlraml.onion/servers",
            bauth_tuple=bauth, loop=loop
        )  # type: str
        if not result:
            logging.warning("Cannot get data from REST api.")
            result = json.dumps({"servers": []})
        servers = json.loads(result)["servers"]  # type: List[List[Any]]

    if not servers:
        logging.warning("No electrum servers found!")
        servers = load_servers_json()
    return random.choice(servers)


def load_servers_json() -> List[List[Any]]:
    """ Loads a list of Electrum servers from a local json file.
    :returns: A list of server info lists for all default Electrum servers
    """
    logging.info("Reading server list from file..")
    with open("servers.json", "r") as infile:
        return json.load(infile)


def get_payable_from_BIP21URI(uri: str, proto: str = "bitcoin") -> Tuple[str, Decimal]:
    """ Computes a 'payable' tuple from a given BIP21 encoded URI.

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
