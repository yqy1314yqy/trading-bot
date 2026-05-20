"""
量化交易机器人 - Android APK
Kivy 苹果风格 UI + ccxt 交易引擎
"""
import json
import threading
from pathlib import Path

from kivy.utils import platform

if platform == 'android':
    from kivy.config import Config
    import os
    # Prefer bundled font, fall back to system CJK fonts
    _FONT_CANDIDATES = [
        'font.ttc',                                   # bundled WenQuanYi Micro Hei
        '/system/fonts/DroidSansFallbackBBK.ttf',      # vivo / BBK
        '/system/fonts/NotoSansCJK-Regular.ttc',       # Samsung / generic
        '/system/fonts/MiSans-Regular.ttf',            # Xiaomi
        '/system/fonts/HarmonyOS_Sans_SC_Regular.ttf',  # Huawei
        '/system/fonts/DroidSansFallback.ttf',         # older Android
    ]
    _font = next((f for f in _FONT_CANDIDATES if os.path.exists(f)), None)
    if _font:
        Config.set('kivy', 'default_font', [
            'Roboto', _font, _font, _font, _font
        ])

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.switch import Switch
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import get_color_from_hex as gc
from kivy.metrics import dp
from kivy.graphics import Color, RoundedRectangle

from bot import TradingEngine, STRATEGY_PARAMS

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

# ─── Colors ───
C_BG = "#F2F2F7"
C_CARD = "#FFFFFF"
C_TEXT = "#1C1C1E"
C_TEXT2 = "#8E8E93"
C_ACCENT = "#007AFF"
C_GREEN = "#34C759"
C_RED = "#FF3B30"
C_SEP = "E0E0E0"

engine = TradingEngine()


