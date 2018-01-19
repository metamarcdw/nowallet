#! /usr/bin/env python3
import asyncio

import kivy
kivy.require('1.10.0')

from kivy.utils import platform
from kivy.core.window import Window
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.recycleview import RecycleView
from async_gui.tasks import Task, ProcessTask
from async_gui.toolkits.kivy import KivyEngine

import nowallet
from settings_json import settings_json

__version__ = nowallet.__version__
if platform != 'android':
    Window.size = (350, 550)

# Declare screens
class LoginScreen(Screen):
    pass

class MainScreen(Screen):
    pass

class RecieveScreen(Screen):
    pass

class SendScreen(Screen):
    def add_new_data(self, text):
        data = sm.get_screen("main").ids.recycleView.data_model.data
        data.insert(0, {"text": text})

class WaitScreen(Screen):
    pass

class XPUBScreen(Screen):
    pass

class RV(RecycleView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data = [{"text": "Recieved 0.5 BTC"},
                     {"text": "Recieved 1 BTC"},
                     {"text": "Sent 0.299 BTC"}]

engine = KivyEngine()
buildKV = Builder.load_file("nowallet_ui.kv")

# Create the screen manager
transition = SlideTransition(direction="up")
sm = ScreenManager(transition=transition)
sm.add_widget(LoginScreen(name="login"))
sm.add_widget(MainScreen(name="main"))
sm.add_widget(RecieveScreen(name="recieve"))
sm.add_widget(SendScreen(name="send"))
sm.add_widget(WaitScreen(name="wait"))
sm.add_widget(XPUBScreen(name="xpub"))

class NowalletApp(App):
    def __init__(self):
        self.chain = nowallet.TBTC
        self.loop = asyncio.get_event_loop()
        self.sm = sm
        super().__init__()

#    def on_start(self):
#        sm.current = "wait"
#        self.scrape_1209k()
#        self.initialize_connection()
#        self.initialize_wallet()
#        sm.current = "main"
#        print(self.wallet.xpub)

    def on_start(self):
        sm.get_screen("wait").ids.wait_text.text = "Waiting 3sec"
        sm.current = "wait"
        self.wait_three()
        sm.current = "main"

    @engine.async
    def wait_three(self):
        import time
        yield Task(time.sleep, 3)

    @engine.async
    def scrape_1209k(self):
        self.server = yield Task(
            nowallet.get_random_onion, self.loop, self.chain)
    @engine.async
    def initialize_connection(self):
        server, port, proto = self.server
        self.connection = yield Task(
            nowallet.Connection, self.loop, server, port, proto)
    @engine.async
    def initialize_wallet(self):
        self.wallet = yield ProcessTask(self.new_wallet)

    def new_wallet(self, email="email", passphrase="passphrase"):
        return nowallet.Wallet(email,
                               passphrase,
                               self.connection,
                               self.loop,
                               self.chain)

    def build(self):
            self.icon = "icons/brain.png"
            self.use_kivy_settings = False
            self.rbf = self.config.get("nowallet", "rbf")
            self.bech32 = self.config.get("nowallet", "bech32")
            self.units = self.config.get("nowallet", "units")
            self.currency = self.config.get("nowallet", "currency")
            return self.sm

    def build_config(self, config):
        config.setdefaults("nowallet", {
            "bech32": False,
            "rbf": False,
            "units": "BTC",
            "currency": "USD"})
        Window.bind(on_keyboard=self.key_input)

    def build_settings(self, settings):
        settings.add_json_panel("Nowallet Settings",
                                self.config,
                                data=settings_json)

    def on_config_change(self, config, section, key, value):
        if key == "rbf":
            self.rbf = value
        elif key == "bech32":
            self.bech32 = value
        elif key == "units":
            self.units = value
        elif key == "currency":
            self.currency = value

    def key_input(self, window, key, scancode, codepoint, modifier):
        if key == 27:   # the back button / ESC
            return True  # override the default behaviour
        else:           # the key now does nothing
            return False

if __name__ == "__main__":
    NowalletApp().run()
