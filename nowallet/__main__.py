import getpass
from .nowallet import *

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
        prv32=b'\x04358394', pub32=b'\x043587cf')
    register_network(vtc_net)

    chain = TBTC
    loop = asyncio.get_event_loop()  # type: asyncio.AbstractEventLoop

    t = get_random_onion(loop, chain)  # type: Tuple[str, int]
    server, port = t
    connection = Connection(loop, server, port)  # type: Connection
#    connection = Connection(loop, "mdw.ddns.net", 50002)  # type: Connection

    email = input("Enter email: ")  # type: str
    passphrase = getpass.getpass("Enter passphrase: ")  # type: str
    confirm = getpass.getpass("Confirm your passphrase: ")  # type: str
    assert passphrase == confirm, "Passphrase and confirmation did not match"
    assert email and passphrase, "Email and/or passphrase were blank"
    wallet = Wallet(email, passphrase, connection, loop, chain)  # type: Wallet
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

    asyncio.ensure_future(wallet.listen_to_addresses())
    asyncio.ensure_future(print_loop(wallet))

    loop.run_forever()
    loop.close()

if __name__ == "__main__":
    main()
