"""纯 Python 技术指标 — 不依赖 TA-Lib，可在 Android 上直接运行"""
import numpy as np


def sma(data, period):
    """简单移动平均"""
    out = np.full_like(data, np.nan)
    if len(data) < period:
        return out
    cumsum = np.cumsum(np.insert(data, 0, 0))
    out[period - 1:] = (cumsum[period:] - cumsum[:-period]) / period
    return out


def ema(data, period):
    """指数移动平均"""
    out = np.full_like(data, np.nan)
    if len(data) < period:
        return out
    multiplier = 2.0 / (period + 1)
    out[period - 1] = np.mean(data[:period])
    for i in range(period, len(data)):
        out[i] = (data[i] - out[i - 1]) * multiplier + out[i - 1]
    return out


def rsi(data, period=14):
    """相对强弱指标"""
    out = np.full_like(data, np.nan)
    if len(data) < period + 1:
        return out
    delta = np.diff(data)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = np.mean(gain[:period])
    avg_loss = np.mean(loss[:period])
    if avg_loss == 0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100.0 - (100.0 / (1.0 + rs))
    for i in range(period + 1, len(data)):
        avg_gain = (avg_gain * (period - 1) + gain[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + loss[i - 1]) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            out[i] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return out


def bbands(data, period=20, nbdev=2.0):
    """布林带"""
    mid = sma(data, period)
    std = np.full_like(data, np.nan)
    for i in range(period - 1, len(data)):
        std[i] = np.std(data[i - period + 1:i + 1], ddof=1)
    upper = mid + nbdev * std
    lower = mid - nbdev * std
    return upper, mid, lower


def atr(high, low, close, period=14):
    """平均真实波幅"""
    out = np.full_like(close, np.nan)
    if len(close) < period + 1:
        return out
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(
            np.abs(high[1:] - close[:-1]),
            np.abs(low[1:] - close[:-1])
        )
    )
    out[period] = np.mean(tr[:period])
    for i in range(period + 1, len(close)):
        out[i] = (out[i - 1] * (period - 1) + tr[i - 1]) / period
    return out


def adx(high, low, close, period=14):
    """平均趋向指数"""
    out = np.full_like(close, np.nan)
    if len(close) < period * 2:
        return out
    tr = atr(high, low, close, period)
    up = high[1:] - high[:-1]
    down = low[:-1] - low[1:]
    plus_dm = np.where((up > down) & (up > 0), up, 0)
    minus_dm = np.where((down > up) & (down > 0), down, 0)
    plus_di_raw = np.full_like(close, np.nan)
    minus_di_raw = np.full_like(close, np.nan)
    plus_di_raw[period] = 100 * np.sum(plus_dm[:period]) / tr[period] if tr[period] > 0 else 0
    minus_di_raw[period] = 100 * np.sum(minus_dm[:period]) / tr[period] if tr[period] > 0 else 0
    for i in range(period + 1, len(close)):
        plus_di_raw[i] = (plus_di_raw[i - 1] * (period - 1) + (
            100 * plus_dm[i - 1] / tr[i] if tr[i] > 0 else 0)) / period
        minus_di_raw[i] = (minus_di_raw[i - 1] * (period - 1) + (
            100 * minus_dm[i - 1] / tr[i] if tr[i] > 0 else 0)) / period
    dx = np.full_like(close, np.nan)
    for i in range(period, len(close)):
        if plus_di_raw[i] + minus_di_raw[i] > 0:
            dx[i] = 100 * abs(plus_di_raw[i] - minus_di_raw[i]) / (plus_di_raw[i] + minus_di_raw[i])
    out[period * 2 - 1] = np.nanmean(dx[period:period * 2])
    for i in range(period * 2, len(close)):
        out[i] = (out[i - 1] * (period - 1) + dx[i]) / period
    return out
