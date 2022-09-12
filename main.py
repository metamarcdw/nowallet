#! /usr/bin/env python3
import sys
import re
import asyncio
import logging
from aiosocks import SocksConnectionError
from aiohttp.client_exceptions import ClientConnectorError
from decimal import Decimal

import kivy
kivy.require("1.10.0")

from kivy.utils import platform
from kivy.core.window import Window
# from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import NumericProperty, StringProperty, ObjectProperty
from kivy.uix.screenmanager import Screen
from kivy.uix.behaviors import ButtonBehavior

from kivymd.app import MDApp
from kivymd.theming import ThemeManager
from kivymd.uix.list import TwoLineListItem, TwoLineIconListItem, ILeftBodyTouch, OneLineListItem
from kivymd.uix.button import MDIconButton, MDRaisedButton, MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.menu import MDDropdownMenu
#from kivymd.uix.menu.menu import MDMenuItem
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.tab import MDTabsBase

from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.button import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty


# class MDMenuItem(RecycleDataViewBehavior, ButtonBehavior, BoxLayout):
    # text = StringProperty()
 

from kivy.garden.qrcode import QRCodeWidget

from pycoin.key import validate
from pycoin.serialize import b2h

import nowallet
from nowallet.exchange_rate import fetch_exchange_rates
from settings_json import settings_json
from functools import partial
from kivy.clock import Clock
import asynckivy as ak
import threading
import concurrent.futures

__version__ = nowallet.__version__
if platform != "android":
    Window.size = (350, 550)


class Tab(MDFloatLayout, MDTabsBase):
    '''Class implementing content for a tab.'''
    content_text = StringProperty()
    pass


# Declare screens
class LoginScreen(Screen):
    pass


class MainScreen(Screen):
    pass


class WaitScreen(Screen):
    pass


class UTXOScreen(Screen):
    pass


class YPUBScreen(Screen):
    pass


class PINScreen(Screen):
    pass


class ZbarScreen(Screen):
    pass


# Declare custom widgets
class IconLeftSampleWidget(ILeftBodyTouch, MDIconButton):
    pass


class BalanceLabel(ButtonBehavior, MDLabel):
    pass


