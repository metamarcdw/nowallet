import sys, asyncio, getpass
from decimal import Decimal

from . import nowallet

async def print_loop(wallet: nowallet.Wallet) -> None:
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
    # ADD VERTCOIN SUPPORT
    from pycoin.networks.network import Network
    from pycoin.networks import register_network
    vtc_net = Network('VTC', 'Vertcoin', 'mainnet',
                      wif=b'\x80', address=b'\x47', pay_to_script=b'\x05',
                      prv32=b'\x04358394', pub32=b'\x043587cf') # type: Network
    register_network(vtc_net)

    chain = nowallet.TBTC
    loop = asyncio.get_event_loop()  # type: asyncio.AbstractEventLoop

    t = nowallet.get_random_onion(loop, chain)  # type: Tuple[str, int]
    server, port = t
    connection = nowallet.Connection(
        loop, server, port)  # type: nowallet.Connection
#    connection = nowallet.Connection(
#        loop, "mdw.ddns.net", 50002)  # type: nowallet.Connection

    email = input("Enter email: ")  # type: str
    passphrase = getpass.getpass("Enter passphrase: ")  # type: str
    confirm = getpass.getpass("Confirm your passphrase: ")  # type: str
    assert passphrase == confirm, "Passphrase and confirmation did not match"
    assert email and passphrase, "Email and/or passphrase were blank"
    wallet = nowallet.Wallet(
        email, passphrase, connection, loop, chain)  # type: nowallet.Wallet
    wallet.discover_all_keys()

    if len(sys.argv) > 1 and sys.argv[1].lower() == "spend":
        print("\nConfirmed balance: {} {}".format(
            wallet.balance, chain.chain_1209k.upper()))
        print("Enter a destination address:")
        spend_addr = input("> ")  # type: str
        print("Enter an amount to spend:")
        spend_amount = Decimal(input("> "))  # type: Decimal
        assert spend_addr and spend_amount, \
                "Spend address and/or amount were blank"
        assert spend_amount <= wallet.balance, "Insufficient funds"

        use_rbf = False  # type: bool
        if len(sys.argv) > 2 and sys.argv[2].lower() == "rbf":
            use_rbf = True
        coin_per_kb = wallet.get_fee_estimation()  # type: float

        t = wallet.spend(spend_addr,
                         spend_amount,
                         coin_per_kb,
                         rbf=use_rbf)  # type: Tuple[str, Decimal]
        txid, decimal_fee = t

        print("Added a miner fee of: {} {}".format(
            decimal_fee, chain.chain_1209k.upper()))
        print("Transaction sent!\nID: {}".format(txid))

    tasks = asyncio.gather(
        asyncio.ensure_future(wallet.listen_to_addresses()),
        asyncio.ensure_future(print_loop(wallet)))

    # Graceful shutdown code borrowed from:
    # https://stackoverflow.com/questions/30765606/
    # whats-the-correct-way-to-clean-up-after-an-interrupted-event-loop
    try:
        # Here `amain(loop)` is the core coroutine that may spawn any
        # number of tasks
        sys.exit(loop.run_until_complete(tasks))
    except KeyboardInterrupt:
        # Optionally show a message if the shutdown may take a while
        print("\nAttempting graceful shutdown, press Ctrl+C again to exit…",
              flush=True)

        # Do not show `asyncio.CancelledError` exceptions during shutdown
        # (a lot of these may be generated, skip this if you prefer to see them)
        def shutdown_exception_handler(loop, context):
            if "exception" not in context \
            or not isinstance(context["exception"], asyncio.CancelledError):
                loop.default_exception_handler(context)
        loop.set_exception_handler(shutdown_exception_handler)

        # Handle shutdown gracefully by waiting for all tasks to be cancelled
        tasks = asyncio.gather(*asyncio.Task.all_tasks(loop=loop),
                               loop=loop,
                               return_exceptions=True)
        tasks.add_done_callback(lambda t: loop.stop())
        tasks.cancel()

        # Keep the event loop running until it is either destroyed or all
        # tasks have really terminated
        while not tasks.done() and not loop.is_closed():
            loop.run_forever()
    finally:
        loop.close()

if __name__ == "__main__":
    main()
