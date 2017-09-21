#! /usr/bin/env python3

import kivy
kivy.require('1.10.0')

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.core.window import Window
Window.size = (350, 600)

Builder.load_string("""
#:import QRCodeWidget kivy.garden.qrcode

<SendScreen>:
    BoxLayout:
        orientation: "vertical"
        Label:
            text: "UNDER CONSTRUCTION"
        Button:
            text: "Back"
            size_hint: 1, 0.2
            on_press: root.manager.current = "main"

<RecieveScreen>:
    BoxLayout:
        orientation: "vertical"
        Label:
            text: "UNDER CONSTRUCTION"
        QRCodeWidget:
            data: "ballsagna"
        Button:
            text: "Back"
            on_press: root.manager.current = "main"

<MainScreen>:
    BoxLayout:
        orientation: "vertical"
        ActionBar:
            pos_hint: {'top':1}
            ActionView:
                use_separator: True
                ActionPrevious:
                    title: "NOWALLET"
                    with_previous: False
                ActionOverflow:
                ActionButton:
                    text: "?"
        Label:
            size_hint: 1, 0.3
            font_size: "30sp"
            text: "1.20049387 BTC"
        ScrollView:
            do_scroll_x: False
            GridLayout:
                cols: 1
                size_hint_y: None
                height: self.minimum_height
                Button:
                    size_hint_y: None
                    height: 50
                    text: "Recieved 0.5 BTC"
                Button:
                    size_hint_y: None
                    height: 50
                    text: "Recieved 1 BTC"
                Button:
                    size_hint_y: None
                    height: 50
                    text: "Sent 0.299 BTC"
        BoxLayout:
            size_hint: 1, 0.2
            Button:
                font_size: "30sp"
                text: "Recieve"
                on_press: root.manager.current = "recieve"
            Button:
                font_size: "30sp"
                text: "Send"
                on_press: root.manager.current = "send"

<LoginScreen>:
    ActionBar:
        pos_hint: {'top':1}
        ActionView:
            use_separator: True
            ActionPrevious:
                title: "NOWALLET"
                with_previous: False
            ActionOverflow:
            ActionButton:
                text: "?"
    AnchorLayout:
        BoxLayout:
            size_hint: 0.8, 0.5
            spacing: 3
            orientation: "vertical"
            Label:
                text: "Email/Salt"
            TextInput:
                hint_text: "email@domain.tld"
                write_tab: False
                padding_y: ( self.height - self.line_height ) / 2
            Label:
                text: "Passphrase"
            TextInput:
                password: True
                write_tab: False
                padding_y: ( self.height - self.line_height ) / 2
            Label:
                text: "Confirm Passphrase"
            TextInput:
                password: True
                write_tab: False
                padding_y: ( self.height - self.line_height ) / 2
            Button:
                text: "Create Wallet"
                on_press: root.manager.current = "main"
""")

# Declare screens
class LoginScreen(Screen):
    pass

class MainScreen(Screen):
    pass

class RecieveScreen(Screen):
    pass

class SendScreen(Screen):
    pass

# Create the screen manager
transition = SlideTransition(direction="up")
sm = ScreenManager(transition=transition)
sm.add_widget(LoginScreen(name="login"))
sm.add_widget(MainScreen(name="main"))
sm.add_widget(RecieveScreen(name="recieve"))
sm.add_widget(SendScreen(name="send"))

class NowalletApp(App):

    def build(self):
        return sm

if __name__ == "__main__":
    NowalletApp().run()
