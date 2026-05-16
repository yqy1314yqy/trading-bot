"""
独立量化交易引擎 — 不依赖 Freqtrade
纯 Python 实现，可在 Android 上直接运行
"""
import time
import json
import threading
from datetime import datetime
from pathlib import Path

import numpy as np
import ccxt
from indicators import rsi, bbands, adx

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state.json"

# ─── 策略参数（合约优化版） ───
STRATEGY_PARAMS = {
    "bb_period": 25,
    "bb_std": 1.292,
    "rsi_period": 14,
    "rsi_buy": 30,
    "rsi_sell": 72,
    "adx_limit": 33,
    "stoploss": -0.045,
    "roi": [(0, 0.04), (180, 0.03), (360, 0.02), (720, 0.01), (1440, 0.0)],
    "leverage": 2,
    "timeframe": "15m",
    "max_trades": 3,
}


class TradingEngine:
    def __init__(self):
        self.running = False
        self.thread = None
        self.exchange = None
        self.state = {
            "balance": 0,
            "profit_total": 0,
            "profit_pct": 0,
            "trades_total": 0,
            "trades_win": 0,
            "trades_loss": 0,
            "open_positions": [],
            "closed_trades": [],
            "logs": [],
            "status": "stopped",
            "start_balance": 0,
        }
        self._load_state()

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self.state["logs"].append(entry)
        if len(self.state["logs"]) > 200:
            self.state["logs"] = self.state["logs"][-200:]
        print(entry)

    def _load_state(self):
        if STATE_PATH.exists():
            try:
                saved = json.loads(STATE_PATH.read_text())
                for k in ["trades_total", "trades_win", "trades_loss",
                          "closed_trades", "profit_total", "profit_pct"]:
                    if k in saved:
                        self.state[k] = saved[k]
            except Exception:
                pass

    def _save_state(self):
        try:
            data = {k: self.state[k] for k in
                    ["trades_total", "trades_win", "trades_loss",
                     "closed_trades", "profit_total", "profit_pct"]}
            STATE_PATH.write_text(json.dumps(data, ensure_ascii=False))
        except Exception:
            pass

    def load_config(self):
        with open(CONFIG_PATH) as f:
            return json.load(f)

    def init_exchange(self):
        cfg = self.load_config()
        params = {
            "apiKey": cfg["exchange"]["key"],
            "secret": cfg["exchange"]["secret"],
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        }
        proxy = cfg.get("exchange", {}).get("ccxt_config", {}).get("proxies", {}).get("https", "")
        if proxy:
            params["proxies"] = {"http": proxy, "https": proxy}
        self.exchange = ccxt.binance(params)
        self.exchange.load_markets()
        self.log("交易所连接成功")
        return True

    def fetch_balance(self):
        try:
            bal = self.exchange.fetch_balance()
            return float(bal.get("USDT", {}).get("free", 0))
        except Exception:
            return 0

    def set_leverage(self, pair):
        try:
            self.exchange.set_leverage(STRATEGY_PARAMS["leverage"], pair)
        except Exception:
            pass

    def get_ohlcv(self, pair, limit=120):
        try:
            data = self.exchange.fetch_ohlcv(
                pair, STRATEGY_PARAMS["timeframe"], limit=limit
            )
            closes = np.array([c[4] for c in data], dtype=float)
            highs = np.array([c[2] for c in data], dtype=float)
            lows = np.array([c[3] for c in data], dtype=float)
            volumes = np.array([c[5] for c in data], dtype=float)
            return closes, highs, lows, volumes
        except Exception as e:
            self.log(f"获取K线失败: {e}")
            return None, None, None, None

    def check_signal(self, pair):
        closes, highs, lows, volumes = self.get_ohlcv(pair)
        if closes is None or len(closes) < STRATEGY_PARAMS["bb_period"]:
            return None

        p = STRATEGY_PARAMS
        bb_upper, bb_middle, bb_lower = bbands(
            closes, period=p["bb_period"], nbdev=p["bb_std"]
        )
        rsi_vals = rsi(closes, period=p["rsi_period"])
        adx_vals = adx(highs, lows, closes, period=14)

        current = {
            "close": closes[-1],
            "bb_lower": bb_lower[-1] if not np.isnan(bb_lower[-1]) else 999999,
            "bb_upper": bb_upper[-1] if not np.isnan(bb_upper[-1]) else 0,
            "rsi": rsi_vals[-1] if not np.isnan(rsi_vals[-1]) else 50,
            "adx": adx_vals[-1] if not np.isnan(adx_vals[-1]) else 50,
        }

        if (current["close"] <= current["bb_lower"] * 1.005
                and current["rsi"] < p["rsi_buy"]
                and current["adx"] < p["adx_limit"]):
            return "buy"

        if (current["close"] >= current["bb_upper"] * 0.995
                and current["rsi"] > p["rsi_sell"]):
            return "sell"

        return None

    def get_open_positions(self):
        try:
            positions = self.exchange.fetch_positions()
            return [p for p in positions if float(p.get("contracts", 0)) > 0]
        except Exception:
            return []

    def get_position_for_pair(self, pair):
        positions = self.get_open_positions()
        for p in positions:
            if p["symbol"] == pair.replace("/", "").replace(":USDT", ""):
                return p
        return None

    def execute_buy(self, pair):
        try:
            cfg = self.load_config()
            balance = self.fetch_balance()
            self.set_leverage(pair)

            max_trades = STRATEGY_PARAMS["max_trades"]
            positions = self.get_open_positions()
            if len(positions) >= max_trades:
                return

            stake = (balance * 0.95) / max_trades
            ticker = self.exchange.fetch_ticker(pair)
            price = ticker["last"]
            amount = (stake * STRATEGY_PARAMS["leverage"]) / price
            amount = self.exchange.amount_to_precision(pair, amount)

            order = self.exchange.create_order(
                pair, "market", "buy", amount, None,
                {"positionSide": "LONG"}
            )
            self.state["trades_total"] += 1
            self.log(f"买入 {pair} 数量:{amount} 价格:{price:.4f}")
            self.state["open_positions"].append({
                "pair": pair,
                "entry_price": price,
                "amount": float(amount),
                "time": datetime.now().strftime("%m-%d %H:%M"),
            })
            return order
        except Exception as e:
            self.log(f"买入失败 {pair}: {e}")
            return None

    def execute_sell(self, pair, position):
        try:
            amount = abs(float(position.get("contracts", 0)))
            if amount <= 0:
                return
            order = self.exchange.create_order(
                pair, "market", "sell", amount, None,
                {"positionSide": "LONG"}
            )
            entry_price = float(position.get("entryPrice", 0))
            current_price = float(position.get("markPrice", 0))
            pnl_pct = (current_price - entry_price) / entry_price * 100

            self.state["closed_trades"].insert(0, {
                "pair": pair.replace(":USDT", ""),
                "pnl_pct": round(pnl_pct, 2),
                "pnl_usdt": round(float(position.get("unrealizedPnl", 0)), 2),
                "time": datetime.now().strftime("%m-%d %H:%M"),
            })
            if len(self.state["closed_trades"]) > 50:
                self.state["closed_trades"] = self.state["closed_trades"][:50]

            if pnl_pct > 0:
                self.state["trades_win"] += 1
            else:
                self.state["trades_loss"] += 1

            self.state["open_positions"] = [
                p for p in self.state["open_positions"]
                if p["pair"] != pair
            ]
            self.log(f"卖出 {pair} 盈亏:{pnl_pct:.2f}%")

            self.state["profit_total"] += float(position.get("unrealizedPnl", 0))
            bal = self.state.get("start_balance", self.state["balance"])
            if bal > 0:
                self.state["profit_pct"] = round(
                    self.state["profit_total"] / bal * 100, 2
                )
            self._save_state()
            return order
        except Exception as e:
            self.log(f"卖出失败 {pair}: {e}")
            return None

    def run_loop(self):
        self.state["status"] = "running"
        self.log("交易引擎启动")
        cfg = self.load_config()
        pairs = cfg["exchange"]["pair_whitelist"]

        try:
            self.init_exchange()
            self.state["balance"] = self.fetch_balance()
            self.state["start_balance"] = self.state["balance"]
            self.log(f"账户余额: {self.state['balance']:.2f} USDT")
        except Exception as e:
            self.log(f"交易所初始化失败: {e}")
            self.state["status"] = "error"
            return

        while self.running:
            try:
                positions = self.get_open_positions()
                open_pairs = set()
                for p in positions:
                    pair = f"{p['symbol']}/USDT:USDT"
                    open_pairs.add(pair)
                    entry = float(p.get("entryPrice", 0))
                    mark = float(p.get("markPrice", 0))
                    pnl_pct = (mark - entry) / entry * 100

                    # 止损检查
                    if pnl_pct <= STRATEGY_PARAMS["stoploss"] * 100:
                        self.log(f"触发止损 {pair} 亏损:{pnl_pct:.2f}%")
                        self.execute_sell(pair, p)
                        continue

                    # 止盈检查
                    held_mins = 0
                    for roi_min, roi_target in STRATEGY_PARAMS["roi"]:
                        if roi_min == 0 and pnl_pct >= roi_target * 100:
                            self.log(f"触发止盈 {pair} 盈利:{pnl_pct:.2f}%")
                            self.execute_sell(pair, p)
                            break

                    # 卖出信号
                    signal = self.check_signal(pair)
                    if signal == "sell":
                        self.log(f"卖出信号 {pair}")
                        self.execute_sell(pair, p)

                # 寻找入场机会
                if len(positions) < STRATEGY_PARAMS["max_trades"]:
                    for pair in pairs:
                        if pair in open_pairs:
                            continue
                        signal = self.check_signal(pair)
                        if signal == "buy":
                            self.execute_buy(pair)
                            break

                self.state["balance"] = self.fetch_balance()
                self.state["open_positions"] = [
                    {"pair": f"{p['symbol']}/USDT:USDT",
                     "entry_price": float(p.get("entryPrice", 0)),
                     "pnl_pct": round(
                         (float(p.get("markPrice", 0)) -
                          float(p.get("entryPrice", 0))) /
                         float(p.get("entryPrice", 0)) * 100, 2)}
                    for p in self.get_open_positions()
                ]

            except Exception as e:
                self.log(f"循环异常: {e}")

            time.sleep(60)

        self.state["status"] = "stopped"
        self.log("交易引擎已停止")

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.state["status"] = "stopped"
