import sys
import json
import asyncio
from aioconsole import ainput

import nowallet

class WalletDaemon:
    def __init__(self, _loop, _salt, _passphrase):
        self.loop = _loop

        chain = nowallet.TBTC
        server, port, proto = nowallet.get_random_server(self.loop)
        connection = nowallet.Connection(self.loop, server, port, proto)

        self.wallet = nowallet.Wallet(_salt, _passphrase, connection, self.loop, chain)
        self.wallet.discover_all_keys()

        history = map(lambda h: h.as_dict(), self.wallet.get_tx_history())
        utxos = map(lambda u: u.as_dict(), self.wallet.utxos)
        output = {
            "tx_history": list(history),
            "utxos": list(utxos)
        }
        print(json.dumps(output))
        self.wallet.new_history = False

    async def input_loop(self):
        while True:
            input_ = await ainput(loop=self.loop)
            if not input_:
                continue
            if input_ == "@end":
                sys.exit(0)
            obj = json.loads(input_)
            self.dispatch_input(obj)

    async def print_new_history(self):
        while True:
            await asyncio.sleep(1)
            if self.wallet.new_history:
                history = self.wallet.get_tx_history()[-1].as_dict()
                output = {"new_history": history}
                print(json.dumps(output))
                self.wallet.new_history = False

    def dispatch_input(self, obj):
        type_ = obj["type"]
        if type_ == "some_message_type":
            pass

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    salt, passphrase = "foo1", "bar1"  # TODO: Get from user somehow
    daemon = WalletDaemon(loop, salt, passphrase)

    tasks = asyncio.gather(
        asyncio.ensure_future(daemon.wallet.listen_to_addresses()),
        asyncio.ensure_future(daemon.input_loop()),
        asyncio.ensure_future(daemon.print_new_history())
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