class AppleButton(Button):
    def __init__(self, color=C_ACCENT, **kw):
        super().__init__(**kw)
        self.background_normal = ""
        self.background_color = gc(color)
        self.font_size = dp(15)
        self.bold = True
        self.size_hint_y = None
        self.height = dp(48)
        with self.canvas.before:
            self.bg_color = Color(*gc(color))
            self.rect = RoundedRectangle(radius=[dp(12)])
        self.bind(pos=self._update, size=self._update)

    def _update(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class Card(BoxLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.orientation = "vertical"
        self.padding = dp(16)
        self.size_hint_y = None
        self.bind(minimum_height=self.setter("height"))
        with self.canvas.before:
            Color(*gc(C_CARD))
            self.rect = RoundedRectangle(radius=[dp(14)])
        self.bind(pos=self._update, size=self._update)

    def _update(self, *args):
        self.rect.pos = (self.x + dp(10), self.y)
        self.rect.size = (self.width - dp(20), self.height)


class StatBox(BoxLayout):
    def __init__(self, label, **kw):
        super().__init__(orientation="vertical", **kw)
        self.size_hint_y = None
        self.height = dp(72)
        self.value_label = Label(
            text="--", font_size=dp(20), bold=True,
            color=gc(C_TEXT), size_hint_y=None, height=dp(28)
        )
        name_label = Label(
            text=label, font_size=dp(11),
            color=gc(C_TEXT2), size_hint_y=None, height=dp(18)
        )
        self.add_widget(self.value_label)
        self.add_widget(name_label)
        with self.canvas.before:
            Color(*gc(C_CARD))
            self.rect = RoundedRectangle(radius=[dp(12)])
        self.bind(pos=self._update, size=self._update)

    def _update(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def set_value(self, val):
        self.value_label.text = str(val)


# ─── Dashboard Screen ───
class DashboardScreen(Screen):
    def __init__(self, **kw):
        super().__init__(name="dashboard", **kw)
        self.layout = ScrollView()
        self.inner = BoxLayout(orientation="vertical", padding=dp(16),
                               spacing=dp(12), size_hint_y=None)
        self.inner.bind(minimum_height=self.inner.setter("height"))

        # Balance card
        self.balance_card = Card(size_hint_y=None, height=dp(130))
        self.balance_label = Label(
            text="--- USDT", font_size=dp(40), bold=True,
            color=gc(C_TEXT), size_hint_y=None, height=dp(50),
            halign="left", valign="middle"
        )
        self.balance_label.bind(size=self.balance_label.setter("text_size"))
        self.pl_label = Label(
            text="--", font_size=dp(14),
            color=gc(C_TEXT2), size_hint_y=None, height=dp(22)
        )
        self.balance_card.add_widget(Label(
            text="账户余额", font_size=dp(12), color=gc(C_TEXT2),
            size_hint_y=None, height=dp(20)
        ))
        self.balance_card.add_widget(self.balance_label)
        self.balance_card.add_widget(self.pl_label)
        self.inner.add_widget(self.balance_card)

        # Stats
        stats = GridLayout(cols=3, spacing=dp(10), size_hint_y=None, height=dp(80))
        self.winrate_box = StatBox("胜率")
        self.trades_box = StatBox("总交易")
        self.open_box = StatBox("当前持仓")
        stats.add_widget(self.winrate_box)
        stats.add_widget(self.trades_box)
        stats.add_widget(self.open_box)
        self.inner.add_widget(stats)

        # Pairs card
        pairs_card = Card(size_hint_y=None, height=dp(60))
        pairs_card.add_widget(Label(
            text="交易对", font_size=dp(12), color=gc(C_TEXT2),
            size_hint_y=None, height=dp(18)
        ))
        self.pairs_label = Label(
            text="--", font_size=dp(14), color=gc(C_ACCENT),
            size_hint_y=None, height=dp(24)
        )
        pairs_card.add_widget(self.pairs_label)
        self.inner.add_widget(pairs_card)

        # Recent trades
        trades_card = Card()
        trades_card.add_widget(Label(
            text="最近交易", font_size=dp(12), color=gc(C_TEXT2),
            size_hint_y=None, height=dp(20)
        ))
        self.trades_list = BoxLayout(orientation="vertical", size_hint_y=None)
        self.trades_list.bind(minimum_height=self.trades_list.setter("height"))
        trades_card.add_widget(self.trades_list)
        self.inner.add_widget(trades_card)

        self.layout.add_widget(self.inner)
        self.add_widget(self.layout)

    def update(self, state):
        bal = state.get("balance", 0)
        self.balance_label.text = f"{bal:,.2f} USDT"
        profit = state.get("profit_total", 0)
        pct = state.get("profit_pct", 0)
        c = C_GREEN if profit >= 0 else C_RED
        self.pl_label.text = f"{'+' if profit>=0 else ''}{profit:.2f} USDT ({'+' if pct>=0 else ''}{pct:.2f}%)"
        self.pl_label.color = gc(c)

        total = state.get("trades_total", 0)
        wins = state.get("trades_win", 0)
        wr = f"{wins/total*100:.0f}%" if total > 0 else "--"
        self.winrate_box.set_value(wr)
        self.trades_box.set_value(str(total))
        self.open_box.set_value(str(len(state.get("open_positions", []))))

        cfg = engine.load_config()
        pairs = cfg.get("exchange", {}).get("pair_whitelist", [])
        self.pairs_label.text = " · ".join(p.replace(":USDT", "") for p in pairs)

        self.trades_list.clear_widgets()
        for t in state.get("closed_trades", [])[:15]:
            row = BoxLayout(
                orientation="horizontal", size_hint_y=None, height=dp(40)
            )
            row.add_widget(Label(
                text=t["pair"], font_size=dp(14), color=gc(C_TEXT),
                size_hint_x=0.3
            ))
            row.add_widget(Label(
                text=t.get("time", ""), font_size=dp(11),
                color=gc(C_TEXT2), size_hint_x=0.35
            ))
            pnl = t.get("pnl_pct", 0)
            row.add_widget(Label(
                text=f"{'+' if pnl>=0 else ''}{pnl}%",
                font_size=dp(14), bold=True,
                color=gc(C_GREEN if pnl >= 0 else C_RED),
                size_hint_x=0.35, halign="right"
            ))
            self.trades_list.add_widget(row)


# ─── Settings Screen ───
class SettingsScreen(Screen):
    def __init__(self, **kw):
        super().__init__(name="settings", **kw)
        layout = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(14))

        # API Key
        layout.add_widget(Label(
            text="API KEY", font_size=dp(11), color=gc(C_TEXT2),
            size_hint_y=None, height=dp(16)
        ))
        self.api_key = TextInput(
            text="", password=True, multiline=False,
            size_hint_y=None, height=dp(46),
            background_color=gc(C_CARD),
            foreground_color=gc(C_TEXT),
            cursor_color=gc(C_ACCENT),
            font_size=dp(14),
            hint_text="输入币安 API Key",
            hint_text_color=gc(C_TEXT2),
        )
        layout.add_widget(self.api_key)

        # API Secret
        layout.add_widget(Label(
            text="API SECRET", font_size=dp(11), color=gc(C_TEXT2),
            size_hint_y=None, height=dp(16)
        ))
        self.api_secret = TextInput(
            text="", password=True, multiline=False,
            size_hint_y=None, height=dp(46),
            background_color=gc(C_CARD),
            foreground_color=gc(C_TEXT),
            cursor_color=gc(C_ACCENT),
            font_size=dp(14),
            hint_text="输入币安 API Secret",
            hint_text_color=gc(C_TEXT2),
        )
        layout.add_widget(self.api_secret)

        # Proxy
        layout.add_widget(Label(
            text="代理地址（国内必填）", font_size=dp(11), color=gc(C_TEXT2),
            size_hint_y=None, height=dp(16)
        ))
        self.proxy = TextInput(
            text="", multiline=False,
            size_hint_y=None, height=dp(46),
            background_color=gc(C_CARD),
            foreground_color=gc(C_TEXT),
            cursor_color=gc(C_ACCENT),
            font_size=dp(14),
            hint_text="http://127.0.0.1:7890",
            hint_text_color=gc(C_TEXT2),
        )
        layout.add_widget(self.proxy)

        # Dry run switch
        switch_row = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(44)
        )
        switch_row.add_widget(Label(
            text="模拟交易 (Dry Run)", font_size=dp(14), color=gc(C_TEXT)
        ))
        self.dry_switch = Switch(active=True)
        self.dry_switch.bind(active=self._on_dry)
        switch_row.add_widget(self.dry_switch)
        layout.add_widget(switch_row)

        # Save button
        save_btn = AppleButton(color=C_ACCENT, text="保存配置")
        save_btn.bind(on_release=lambda x: self.save())
        layout.add_widget(save_btn)

        # Test button
        test_btn = AppleButton(color=C_GREEN, text="测试连接")
        test_btn.bind(on_release=lambda x: self.test_connection())
        layout.add_widget(test_btn)

        self.test_result = Label(
            text="", font_size=dp(13), size_hint_y=None, height=dp(40),
            color=gc(C_TEXT2)
        )
        layout.add_widget(self.test_result)

        layout.add_widget(Label(
            text="⚠ 请创建独立交易子账户 API\n仅开启「合约交易」，务必关闭「提现」",
            font_size=dp(12), color=gc(C_RED),
            size_hint_y=None, height=dp(40)
        ))

        self.add_widget(layout)

    def _on_dry(self, instance, value):
        pass

    def save(self):
        cfg = engine.load_config()
        cfg["exchange"]["key"] = self.api_key.text.strip()
        cfg["exchange"]["secret"] = self.api_secret.text.strip()
        proxy = self.proxy.text.strip()
        cfg["exchange"]["ccxt_config"]["proxies"] = {
            "http": proxy, "https": proxy
        }
        cfg["exchange"]["ccxt_async_config"]["proxies"] = {
            "http": proxy, "https": proxy
        }
        cfg["dry_run"] = self.dry_switch.active
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=4)
        self.test_result.text = "✓ 配置已保存"
        self.test_result.color = gc(C_GREEN)

    def test_connection(self):
        self.save()
        threading.Thread(target=self._do_test, daemon=True).start()

    def _do_test(self):
        try:
            import ccxt
            cfg = engine.load_config()
            params = {
                "apiKey": cfg["exchange"]["key"],
                "secret": cfg["exchange"]["secret"],
                "enableRateLimit": True,
                "options": {"defaultType": "future"},
            }
            proxy = cfg["exchange"]["ccxt_config"]["proxies"].get("https", "")
            if proxy:
                params["proxies"] = {"http": proxy, "https": proxy}
            ex = ccxt.binance(params)
            ex.load_markets()
            bal = ex.fetch_balance()
            usdt = bal.get("USDT", {})
            Clock.schedule_once(lambda dt: self._show_test_result(
                True, usdt.get("total", 0)
            ))
        except Exception as e:
            Clock.schedule_once(lambda dt: self._show_test_result(
                False, str(e)[:100]
            ))

    def _show_test_result(self, ok, info):
        if ok:
            self.test_result.text = f"✓ 连接成功！余额: {info:.2f} USDT"
            self.test_result.color = gc(C_GREEN)
        else:
            self.test_result.text = f"✗ 连接失败: {info}"
            self.test_result.color = gc(C_RED)

    def load(self):
        try:
            cfg = engine.load_config()
            self.api_key.text = cfg.get("exchange", {}).get("key", "")
            self.api_secret.text = cfg.get("exchange", {}).get("secret", "")
            proxy = cfg.get("exchange", {}).get("ccxt_config", {}).get("proxies", {})
            self.proxy.text = proxy.get("https", "")
            self.dry_switch.active = cfg.get("dry_run", True)
        except Exception:
            pass


