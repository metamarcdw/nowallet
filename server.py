from aiohttp import web
import json, asyncio, sys

from nowallet.scrape import scrape_electrum_servers
from nowallet import BTC, TBTC, LTC
CHAINS = [chain.chain_1209k for chain in (BTC, TBTC, LTC)]

class Server:
    def __init__(self, chain):
        self.chain = chain
        self.app = web.Application()
        self.app.router.add_get('/servers', self.handle)
        self.app.on_startup.append(self.start_background_tasks)
        self.app.on_cleanup.append(self.cleanup_background_tasks)
        self.load_server_list()

    def load_server_list(self):
        try:
            with open("servers.json", "r") as infile:
                self.server_list = json.load(infile)
        except Exception:
            self.server_list = []

    async def update_server_list(self):
        self.server_list = await scrape_electrum_servers(
            self.chain, loop=self.app.loop)
        with open("servers.json", "w") as outfile:
            json.dump(self.server_list, outfile)

    async def update_loop(self):
        while True:
            await self.update_server_list()
            await asyncio.sleep(600)

    async def start_background_tasks(self, app):
        app['dispatch'] = app.loop.create_task(self.update_loop())

    async def cleanup_background_tasks(self, app):
        app['dispatch'].cancel()
        await app['dispatch']

    async def handle(self, request):
        response_obj = { 'servers' : self.server_list }
        return web.Response(text=json.dumps(response_obj))

if __name__ == "__main__":
    is_chain_arg = len(sys.argv) > 1 and sys.argv[1] in CHAINS
    chain = sys.argv[1] if is_chain_arg else BTC.chain_1209k
    web.run_app(Server(chain).app, port=3000)
