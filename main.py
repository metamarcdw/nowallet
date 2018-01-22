#! /usr/bin/env python3
import asyncio

import kivy
kivy.require("1.10.0")

from kivy.utils import platform
from kivy.core.window import Window
from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.recycleview import RecycleView

from kivymd.theming import ThemeManager
from kivymd.list import OneLineIconListItem
from kivymd.list import ILeftBodyTouch
from kivymd.button import MDIconButton
from kivymd.menu import MDMenuItem

import nowallet
from settings_json import settings_json

__version__ = nowallet.__version__
if platform != "android":
    Window.size = (350, 550)

# Declare screens
class LoginScreen(Screen):
    pass

class MainScreen(Screen):
    pass

class WaitScreen(Screen):
    pass

class YPUBScreen(Screen):
    pass

class RV(RecycleView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data = [{"text": "Recieved 0.5 BTC"},
                     {"text": "Recieved 1 BTC"},
                     {"text": "Sent 0.299 BTC"}]

class IconLeftSampleWidget(ILeftBodyTouch, MDIconButton):
    pass

class ListItem(OneLineIconListItem):
    pass

class MenuItem(MDMenuItem):
    def on_release(self):
        if "YPUB" in self.text \
        and App.get_running_app().root.ids.sm.current == "main":
            App.get_running_app().root.ids.sm.current = "ypub"
        elif "Settings" in self.text:
            App.get_running_app().open_settings()

class NowalletApp(App):
    theme_cls = ThemeManager()
    theme_cls.theme_style = "Dark"
    theme_cls.primary_palette = "Grey"
    theme_cls.accent_palette = "LightGreen"

    def __init__(self):
        self.chain = nowallet.TBTC
        self.loop = asyncio.get_event_loop()
        self.menu_items = [
            {"viewclass": "MenuItem",
             "text": "View YPUB"},
            {"viewclass": "MenuItem",
             "text": "Settings"}
        ]
        super().__init__()

#    def on_start(self):
#        self.root.ids.sm.current = "wait"
#        server, port, proto = nowallet.get_random_onion(self.loop, self.chain)
#        connection = nowallet.Connection(self.loop, server, port, proto)
#        self.wallet = nowallet.Wallet("email", "passphrase", connection, self.loop, self.chain)
#        self.root.ids.sm.current = "login"
#        print(self.wallet.xpub)

    def build(self):
        self.icon = "icons/brain.png"
        self.use_kivy_settings = False
        self.rbf = self.config.get("nowallet", "rbf")
        self.bech32 = self.config.get("nowallet", "bech32")
        self.units = self.config.get("nowallet", "units")
        self.currency = self.config.get("nowallet", "currency")

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

    def add_list_item(self, text):
        data = self.root.ids.recycleView.data_model.data
        data.insert(0, {"text": text})

if __name__ == "__main__":
    NowalletApp().run()