# ─── Logs Screen ───
class LogsScreen(Screen):
    def __init__(self, **kw):
        super().__init__(name="logs", **kw)
        layout = BoxLayout(orientation="vertical", padding=dp(16))
        self.log_label = Label(
            text="暂无日志", font_size=dp(11),
            font_name="DroidSansMono",
            color=gc(C_TEXT), valign="top", halign="left",
            size_hint_y=None
        )
        self.log_label.bind(
            size=self.log_label.setter("text_size"),
            texture_size=self._update_height
        )
        scroll = ScrollView()
        scroll.add_widget(self.log_label)
        layout.add_widget(scroll)
        self.add_widget(layout)

    def _update_height(self, instance, value):
        instance.height = value[1]

    def update(self, logs):
        self.log_label.text = "\n".join(logs[-80:]) or "暂无日志"


# ─── Main App ───
class TradingBotApp(App):
    def build(self):
        Window.clearcolor = gc(C_BG)

        self.root = BoxLayout(orientation="vertical")

        # Status bar
        self.status_bar = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(56),
            padding=[dp(16), dp(8)]
        )
        with self.status_bar.canvas.before:
            Color(*gc(C_BG))
            self.status_rect = RoundedRectangle()
        self.status_bar.bind(pos=self._update_status_bg, size=self._update_status_bg)

        self.status_dot = Label(
            text="●", font_size=dp(16), color=gc(C_RED),
            size_hint_x=None, width=dp(24)
        )
        self.status_text = Label(
            text="已停止", font_size=dp(16), bold=True, color=gc(C_TEXT)
        )
        self.status_bar.add_widget(self.status_dot)
        self.status_bar.add_widget(self.status_text)
        self.root.add_widget(self.status_bar)

        # Start / Stop buttons
        btn_row = BoxLayout(
            orientation="horizontal", spacing=dp(12),
            padding=[dp(16), dp(8)], size_hint_y=None, height=dp(56)
        )
        self.start_btn = AppleButton(color=C_GREEN, text="▶  启动")
        self.start_btn.bind(on_release=lambda x: self._start())
        self.stop_btn = AppleButton(color=C_RED, text="■  停止")
        self.stop_btn.bind(on_release=lambda x: self._stop())
        self.stop_btn.background_color = gc(C_RED + "88")
        btn_row.add_widget(self.start_btn)
        btn_row.add_widget(self.stop_btn)
        self.root.add_widget(btn_row)

        # Screens
        self.sm = ScreenManager()
        self.dashboard = DashboardScreen()
        self.settings = SettingsScreen()
        self.logs = LogsScreen()
        self.sm.add_widget(self.dashboard)
        self.sm.add_widget(self.settings)
        self.sm.add_widget(self.logs)
        self.root.add_widget(self.sm)

        # Bottom nav
        nav = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(64),
            padding=[dp(16), dp(8)]
        )
        with nav.canvas.before:
            Color(*gc(C_CARD))
            self.nav_rect = RoundedRectangle()
        nav.bind(pos=self._update_nav_bg, size=self._update_nav_bg)

        for name, label in [("dashboard", "📊 仪表盘"), ("settings", "⚙️ 设置"), ("logs", "📋 日志")]:
            btn = Button(
                text=label, font_size=dp(12), color=gc(C_ACCENT),
                background_normal="", background_down="",
                size_hint_y=None, height=dp(44),
            )
            btn.bind(on_release=lambda x, s=name: self._switch_screen(s))
            if name == "dashboard":
                self._active_nav = btn
            nav.add_widget(btn)
        self.root.add_widget(nav)

        # Timer
        Clock.schedule_interval(self._update_ui, 8)
        Clock.schedule_once(lambda dt: self.settings.load(), 1)

        return self.root

    def _update_status_bg(self, *args):
        pass

    def _update_nav_bg(self, *args):
        pass

    def _switch_screen(self, name):
        self.sm.current = name
        if name == "logs":
            self.logs.update(engine.state.get("logs", []))

    def _start(self):
        if not engine.running:
            engine.start()
            self._update_status("running")

    def _stop(self):
        if engine.running:
            engine.stop()
            self._update_status("stopped")

    def _update_status(self, status):
        if status == "running":
            self.status_dot.color = gc(C_GREEN)
            self.status_text.text = "运行中"
        else:
            self.status_dot.color = gc(C_RED)
            self.status_text.text = "已停止"

    def _update_ui(self, dt):
        state = engine.state
        running = engine.running
        Clock.schedule_once(lambda _: self._update_status(
            "running" if running else "stopped"
        ))
        if running:
            self.dashboard.update(state)
        if self.sm.current == "logs":
            self.logs.update(state.get("logs", []))


if __name__ == "__main__":
    TradingBotApp().run()