class PINButton(MDRaisedButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.height = dp(50)


class UTXOListItem(TwoLineListItem):
    utxo = ObjectProperty()

# class MyMenuItem(MDMenuItem):
class MyMenuItem(OneLineListItem):
    pass

class ListItem(TwoLineIconListItem):
    icon = StringProperty("check-circle")
    history = ObjectProperty()

    def on_release(self):
        app = App.get_running_app()
        base_url, chain = None, app.chain.chain_1209k
        txid = self.history.tx_obj.id()
        if app.explorer == "blockcypher":
            base_url = "https://live.blockcypher.com/{}/tx/{}/"
            if app.chain == nowallet.TBTC:
                chain = "btc-testnet"
        elif app.explorer == "smartbit":
            base_url = "https://{}.smartbit.com.au/tx/{}/"
            if app.chain == nowallet.BTC:
                chain = "www"
            elif app.chain == nowallet.TBTC:
                chain = "testnet"
        url = base_url.format(chain, txid)
        open_url(url)


class FloatInput(MDTextField):
    pat = re.compile('[^0-9]')

    def insert_text(self, substring, from_undo=False):
        pat = self.pat
        if '.' in self.text:
            s = re.sub(pat, '', substring)
        else:
            s = '.'.join([re.sub(pat, '', s) for s in substring.split('.', 1)])
        return super(FloatInput, self).insert_text(s, from_undo=from_undo)


class NowalletApp(MDApp):
    """
     ValueError: ThemeManager.primary_palette is set to an invalid option 'Grey'. Must be one of: ['Red', 'Pink', 'Purple', 'DeepPurple', 'Indigo', 'Blue', 'LightBlue', 'Cyan', 'Teal', 'Green', 'LightGreen', 'Lime', 'Yellow', 'Amber', 'Orange', 'DeepOrange', 'Brown', 'Gray', 'BlueGray']
    """
    theme_cls = ThemeManager()
    theme_cls.theme_style = "Dark"
    theme_cls.primary_palette = "Gray"
    theme_cls.accent_palette = "DeepOrange"

    units = StringProperty()
    currency = StringProperty()
    current_coin = StringProperty("0")
    current_fiat = StringProperty("0")
    current_fee = NumericProperty()
    current_utxo = ObjectProperty()

    def __init__(self, loop):
        self.chain = nowallet.TBTC
        self.loop = loop
        self.is_amount_inputs_locked = False
        self.fiat_balance = False
        self.bech32 = False
        self.exchange_rates = None

        self.menu_items = [{"viewclass": "MyMenuItem",
                            "text": "View YPUB",
                            "on_release": lambda x="View YPUB": app.menu_item_handler(x)},
                           {"viewclass": "MyMenuItem",
                            "text": "Lock with PIN",
                            "on_release": lambda x="Lock with PIN": app.menu_item_handler(x)},
                           {"viewclass": "MyMenuItem",
                            "text": "Manage UTXOs",
                            "on_release": lambda x="Manage UTXOs": app.menu_item_handler(x)},
                           {"viewclass": "MyMenuItem",
                            "text": "Settings",
                            "on_release": lambda x="Settings": app.menu_item_handler(x)}]
        self.utxo_menu_items = [{"viewclass": "MyMenuItem",
                                 "text": "View Private key"},
                                {"viewclass": "MyMenuItem",
                                 "text": "View Redeem script"}]
        super().__init__()

    def show_dialog(self, title, message, qrdata=None, cb=None):
        if qrdata:
            dialog_height = 300
            content = QRCodeWidget(data=qrdata,
                                   size=(dp(150), dp(150)),
                                   size_hint=(None, None))
        else:
            dialog_height = 200
            content = ""
            # content = MDLabel(font_style='Body1',
            #                   theme_text_color='Secondary',
            #                   text=message,
            #                   size_hint_y=None,
            #                   valign='top')
            # content.bind(texture_size=content.setter('size'))
        self.dialog = MDDialog(title=title,
                               content_cls=content if content else None,
                               text=message if not content else None,
                               size_hint=(.8, None),
                               height=dp(dialog_height),
                               auto_dismiss=False,
                               buttons=[
                                   MDFlatButton(
                                       text="Dismiss",
                                       on_release=partial(self.close_dialog))
                                   ]
                               )

        self.dialog.open()

    def close_dialog(self, *args):
        self.dialog.dismiss()

    def start_zbar(self):
        if platform != "android":
            return
        self.root.ids.sm.current = "zbar"
        self.root.ids.detector.start()

    def qrcode_handler(self, symbols):
        try:
            address, amount = nowallet.get_payable_from_BIP21URI(symbols[0])
        except ValueError as ve:
            self.show_dialog("Error", str(ve))
            return
        self.root.ids.address_input.text = address
        self.update_amounts(text=str(amount))
        self.root.ids.detector.stop()
        self.root.ids.sm.current = "main"

    def menu_button_handler(self, button):
        if self.root.ids.sm.current == "main":
            # MDDropdownMenu(items=self.menu_items, width_mult=4).open(button)
            MDDropdownMenu(items=self.menu_items, width_mult=4, caller=button, max_height=dp(200)).open()

    def menu_item_handler(self, text):
        # Main menu items
        if "PUB" in text:
            self.root.ids.sm.current = "ypub"
        elif "PIN" in text:
            self.root.ids.sm.current = "pin"
        elif "UTXO" in text:
            self.root.ids.sm.current = "utxo"
        elif "Settings" in text:
            self.open_settings()
        # UTXO menu items
        elif self.root.ids.sm.current == "utxo":
            addr = self.utxo.address(self.chain.netcode)
            key = self.wallet.search_for_key(addr)
            if not key:
                key = self.wallet.search_for_key(addr, change=True)

            if "Private" in text:
                self.show_dialog("Private key", "", qrdata=key.wif())
            if "Redeem" in text:
                if self.bech32:
                    return
                script = b2h(key.p2wpkh_script())
                self.show_dialog("Redeem script", "", qrdata=script)

    def fee_button_handler(self):
        fee_input = self.root.ids.fee_input
        fee_button = self.root.ids.fee_button
        fee_input.disabled = not fee_input.disabled
        if not fee_input.disabled:
            fee_button.text = "Custom Fee"
        else:
            fee_button.text = "Normal Fee"
            fee_input.text = str(self.estimated_fee)
            self.current_fee = self.estimated_fee

    def fee_input_handler(self):
        text = self.root.ids.fee_input.text
        if text:
            self.current_fee = int(float(text))

    def set_address_error(self, addr):
        netcode = self.chain.netcode
        is_valid = addr.strip() and validate.is_address_valid(
            addr.strip(), ["address", "pay_to_script"], [netcode]) == netcode
        self.root.ids.address_input.error = not is_valid

    def set_amount_error(self, amount):
        _amount = Decimal(amount) if amount else Decimal("0")
        is_valid = _amount / self.unit_factor <= self.wallet.balance
        self.root.ids.spend_amount_input.error = not is_valid

    async def do_spend(self, address, amount, fee_rate):
        self.spend_tuple = await self.wallet.spend(
            address, amount, fee_rate, rbf=self.rbf)

    async def send_button_handler(self):
        addr_input = self.root.ids.address_input
        address = addr_input.text.strip()
        amount_str = self.root.ids.spend_amount_input.text
        amount = Decimal(amount_str) / self.unit_factor

        if addr_input.error or not address:
            self.show_dialog("Error", "Invalid address.")
            return
        elif amount > self.wallet.balance:
            self.show_dialog("Error", "Insufficient funds.")
            return
        elif not amount:
            self.show_dialog("Error", "Amount cannot be zero.")
            return

        fee_rate_sat = int(Decimal(self.current_fee))
        fee_rate = nowallet.Wallet.satb_to_coinkb(fee_rate_sat)
        await self.do_spend(address, amount, fee_rate)
        logging.info("Finished doing spend")

        txid, decimal_fee = self.spend_tuple[:2]

        message = "Added a miner fee of: {} {}".format(
            decimal_fee, self.chain.chain_1209k.upper())
        message += "\nTxID: {}...{}".format(txid[:13], txid[-13:])
        self.show_dialog("Transaction sent!", message)

    def check_new_history(self):
        if self.wallet.new_history:
            self.update_screens()
            self.wallet.new_history = False

    @property
    def pub_char(self):
        if self.chain == nowallet.BTC:
            return "z" if self.bech32 else "y"
        elif self.chain == nowallet.TBTC:
            return "v" if self.bech32 else "u"

    async def do_login(self):
        email = self.root.ids.email_field.text
        passphrase = self.root.ids.pass_field.text
        confirm = self.root.ids.confirm_field.text
        if not email or not passphrase or not confirm:
            self.show_dialog("Error", "All fields are required.")
            return
        if passphrase != confirm:
            self.show_dialog("Error", "Passwords did not match.")
            return
        self.bech32 = self.root.ids.bech32_checkbox.active
        self.menu_items[0]["text"] = "View {}PUB".format(self.pub_char.upper())

        self.root.ids.sm.current = "wait"
        try:
            await self.do_login_tasks(email, passphrase)
        except (SocksConnectionError, ClientConnectorError):
            self.show_dialog("Error",
                             "Make sure Tor/Orbot is installed and running before using Nowallet.",
                             cb=lambda x: sys.exit(1))
            return
        self.update_screens()
        self.root.ids.sm.current = "main"
        await asyncio.gather(
            self.new_history_loop(),
            self.do_listen_task()
            )

    def login(self):
        task1 = asyncio.create_task(self.do_login())

    async def do_listen_task(self):
        logging.info("Listening for new transactions.")
        task = asyncio.create_task(self.wallet.listen_to_addresses())

    async def do_login_tasks(self, email, passphrase):
        self.root.ids.wait_text.text = "Connecting.."

        server, port, proto = await nowallet.get_random_server(self.loop)

        try:
            connection = nowallet.Connection(self.loop, server, port, proto)
        except Exception as ex:
            print("excepted")
            logging.error(ex, exc_info=True)
            logging.info("{} {} {}".format(server, port, proto))
            await connection.do_connect()
            logging.info("{} {} {} -&gt; connected".format(server, port, proto))

        await connection.do_connect()

        self.root.ids.wait_text.text = "Deriving Keys.."

        # make run in a seperate thread
        # in executor runs but gets stuck
        # wallet = await asyncio.gather(self.loop.run_in_executor(None, nowallet.Wallet, email, passphrase,
            # connection, self.loop, self.chain, self.bech32))
        self.wallet = nowallet.Wallet(email, passphrase, connection, self.loop, self.chain, self.bech32)

        self.root.ids.wait_text.text = "Fetching history.."
        await self.wallet.discover_all_keys()

        self.root.ids.wait_text.text = "Fetching exchange rates.."
        # just await, but since the fetching url ruturns 403 make it anything
        # self.exchange_rates = await fetch_exchange_rates(nowallet.BTC.chain_1209k)
        self.exchange_rates = False

        self.root.ids.wait_text.text = "Getting fee estimate.."
        coinkb_fee = await self.wallet.get_fee_estimation()
        self.current_fee = self.estimated_fee = nowallet.Wallet.coinkb_to_satb(coinkb_fee)
        logging.info("Finished 'doing login tasks'")

    def update_screens(self):
        self.update_balance_screen()
        self.update_send_screen()
        self.update_recieve_screen()
        self.update_ypub_screen()
        self.update_utxo_screen()

    async def new_history_loop(self):
        while True:
            await asyncio.sleep(1)
            self.check_new_history()


    def toggle_balance_label(self):
        self.fiat_balance = not self.fiat_balance
        self.update_balance_screen()

    def balance_str(self, fiat=False):
        balance, units = None, None
        if not fiat:
            balance = self.unit_precision.format(
                self.wallet.balance * self.unit_factor)
            units = self.units
        else:
            balance = "{:.2f}".format(self.wallet.balance * self.get_rate())
            units = self.currency
        return "{} {}".format(balance.rstrip("0").rstrip("."), units)

    def update_balance_screen(self):
        self.root.ids.balance_label.text = self.balance_str(
            fiat=self.fiat_balance)
        self.root.ids.recycleView.data_model.data = []

        for hist in self.wallet.get_tx_history():
            logging.info("Adding history item to balance screen\n{}".format(hist))
            verb = "Sent" if hist.is_spend else "Recieved"
            hist_str = "{} {} {}".format(
                verb, hist.value * self.unit_factor, self.units)
            self.add_list_item(hist_str, hist)

    def update_utxo_screen(self):
        self.root.ids.utxoRecycleView.data_model.data = []
        for utxo in self.wallet.utxos:
            value = Decimal(str(utxo.coin_value / nowallet.Wallet.COIN))
            utxo_str = (self.unit_precision + " {}").format(
                value * self.unit_factor, self.units)
            self.add_utxo_list_item(utxo_str, utxo)

    def update_send_screen(self):
        self.root.ids.send_balance.text = \
            "Available balance:\n" + self.balance_str()
        self.root.ids.fee_input.text = str(self.current_fee)

    def update_recieve_screen(self):
        address = self.update_recieve_qrcode()
        encoding = "bech32" if self.wallet.bech32 else "P2SH"
        self.root.ids.addr_label.text = \
            "Current Address ({}):\n{}".format(encoding, address)

    def update_recieve_qrcode(self):
        address = self.wallet.get_address(
            self.wallet.get_next_unused_key(), addr=True)
        # address = self.wallet.get_address(
        #         self.wallet.get_key(index=0, change=False),
        #         addr=True
        #         )
        logging.info("Current address: {}".format(address))
        amount = Decimal(self.current_coin) / self.unit_factor
        self.root.ids.addr_qrcode.data = \
            "bitcoin:{}?amount={}".format(address, amount)
        return address

    def update_ypub_screen(self):
        ypub = self.wallet.ypub
        ypub = self.pub_char + ypub[1:]
        self.root.ids.ypub_label.text = "Extended Public Key (SegWit):\n" + ypub
        self.root.ids.ypub_qrcode.data = ypub

    def lock_UI(self, pin):
        if not pin:
            self.show_dialog("Error", "PIN field is empty.")
            return
        self.pin = pin
        self.root.ids.pin_back_button.disabled = True
        self.root.ids.lock_button.text = "unlock"

    def unlock_UI(self, attempt):
        if not attempt or attempt != self.pin:
            self.show_dialog("Error", "Bad PIN entered.")
            return
        self.root.ids.pin_back_button.disabled = False
        self.root.ids.lock_button.text = "lock"

    def update_pin_input(self, char):
        pin_input = self.root.ids.pin_input
        if char == "clear":
            pin_input.text = ""
        elif char == "lock":
            self.lock_UI(pin_input.text)
            pin_input.text = ""
        elif char == "unlock":
            self.unlock_UI(pin_input.text)
            pin_input.text = ""
        else:
            pin_input.text += char

    def update_unit(self):
        self.unit_factor = 1
        self.unit_precision = "{:.8f}"
        if self.units[0] == "m":
            self.unit_factor = 1000
            self.unit_precision = "{:.5f}"
        elif self.units[0] == "u":
            self.unit_factor = 1000000
            self.unit_precision = "{:.2f}"

        coin = Decimal(self.current_coin) / self.unit_factor
        fiat = Decimal(self.current_fiat) / self.unit_factor
        self.update_amount_fields(coin, fiat)

    def get_rate(self):
        rate = self.exchange_rates[self.price_api][self.currency] \
            if self.exchange_rates else 1
        return Decimal(str(rate))

    def update_amounts(self, text=None, type="coin"):
        if self.is_amount_inputs_locked:
            return
        amount = Decimal(text) if text else Decimal("0")
        rate = self.get_rate() / self.unit_factor
        new_amount = None
        if type == "coin":
            new_amount = amount * rate
            self.update_amount_fields(amount, new_amount)
        elif type == "fiat":
            new_amount = amount / rate
            self.update_amount_fields(new_amount, amount)
        self.update_recieve_qrcode()

    def update_amount_fields(self, coin, fiat):
        self.is_amount_inputs_locked = True
        _coin = self.unit_precision.format(coin)
        self.current_coin = _coin.rstrip("0").rstrip(".")
        _fiat = "{:.2f}".format(fiat)
        self.current_fiat = _fiat.rstrip("0").rstrip(".")
        self.is_amount_inputs_locked = False

    def on_start(self):
        pass

    def build(self):
        self.icon = "icons/brain.png"
        self.use_kivy_settings = False
        self.rbf = self.config.get("nowallet", "rbf")
        self.units = self.config.get("nowallet", "units")
        self.update_unit()
        self.currency = self.config.get("nowallet", "currency")
        self.explorer = self.config.get("nowallet", "explorer")
        self.set_price_api(self.config.get("nowallet", "price_api"))

    def build_config(self, config):
        config.setdefaults("nowallet", {
            "rbf": False,
            "units": self.chain.chain_1209k.upper(),
            "currency": "USD",
            "explorer": "blockcypher",
            "price_api": "BitcoinAverage"})
        Window.bind(on_keyboard=self.key_input)

    def build_settings(self, settings):
        coin = self.chain.chain_1209k.upper()
        settings.add_json_panel("Nowallet Settings",
                                self.config,
                                data=settings_json(coin))

    def on_config_change(self, config, section, key, value):
        if key == "rbf":
            self.rbf = value
        elif key == "units":
            self.units = value
            self.update_unit()
            self.update_amounts()
            self.update_balance_screen()
            self.update_send_screen()
            self.update_utxo_screen()
        elif key == "currency":
            self.currency = value
            self.update_amounts()
        elif key == "explorer":
            self.explorer = value
        elif key == "price_api":
            self.set_price_api(value)
            self.update_amounts()

    def set_price_api(self, val):
        if val == "BitcoinAverage":
            self.price_api = "btcav"
        elif val == "CryptoCompare":
            self.price_api = "ccomp"

    def key_input(self, window, key, scancode, codepoint, modifier):
        if key == 27:   # the back button / ESC
            return True  # override the default behaviour
        else:           # the key now does nothing
            return False

    def on_pause(self):
        return True

    def add_list_item(self, text, history):
        data = self.root.ids.recycleView.data_model.data
        icon = "check-circle" if history.height > 0 else "timer-sand"
        data.append({"text": text,
                        "secondary_text": history.tx_obj.id(),
                        "history": history,
                        "icon": icon})

    def add_utxo_list_item(self, text, utxo):
        data = self.root.ids.utxoRecycleView.data_model.data
        data.append({"text": text,
                        "secondary_text": utxo.as_dict()["tx_hash_hex"],
                        "utxo": utxo})


def open_url(url):
    if platform == 'android':
        ''' Open a webpage in the default Android browser.  '''
        from jnius import autoclass, cast
        context = autoclass('org.renpy.android.PythonActivity').mActivity
        Uri = autoclass('android.net.Uri')
        Intent = autoclass('android.content.Intent')

        intent = Intent()
        intent.setAction(Intent.ACTION_VIEW)
        intent.setData(Uri.parse(url))
        currentActivity = cast('android.app.Activity', context)
        currentActivity.startActivity(intent)
    else:
        import webbrowser
        webbrowser.open(url)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    # loop = asyncio.new_event_loop()
    app = NowalletApp(loop)
    loop.run_until_complete(app.async_run())
    loop.close()
