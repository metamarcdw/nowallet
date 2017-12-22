#! /usr/bin/env python3
#import asyncio

import kivy
kivy.require('1.10.0')

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition

import nowallet
from settings_json import settings_json

__version__ = nowallet.__version__

# Declare screens
class LoginScreen(Screen):
    pass

class MainScreen(Screen):
    pass

class RecieveScreen(Screen):
    pass

class SendScreen(Screen):
    pass

class WaitScreen(Screen):
    pass

class XPUBScreen(Screen):
    pass

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
#        chain = nowallet.TBTC
#        loop = asyncio.get_event_loop()
#        server, port = nowallet.get_random_onion(loop, chain)
#        connection = nowallet.Connection(loop, server, port)
#        wallet = nowallet.Wallet(
#            "email", "passphrase", connection, loop, chain)
#        print(wallet.xpub)

        self.sm = sm
        super().__init__()

    def build(self):
        self.use_kivy_settings = False
        self.rbf = self.config.get("nowallet", "rbf")
        self.bech32 = self.config.get("nowallet", "bech32")
        self.currency = self.config.get("nowallet", "currency")
        return self.sm

    def build_config(self, config):
        config.setdefaults("nowallet", {
            "bech32": False,
            "rbf": False,
            "currency": "USD"})

    def build_settings(self, settings):
        settings.add_json_panel("Nowallet Settings",
                                self.config,
                                data=settings_json)

    def on_config_change(self, config, section, key, value):
        if key == "rbf":
            self.rbf = value
        if key == "bech32":
            self.bech32 = value
        elif key == "currency":
            self.currency = value

if __name__ == "__main__":
    NowalletApp().run()
