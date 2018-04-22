import json, asyncio, sys
from aiohttp import web

from connectrum.svr_info import ServerInfo
from connectrum.client import StratumClient

from nowallet.scrape import scrape_electrum_servers
from nowallet import BTC, TBTC, LTC
CHAINS = [_chain.chain_1209k for _chain in (BTC, TBTC, LTC)]

class Server:
    def __init__(self, _chain):
        self.chain = _chain
        self.client = None
        self.connection = None
        self.server_list = None
        self.app = web.Application()
        self.app.router.add_get('/servers', self.handle)
        self.app.on_startup.append(self.start_background_tasks)
        self.app.on_cleanup.append(self.cleanup_background_tasks)
        self.load_server_list()
        self.connected = False

    def load_server_list(self):
        try:
            with open("servers.json", "r") as infile:
                self.server_list = json.load(infile)
        except Exception:
            self.server_list = list()

    async def connect(self):
        server_info = ServerInfo(
            "", hostname="mdw.ddns.net", ports=50001)
        self.client = StratumClient(self.app.loop)
        self.connection = self.client.connect(
            server_info,
            proto_code="t")  # type: asyncio.Future
        try:
            await self.connection
            self.connected = True
        except Exception:
            print("Unable to connect to server:", server_info)

    async def get_peers(self):
        server_list = list()
        peers = await self.client.RPC("server.peers.subscribe")
        for peer in peers:
            host, info = peer[1:]
            if info[0] not in ("v1.1", "v1.2"):
                continue
            proto_port = info[1]
            proto, port = proto_port[0], int(proto_port[1:])
            server = [host, port, proto]
            server_list.append(server)
        return server_list

    async def update_server_list(self):
        if self.connected:
            self.server_list = await self.get_peers()
        else:
            self.server_list = await scrape_electrum_servers(
                self.chain, loop=self.app.loop)
        with open("servers.json", "w") as outfile:
            json.dump(self.server_list, outfile)

    async def update_loop(self):
        while True:
            if self.connected and not self.client.protocol:
                self.connected = False
            if not self.connected:
                pass # await self.connect()
            await self.update_server_list()
            await asyncio.sleep(600)

    async def start_background_tasks(self, app):
        app['dispatch'] = asyncio.ensure_future(self.update_loop())

    async def cleanup_background_tasks(self, app):
        app['dispatch'].cancel()
        await app['dispatch']

    async def handle(self, request):
        response_obj = {'servers' : self.server_list}
        return web.json_response(response_obj)

if __name__ == "__main__":
    is_chain_arg = len(sys.argv) > 1 and sys.argv[1] in CHAINS
    chain = sys.argv[1] if is_chain_arg else BTC.chain_1209k
    web.run_app(Server(chain).app, port=3000)
else:
    global_app = Server(TBTC.chain_1209k).app
