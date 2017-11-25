#! /usr/bin/env python3
import sys
import os

import kivy
kivy.require('1.10.0')

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.core.window import Window
Window.size = (350, 600)

#sys.path.append(os.path.abspath(
#    os.path.join(os.path.dirname(__file__), os.path.pardir)))
#import nowallet
from settings_json import settings_json

__version__ = "0.1.0"

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
        self.sm = sm
        super().__init__()

    def build(self):
        self.use_kivy_settings = False
        self.rbf = self.config.get("nowallet", "rbf")
        self.currency = self.config.get("nowallet", "currency")
        return self.sm

    def build_config(self, config):
        config.setdefaults("nowallet", {
            "rbf": False,
            "currency": "USD"})

    def build_settings(self, settings):
        settings.add_json_panel("Nowallet Settings",
                                self.config,
                                data=settings_json)

    def on_config_change(self, config, section, key, value):
        if key == "rbf":
            self.rbf = value
        elif key == "currency":
            self.currency = value

if __name__ == "__main__":
    NowalletApp().run()
