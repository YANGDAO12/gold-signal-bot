# -*- coding: utf-8 -*-
"""
黄金信号汇总+RSI策略 - 自动扫描推送脚本
用于GitHub Actions定时运行，每30分钟扫描一次
达到开仓条件时通过Server酱推送到微信
"""
import urllib.request
import urllib.parse
import json
import time
import os

# Server酱 SendKey（从GitHub Secrets读取）
SENDKEY = os.environ.get('SERVERCHAN_KEY', '')

# 行情接口（腾讯财经）
QUOTE_URL = "https://qt.gtimg.cn/q=hf_XAU"
DAY_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh518880,day,,,250,qfq"
M60_KLINE_URL = "https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=sh518880,m60,,300&_var=m60_today"

def fetch_url(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('gbk', errors='ignore')
    except Exception as e:
        print(f"获取URL失败: {e}")
        return None

def get_live_price():
    data = fetch_url(QUOTE_URL)
    if not data:
        return None
    try:
        parts = data.split('"')
        if len(parts) >= 2:
            fields = parts[1].split('~')
            if len(fields) >= 4:
                return float(fields[3])
    except Exception as e:
        print(f"解析实时价格失败: {e}")
    return None

def parse_kline(data_str, is_minute=False):
    try:
        if is_minute:
            json_str = data_str.split('=', 1)[1].strip()
            if json_str.endswith(';'):
                json_str = json_str[:-1]
            data = json.loads(json_str)
            stock_data = data.get('data', {}).get('sh518880', {})
            klines = stock_data.get('m60', [])
            if not klines:
                klines = stock_data.get('qtimeline', [])
        else:
            data = json.loads(data_str)
            stock_data = data.get('data', {}).get('sh518880', {})
            klines = stock_data.get('day', [])
            if not klines:
                klines = stock_data.get('qfqday', [])
        
        result = []
        for k in klines:
            if len(k) >= 5:
                result.append({
                    'date': k[0],
                    'open': float(k[1]),
                    'close': float(k[2]),
                    'high': float(k[3]),
                    'low': float(k[4]),
                    'volume': float(k[5]) if len(k) >= 6 else 0
                })
        return result
    except Exception as e:
        print(f"解析K线失败: {e}")
        return []

def calc_ma(klines, period):
    if len(klines) < period:
        return None
    return sum(k['close'] for k in klines[-period:]) / period

def calc_rsi(klines, period=14):
    if len(klines) < period + 1:
        return 50
    gains = []
    losses = []
    for i in range(len(klines) - period, len(klines)):
        change = klines[i]['close'] - klines[i-1]['close']
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_atr(klines, period=14):
    if len(klines) < period + 1:
        return 0
    trs = []
    for i in range(len(klines) - period, len(klines)):
        tr = max(
            klines[i]['high'] - klines[i]['low'],
            abs(klines[i]['high'] - klines[i-1]['close']),
            abs(klines[i]['low'] - klines[i-1]['close'])
        )
        trs.append(tr)
    return sum(trs) / len(trs)

def check_trend(klines):
    if len(klines) < 200:
        return 'wait'
    ma20 = calc_ma(klines, 20)
    ma60 = calc_ma(klines, 60)
    ma200 = calc_ma(klines, 200)
    cur = klines[-1]['close']
    if ma20 and ma60 and ma200:
        if ma20 > ma60 > ma200 and cur > ma20:
            return 'buy'
        elif ma20 < ma60 < ma200 and cur < ma20:
            return 'sell'
    return 'wait'

def send_wechat(title, desp):
    if not SENDKEY:
        print("未配置SERVERCHAN_KEY，跳过推送")
        return False
    try:
        url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
        data = urllib.parse.urlencode({'title': title, 'desp': desp}).encode()
        req = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            if result.get('code') == 0:
                print("微信推送成功")
                return True
            else:
                print(f"微信推送失败: {result}")
                return False
    except Exception as e:
        print(f"微信推送异常: {e}")
        return False

def main():
    print("=" * 50)
    print(f"黄金信号扫描 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # 1. 获取实时价格
    live_price = get_live_price()
    if live_price:
        print(f"伦敦金实时价格: ${live_price:.2f}")
    else:
        print("无法获取实时价格，用ETF价格换算")
        live_price = 0
    
    # 2. 获取日K线
    print("\n获取日K线...")
    day_data = fetch_url(DAY_KLINE_URL)
    day_klines = parse_kline(day_data, is_minute=False)
    print(f"日K线数量: {len(day_klines)}")
    if len(day_klines) < 200:
        print("日K线数据不足，退出")
        return
    day_trend = check_trend(day_klines)
    print(f"日K趋势: {day_trend}")
    
    # 3. 获取60分钟K线
    print("\n获取60分钟K线...")
    m60_data = fetch_url(M60_KLINE_URL)
    m60_klines = parse_kline(m60_data, is_minute=True)
    print(f"60分钟K线数量: {len(m60_klines)}")
    if len(m60_klines) < 200:
        print("60分钟K线数据不足，退出")
        return
    m60_trend = check_trend(m60_klines)
    m60_rsi = calc_rsi(m60_klines, 14)
    m60_atr_etf = calc_atr(m60_klines, 14)
    print(f"60分钟趋势: {m60_trend}")
    print(f"60分钟RSI(14): {m60_rsi:.1f}")
    
    # 4. 4小时趋势
    print("\n判断4小时趋势...")
    h4_klines = []
    for i in range(0, len(m60_klines) - 3, 4):
        group = m60_klines[i:i+4]
        h4_klines.append({
            'date': group[0]['date'],
            'open': group[0]['open'],
            'close': group[-1]['close'],
            'high': max(k['high'] for k in group),
            'low': min(k['low'] for k in group),
            'volume': sum(k['volume'] for k in group)
        })
    h4_trend = check_trend(h4_klines)
    print(f"4小时趋势: {h4_trend}")
    
    # 5. 价格换算（ETF人民币 → 伦敦金美元）
    # 华安黄金ETF 518880 约对应0.01克黄金，人民币计价
    # 伦敦金是美元/盎司，需要换算
    etf_price = m60_klines[-1]['close']
    if live_price > 0 and etf_price > 0:
        convert_ratio = live_price / etf_price
    else:
        # 默认换算比例：根据实际价格校准
        # ETF约8.8元 ↔ 伦敦金约4300美元，比例约487
        convert_ratio = 487
        live_price = etf_price * convert_ratio
    m60_atr = m60_atr_etf * convert_ratio
    print(f"\nETF价格: {etf_price:.4f}元, 伦敦金: ${live_price:.2f}, ATR: ${m60_atr:.2f}")
    
    # 6. 开仓条件判断
    print("\n" + "=" * 50)
    print("开仓条件判断:")
    print(f"  日K: {day_trend}, 4H: {h4_trend}, 1H: {m60_trend}")
    print(f"  1H RSI: {m60_rsi:.1f}")
    
    big_trend_align = (day_trend != 'wait') and (day_trend == h4_trend) and (day_trend == m60_trend)
    print(f"  大周期共振: {'是' if big_trend_align else '否'}")
    
    if not big_trend_align:
        print("\n大周期未共振，不开仓")
        return
    
    direction = day_trend
    rsi_pass = True
    if direction == 'buy' and m60_rsi > 54:
        rsi_pass = False
    elif direction == 'sell' and m60_rsi < 46:
        rsi_pass = False
    
    if not rsi_pass:
        print(f"\nRSI不达标（当前{m60_rsi:.1f}），不开仓")
        return
    
    # 7. 计算交易计划
    entry = live_price
    atr = m60_atr if m60_atr > 0 else 15
    if direction == 'buy':
        stop = entry - atr * 3
        tp = entry + atr * 7
    else:
        stop = entry + atr * 3
        tp = entry - atr * 7
    
    print(f"\n✅ 达到开仓条件！")
    print(f"  方向: {'做多' if direction == 'buy' else '做空'}")
    print(f"  入场: ${entry:.2f}, 止损: ${stop:.2f}, 止盈: ${tp:.2f}")
    
    # 8. 发送微信推送
    is_buy = direction == 'buy'
    title = f"🚨 {'做多' if is_buy else '做空'}信号 · 黄金 ${entry:.2f}"
    desp = f"""## {'📈 做多信号' if is_buy else '📉 做空信号'}

**品种**：伦敦金现货（XAUUSD）
**策略**：大周期共振 + RSI过滤
**时间**：{time.strftime('%Y-%m-%d %H:%M:%S')}

### 趋势确认
| 周期 | 趋势 |
|------|------|
| 日K | {'多头' if day_trend=='buy' else '空头'} |
| 4小时 | {'多头' if h4_trend=='buy' else '空头'} |
| 1小时 | {'多头' if m60_trend=='buy' else '空头'} |

### 指标
- 1H RSI(14): {m60_rsi:.1f} ✅ 达标
- 1H ATR(14): ${atr:.2f}

### 交易计划
| 项目 | 价格 |
|------|------|
| 入场 | ${entry:.2f} |
| 止损 | ${stop:.2f}（3ATR） |
| 止盈 | ${tp:.2f}（7ATR） |
| 盈亏比 | 1:{7/3:.2f} |

### 操作建议
1. 确认当前价在入场价附近
2. 设置好止损和止盈
3. 单笔风险不超过账户1.5%
4. 严格执行止损，不扛单
5. 平仓后24小时内不开新仓

---
*裸K黄金终端 · 回测验证版*
*5年回测：胜率35.2%，收益+75.5%，回撤9.1%*
*仅供参考，不构成投资建议*"""
    
    send_wechat(title, desp)
    print("\n已发送微信推送")

if __name__ == '__main__':
    main()
