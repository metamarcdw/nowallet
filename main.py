#! /usr/bin/env python3
import asyncio
from async_gui.engine import Task
from async_gui.toolkits.kivy import KivyEngine
engine = KivyEngine()

import kivy
kivy.require("1.10.0")

from kivy.utils import platform
from kivy.core.window import Window
from kivy.app import App
from kivy.metrics import dp
from kivy.uix.screenmanager import Screen

from kivymd.theming import ThemeManager
from kivymd.list import OneLineIconListItem
from kivymd.list import ILeftBodyTouch
from kivymd.button import MDIconButton
from kivymd.menu import MDMenuItem
from kivymd.dialog import MDDialog
from kivymd.label import MDLabel

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

        self.menu_items = [{"viewclass": "MenuItem",
                            "text": "View YPUB"},
                           {"viewclass": "MenuItem",
                            "text": "Settings"}]
        super().__init__()

    def show_dialog(self, title, message):
        content = MDLabel(font_style='Body1',
                          theme_text_color='Secondary',
                          text=message,
                          size_hint_y=None,
                          valign='top')
        content.bind(texture_size=content.setter('size'))
        self.dialog = MDDialog(title=title,
                               content=content,
                               size_hint=(.8, None),
                               height=dp(200),
                               auto_dismiss=False)

        self.dialog.add_action_button("Dismiss",
                                      action=lambda *x: self.dialog.dismiss())
        self.dialog.open()

    def do_login(self):
        email = self.root.ids.email_field.text
        passphrase = self.root.ids.pass_field.text
        confirm = self.root.ids.confirm_field.text
        if not email or not passphrase or not confirm:
            self.show_dialog("Error", "All fields are required.")
            return
        if passphrase != confirm:
            self.show_dialog("Error", "Passwords did not match.")
            return

        self.root.ids.sm.current = "wait"
        self.do_login_tasks(email, passphrase)
        self.update_balance_screen()
        self.root.ids.sm.current = "main"

    @engine.async
    def do_login_tasks(self, email, passphrase):
        self.root.ids.wait_text.text = "Connecting.."
        server, port, proto = yield Task(
            nowallet.get_random_onion, self.loop, self.chain)
        connection = yield Task(
            nowallet.Connection, self.loop, server, port, proto)
        self.root.ids.wait_text.text = "Deriving Keys.."
        self.wallet = yield Task(
            nowallet.Wallet, email, passphrase,
            connection, self.loop, self.chain)
        self.root.ids.wait_text.text = "Fetching history.."
        yield Task(self.wallet.discover_all_keys)

    def update_balance_screen(self):
        balance_str = "{} {}".format(
            self.wallet.balance, self.wallet.chain.chain_1209k.upper())
        self.root.ids.balance_label.text = balance_str
        for hist in self.wallet.get_tx_history():
            verb = "Sent" if hist.is_spend else "Recieved"
            hist_str = "{} {} {}".format(
                verb, hist.value, self.wallet.chain.chain_1209k.upper())
            self.add_list_item(hist_str)

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

    def on_pause(self):
        return True

    def add_list_item(self, text):
        data = self.root.ids.recycleView.data_model.data
        data.insert(0, {"text": text})

if __name__ == "__main__":
    app = NowalletApp()
    engine.main_app = app
    app.run()
