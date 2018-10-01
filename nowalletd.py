import sys
import json
import asyncio
import argparse

from decimal import Decimal
from aioconsole import ainput
from aiosocks import SocksConnectionError
from aiohttp.client_exceptions import ClientConnectorError
from pycoin.tx.Tx import Tx

import nowallet

class WalletDaemon:
    def __init__(self, _loop):
        self.loop = _loop
        self.chain = nowallet.TBTC

    async def initialize_wallet(self, _salt, _passphrase, bech32, rbf):
        try:
            server, port, proto = await nowallet.get_random_server(self.loop)
            connection = nowallet.Connection(self.loop, server, port, proto)
            self.wallet = nowallet.Wallet(
                _salt, _passphrase, connection, self.loop, self.chain)
            await connection.do_connect()
        except (SocksConnectionError, ClientConnectorError):
            self.print_json({
                "error": "Make sure Tor is installed and running before using nowalletd."
            })
            sys.exit(1)

        self.wallet.bech32 = bech32
        self.rbf = rbf

        await self.wallet.discover_all_keys()
        self.print_history()
        self.wallet.new_history = False

    def print_json(self, output):
        print(json.dumps(output))

    def print_history(self, last_only=False):
        history = [h.as_dict() for h in self.wallet.get_tx_history()]
        utxos = [u.as_dict() for u in self.wallet.utxos]
        wallet_info = {
            "tx_history": history[-1] if last_only else history,
            "utxos": utxos
        }
        self.print_json({"wallet_info": wallet_info})

    async def input_loop(self):
        while True:
            input_ = await ainput(loop=self.loop)
            if not input_:
                continue
            if input_ == "@end":
                sys.exit(0)
            try:
                obj = json.loads(input_)
            except json.JSONDecodeError as err:
                self.print_json({
                    "error": "{}: {}".format(type(err).__name__, str(err))
                })
                continue
            await self.dispatch_input(obj)

    async def new_history_loop(self):
        while True:
            await asyncio.sleep(1)
            if self.wallet.new_history:
                self.print_history(last_only=True)
                self.wallet.new_history = False

    async def dispatch_input(self, obj):
        type_ = obj.get("type")
        if not type_:
            self.print_json({"error": "Command type was not specified"})
        elif type_ == "get_address":
            self.do_get_address()
        elif type_ == "get_feerate":
            await self.do_get_feerate()
        elif type_ == "get_balance":
            self.do_get_balance()
        elif type_ == "get_ypub":
            self.do_get_ypub()
        elif type_ == "mktx":
            await self.do_mktx(obj)
        elif type_ == "broadcast":
            await self.do_broadcast(obj)
        else:
            self.print_json({"error": "Command type is not supported"})

    def do_get_address(self):
        key = self.wallet.get_next_unused_key()
        address = self.wallet.get_address(key, addr=True)
        self.print_json({"address": address})

    async def do_get_feerate(self):
        feerate = await self.wallet.get_fee_estimation()
        self.print_json({"feerate": feerate})

    def do_get_balance(self):
        balances = {
            "confirmed": str(self.wallet.balance),
            "zeroconf": str(self.wallet.zeroconf_balance)
        }
        self.print_json({"balance": balances})

    def do_get_ypub(self):
        self.print_json({"ypub": self.wallet.ypub})

    async def do_mktx(self, obj):
        address, amount, coin_per_kb = \
            obj.get("address"), Decimal(obj.get("amount")), obj.get("feerate")
        if not address or not amount or not coin_per_kb:
            self.print_json({"error": "Command parameters are not correct"})
            return

        tx_hex, chg_vout, decimal_fee, tx_vsize = \
            await self.wallet.spend(address, amount, coin_per_kb, rbf=self.rbf, broadcast=False)
        tx_info = {
            "tx_hex": tx_hex,
            "vout": chg_vout,
            "fee": str(decimal_fee),
            "vsize": tx_vsize
        }
        self.print_json({"tx_info": tx_info})

    async def do_broadcast(self, obj):
        tx_hex, chg_vout = obj.get("tx_hex"), obj.get("vout")
        if not tx_hex or not chg_vout:
            self.print_json({"error": "Command parameters are not correct"})
            return

        chg_out = Tx.from_hex(tx_hex).txs_out[chg_vout]
        txid = await self.wallet.broadcast(tx_hex, chg_out)
        self.print_json({"txid": txid})

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("salt", help="You must supply a salt to create a wallet.")
    parser.add_argument("passphrase", help="You must supply a passphrase to create a wallet.")
    parser.add_argument("--bech32", help="Create a Bech32 wallet.", action="store_true")
    parser.add_argument("--rbf", help="Mark transactions as replaceable.", action="store_true")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    daemon = WalletDaemon(loop)

    loop.run_until_complete(daemon.initialize_wallet(
        args.salt, args.passphrase, args.bech32, args.rbf))

    tasks = asyncio.gather(
        asyncio.ensure_future(daemon.wallet.listen_to_addresses()),
        asyncio.ensure_future(daemon.input_loop()),
        asyncio.ensure_future(daemon.new_history_loop())
    )

    # Graceful shutdown code borrowed from:
    # https://stackoverflow.com/questions/30765606/
    # whats-the-correct-way-to-clean-up-after-an-interrupted-event-loop
    try:
        # Here `amain(loop)` is the core coroutine that may spawn any
        # number of tasks
        sys.exit(loop.run_until_complete(tasks))

    except KeyboardInterrupt:
        # Optionally show a message if the shutdown may take a while
        print("\nAttempting graceful shutdown, press Ctrl+C again to exit...",
              flush=True)

        # Do not show `asyncio.CancelledError` exceptions during shutdown
        # (a lot of these may be generated, skip this if you prefer to see them)
        def shutdown_exception_handler(_loop, context):
            if "exception" not in context \
                    or not isinstance(context["exception"], asyncio.CancelledError):
                _loop.default_exception_handler(context)
        loop.set_exception_handler(shutdown_exception_handler)

        # Handle shutdown gracefully by waiting for all tasks to be cancelled
        tasks = asyncio.gather(*asyncio.Task.all_tasks(loop=loop),
                               loop=loop, return_exceptions=True)
        tasks.add_done_callback(lambda t: loop.stop())
        tasks.cancel()

        # Keep the event loop running until it is either destroyed or all
        # tasks have really terminated
        while not tasks.done() and not loop.is_closed():
            loop.run_forever()

    finally:
        loop.close()
