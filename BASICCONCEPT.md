## 1. Algorithmic Trading คืออะไร

**Algorithmic Trading** คือการใช้ “กฎที่เขียนเป็นระบบ” ให้คอมพิวเตอร์ตัดสินใจซื้อขายแทนเรา เช่น

> ถ้าเส้นค่าเฉลี่ย 20 วันตัดขึ้นเหนือเส้นค่าเฉลี่ย 50 วัน → ซื้อ
> ถ้าราคาหลุด Stop Loss 2% → ขาย
> ถ้า volatility สูงเกินไป → ลดขนาด position

พูดง่าย ๆ คือเปลี่ยนจาก

> “รู้สึกว่ากราฟน่าจะขึ้น”

เป็น

> “ถ้าเงื่อนไข A, B, C เป็นจริง ให้ทำ X ด้วยขนาด Y และมีความเสี่ยง Z”

หัวใจของ algo trading ไม่ใช่การทำนายอนาคตให้แม่น 100% แต่คือการสร้างระบบที่มี **edge**, คุมความเสี่ยงได้, และทดสอบซ้ำได้

---

# 2. โครงสร้างพื้นฐานของระบบ Algorithmic Trading

ระบบเทรดเชิงอัลกอริทึมทั่วไปมักมี 6 ส่วนหลัก

```text
Market Data
    ↓
Feature / Indicator
    ↓
Signal Generation
    ↓
Risk Management
    ↓
Order Execution
    ↓
Performance Evaluation
```

หรือแปลเป็นภาษาคน:

1. เอาข้อมูลราคามา
2. คำนวณสิ่งที่ใช้ตัดสินใจ
3. สร้างสัญญาณซื้อ/ขาย
4. คุมความเสี่ยง
5. ส่งคำสั่งซื้อขาย
6. วัดผลว่ารอดหรือโดนตลาดตบ

---

# 3. Market Data: ข้อมูลที่ใช้

ข้อมูลพื้นฐานที่สุดคือ **OHLCV**

| ตัวแปร | ความหมาย          |
| ------ | ----------------- |
| Open   | ราคาเปิดของแท่ง   |
| High   | ราคาสูงสุดของแท่ง |
| Low    | ราคาต่ำสุดของแท่ง |
| Close  | ราคาปิดของแท่ง    |
| Volume | ปริมาณการซื้อขาย  |

ตัวอย่างข้อมูล:

| Time  | Open | High | Low | Close | Volume |
| ----- | ---: | ---: | --: | ----: | -----: |
| 09:00 |  100 |  105 |  99 |   104 |   1200 |
| 10:00 |  104 |  108 | 103 |   107 |   1500 |
| 11:00 |  107 |  109 | 101 |   102 |   2100 |

ข้อมูลพวกนี้เอาไปสร้าง indicator, feature, signal ได้

---

# 4. Signal คืออะไร

**Signal** คือสัญญาณที่บอกว่าระบบควรทำอะไร

ตัวอย่าง:

| Signal | ความหมาย          |
| ------ | ----------------- |
| `1`    | Buy / Long        |
| `-1`   | Sell / Short      |
| `0`    | Hold / Do nothing |

เช่น

```python
if fast_ma > slow_ma:
    signal = 1
elif fast_ma < slow_ma:
    signal = -1
else:
    signal = 0
```

นี่คือกฎง่าย ๆ แต่ในระบบจริง Signal ไม่ควรถูกใช้ลอย ๆ ต้องมี risk management ประกบเสมอ ไม่งั้นเหมือนขับรถด้วยความเร็ว 200 แต่ไม่มีเบรก มีแค่ศรัทธา

---

# 5. Concept สำคัญ: Edge

**Edge** คือความได้เปรียบเชิงสถิติของระบบ

ไม่จำเป็นต้องชนะบ่อยเสมอไป ขอแค่ผลรวมระยะยาวเป็นบวก

ตัวอย่าง:

ระบบ A:

* Win rate: 40%
* กำไรเฉลี่ยต่อครั้งที่ชนะ: +$300
* ขาดทุนเฉลี่ยต่อครั้งที่แพ้: -$100

Expected Value:

```text
EV = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
EV = (0.4 × 300) - (0.6 × 100)
EV = 120 - 60
EV = +60
```

ระบบนี้แพ้บ่อยกว่าชนะ แต่ยังมีกำไรคาดหวังเป็นบวก

ในทางกลับกัน ระบบที่ชนะ 80% ก็เจ๊งได้ ถ้าแพ้ทีเดียวล้างกำไรทั้งเดือน แบบพวก “เก็บเหรียญหน้ารถสิบล้อ”

---

# 6. Strategy Example 1: Moving Average Crossover

กลยุทธ์คลาสสิกที่สุด

## แนวคิด

ใช้ค่าเฉลี่ยเคลื่อนที่ 2 เส้น:

* Fast MA เช่น 20 วัน
* Slow MA เช่น 50 วัน

กฎ:

```text
ถ้า Fast MA ตัดขึ้นเหนือ Slow MA → Buy
ถ้า Fast MA ตัดลงใต้ Slow MA → Sell
```

## ตัวอย่าง

| Time  | Close | MA20 | MA50 | Signal |
| ----- | ----: | ---: | ---: | ------ |
| Day 1 |   100 |   98 |  101 | Hold   |
| Day 2 |   105 |  102 |  101 | Buy    |
| Day 3 |   108 |  104 |  102 | Hold   |
| Day 4 |    99 |  101 |  103 | Sell   |

## Pseudocode

```python
data["ma_fast"] = data["close"].rolling(20).mean()
data["ma_slow"] = data["close"].rolling(50).mean()

data["signal"] = 0
data.loc[data["ma_fast"] > data["ma_slow"], "signal"] = 1
data.loc[data["ma_fast"] < data["ma_slow"], "signal"] = -1
```

## จุดแข็ง

* เข้าใจง่าย
* เหมาะกับตลาดมี trend
* ใช้เป็น baseline ได้ดี

## จุดอ่อน

* แพ้หนักในตลาด sideway
* สัญญาณช้า
* โดนหลอกบ่อยตอนราคาสวิง

---

# 7. Strategy Example 2: Mean Reversion

## แนวคิด

ราคาที่ขึ้น/ลงแรงเกินไป อาจเด้งกลับเข้าค่าเฉลี่ย

ตัวอย่างง่าย ๆ ใช้ RSI:

* RSI < 30 → Oversold → อาจ Buy
* RSI > 70 → Overbought → อาจ Sell

```text
ถ้า RSI ต่ำมาก → ราคาถูกขายมากเกินไป → หาจังหวะซื้อ
ถ้า RSI สูงมาก → ราคาถูกซื้อมากเกินไป → หาจังหวะขาย
```

## ตัวอย่างกฎ

```python
if rsi < 30:
    signal = 1
elif rsi > 70:
    signal = -1
else:
    signal = 0
```

## จุดแข็ง

* ใช้ได้ดีในตลาด sideway
* เข้าเร็วกว่า trend-following
* Risk/reward อาจดีถ้าจับจุดกลับตัวแม่น

## จุดอ่อน

* ตลาดมี trend แรงจะโดนลากยาว
* “ถูกแล้ว” ยังถูกได้อีก
* Oversold ไม่ได้แปลว่าต้องขึ้นทันที

Mean reversion คือการยืนขวางรถไฟโดยหวังว่ารถไฟจะเปลี่ยนใจ ดังนั้นต้องมี stop loss เสมอ

---

# 8. Strategy Example 3: Breakout

## แนวคิด

ถ้าราคาทะลุกรอบสำคัญ อาจเกิด momentum ตามมา

ตัวอย่าง:

```text
ถ้าราคาปิดสูงกว่า High 20 วันล่าสุด → Buy
ถ้าราคาปิดต่ำกว่า Low 20 วันล่าสุด → Sell
```

## ตัวอย่าง

```python
data["rolling_high"] = data["high"].rolling(20).max()
data["rolling_low"] = data["low"].rolling(20).min()

if close > rolling_high:
    signal = 1
elif close < rolling_low:
    signal = -1
```

## จุดแข็ง

* จับ trend ใหญ่ได้
* เหมาะกับตลาดที่มี momentum
* ใช้กับหลาย asset ได้

## จุดอ่อน

* False breakout เยอะ
* เข้าแพง
* ต้องทน drawdown ได้

---

# 9. Risk Management: ส่วนที่สำคัญกว่าการเข้าไม้

มือใหม่ชอบถามว่า

> “เข้าตรงไหนดี?”

แต่มืออาชีพจะถามว่า

> “ถ้าผิด จะเสียเท่าไหร่?”

Risk management คือหัวใจของระบบเทรด

## 9.1 Position Sizing

คือการกำหนดว่าจะซื้อขายขนาดเท่าไหร่

ตัวอย่าง:

* พอร์ต = $10,000
* ยอมเสี่ยงต่อ trade = 1%
* ขาดทุนสูงสุดที่ยอมรับได้ = $100
* Stop loss ห่างจาก entry = $2

Position size:

```text
Position Size = Risk Amount / Stop Distance
Position Size = 100 / 2
Position Size = 50 units
```

แปลว่าเปิดได้ 50 units

ถ้าโดน stop loss จะเสียประมาณ $100

---

## 9.2 Stop Loss

Stop loss คือจุดที่ระบบยอมรับว่า “ผิดทางแล้ว ออก”

ตัวอย่าง:

```text
Entry = 100
Stop Loss = 98
Take Profit = 106
```

Risk = 2
Reward = 6
Risk:Reward = 1:3

ถ้าระบบนี้ชนะมากกว่า 25% ก็มีโอกาสคุ้มในเชิง expected value

---

## 9.3 Take Profit

Take profit คือจุดปิดกำไร

แต่ไม่จำเป็นต้องใช้แบบ fixed เสมอไป อาจใช้:

| วิธี          | ตัวอย่าง                  |
| ------------- | ------------------------- |
| Fixed TP      | กำไร 3% แล้วปิด           |
| Risk Multiple | ได้ 2R แล้วปิด            |
| Trailing Stop | เลื่อน stop ตามราคา       |
| Signal Exit   | ออกเมื่อเกิดสัญญาณตรงข้าม |
| Time Exit     | ถือครบ 24 แท่งแล้วปิด     |

---

# 10. Backtesting คืออะไร

**Backtesting** คือการเอากลยุทธ์ไปทดสอบกับข้อมูลในอดีต

คำถามคือ:

> ถ้าเราใช้กฎนี้ในอดีต มันจะรอดไหม?

ตัวอย่าง flow:

```text
เริ่มด้วยเงิน $10,000
อ่านข้อมูลแท่งที่ 1
คำนวณ signal
ถ้า buy → เปิด position
แท่งถัดไป → เช็ก TP / SL / exit
บันทึกกำไรขาดทุน
ทำซ้ำจนจบข้อมูล
สรุปผล
```

## Metrics ที่ควรดู

| Metric             | ความหมาย                                    |
| ------------------ | ------------------------------------------- |
| Total Return       | ผลตอบแทนรวม                                 |
| Win Rate           | เปอร์เซ็นต์การชนะ                           |
| Profit Factor      | กำไรรวม / ขาดทุนรวม                         |
| Max Drawdown       | พอร์ตเคยร่วงหนักสุดเท่าไหร่                 |
| Sharpe Ratio       | ผลตอบแทนเทียบความผันผวน                     |
| Expectancy         | ค่าเฉลี่ยกำไร/ขาดทุนต่อ trade               |
| Avg Win / Avg Loss | กำไรเฉลี่ยตอนชนะ เทียบกับขาดทุนเฉลี่ยตอนแพ้ |
| Number of Trades   | จำนวน trade มากพอไหม                        |

**Number of Trades สำคัญมาก**
ถ้า backtest มีแค่ 10 trades แล้วกำไร อย่าเพิ่งดีใจ อาจเป็นดวง ไม่ใช่ edge

ตลาดไม่ได้แพ้เรา แค่ยังไม่เริ่มจริงจังกับการตีหัวเรา

---

# 11. Common Backtesting Mistakes

## 11.1 Lookahead Bias

ใช้ข้อมูลอนาคตโดยไม่รู้ตัว

ตัวอย่างผิด:

```python
data["signal"] = data["close"].shift(-1) > data["close"]
```

นี่คือการใช้ close ของอนาคตมาสร้าง signal ปัจจุบัน

ผล backtest จะเทพเหมือนมีญาณทิพย์ แต่พอเทรดจริงจะกลายเป็นญาณทิ้ง

---

## 11.2 Overfitting

ปรับระบบให้เข้ากับอดีตมากเกินไป

เช่นลอง parameter 1,000 แบบ แล้วเลือกอันที่กำไรที่สุด

```text
MA 17.3 กับ RSI 42.8 และ TP 2.37% ใช้ได้ดีที่สุดใน XAUUSD ช่วง 2022-2024
```

ดูเหมือนแม่น แต่จริง ๆ อาจแค่จำ noise

วิธีลด overfitting:

* แยก train/test
* ใช้ walk-forward validation
* ทดสอบหลายช่วงตลาด
* ทดสอบหลายสินทรัพย์
* อย่าใช้ parameter แปลกเกินไป
* อย่าเชื่อ equity curve ที่สวยเกินมนุษย์

---

## 11.3 Ignoring Costs

ค่าธรรมเนียม, spread, slippage สำคัญมาก

กลยุทธ์ที่กำไรเล็ก ๆ ต่อ trade อาจเจ๊งทันทีเมื่อใส่ cost จริง

ตัวอย่าง:

```text
กำไรเฉลี่ยต่อ trade = $3
ค่าธรรมเนียม + spread + slippage = $4
```

ระบบนี้ไม่ได้เทรด มันบริจาคเงินให้ตลาดอย่างมีระบบ

---

## 11.4 Survivorship Bias

ใช้ข้อมูลเฉพาะสินทรัพย์ที่รอดมาแล้ว เช่นหุ้นที่ยังอยู่ในดัชนีปัจจุบัน แต่ไม่รวมบริษัทที่เจ๊งไปแล้ว

ทำให้ผล backtest ดูดีเกินจริง

---

# 12. Execution: จาก Signal ไปเป็น Order

เมื่อระบบมี signal แล้ว ต้องแปลงเป็นคำสั่งซื้อขาย

ประเภท order สำคัญ:

| Order Type   | ความหมาย                          |
| ------------ | --------------------------------- |
| Market Order | ซื้อ/ขายทันทีที่ราคาตลาด          |
| Limit Order  | ซื้อ/ขายที่ราคาที่กำหนดหรือดีกว่า |
| Stop Order   | Trigger เมื่อราคาถึงจุดหนึ่ง      |
| Stop Loss    | คำสั่งปิดขาดทุน                   |
| Take Profit  | คำสั่งปิดกำไร                     |

## ตัวอย่าง

```text
Signal: Buy
Entry: Market
Stop Loss: 2% below entry
Take Profit: 4% above entry
Risk per trade: 1% of portfolio
```

ระบบจริงควรมี state เช่น:

```text
No Position
Long Position
Short Position
Waiting for Exit
Order Pending
Order Rejected
```

ไม่ใช่แค่ “เห็น buy ก็ buy ทุกแท่ง” เพราะแบบนั้นไม่ได้เทรด เป็นการ spam order ให้ broker งงเล่น

---

# 13. Example: ระบบเทรดง่าย ๆ แบบครบวงจร

สมมติใช้กลยุทธ์ MA Crossover + Risk Management

## Rules

```text
1. ถ้า MA20 > MA50 และยังไม่มี position → Buy
2. Stop Loss = 2%
3. Take Profit = 4%
4. Risk per trade = 1% ของพอร์ต
5. ถ้า MA20 < MA50 → ปิด Long
```

## Pseudocode

```python
capital = 10000
risk_per_trade = 0.01
position = None

for candle in data:
    ma20 = calculate_ma20()
    ma50 = calculate_ma50()
    price = candle.close

    if position is None:
        if ma20 > ma50:
            risk_amount = capital * risk_per_trade
            stop_price = price * 0.98
            take_profit = price * 1.04

            stop_distance = price - stop_price
            size = risk_amount / stop_distance

            position = {
                "entry": price,
                "size": size,
                "stop": stop_price,
                "tp": take_profit
            }

    else:
        if candle.low <= position["stop"]:
            loss = (position["stop"] - position["entry"]) * position["size"]
            capital += loss
            position = None

        elif candle.high >= position["tp"]:
            profit = (position["tp"] - position["entry"]) * position["size"]
            capital += profit
            position = None

        elif ma20 < ma50:
            pnl = (price - position["entry"]) * position["size"]
            capital += pnl
            position = None
```

นี่คือ skeleton ที่ใกล้เคียงกับระบบจริงมากกว่าการแค่สร้าง signal

---

# 14. Difference: Rule-Based vs Machine Learning Trading

## Rule-Based Trading

ใช้กฎชัดเจน เช่น

```text
ถ้า RSI < 30 → Buy
```

ข้อดี:

* เข้าใจง่าย
* Debug ง่าย
* รู้ว่าทำไมเข้า trade
* เหมาะสำหรับเริ่มต้น

ข้อเสีย:

* อาจแข็งเกินไป
* ปรับตัวกับตลาดยาก
* Edge อาจหายเมื่อ regime เปลี่ยน

---

## Machine Learning Trading

ใช้โมเดลเรียนรู้ pattern จากข้อมูล เช่น

```text
input: OHLCV + indicators + volatility + trend features
output: probability ว่าราคาจะขึ้น/ลง
```

ตัวอย่าง target:

```text
1 = ราคาถึง Take Profit ก่อน Stop Loss
0 = ราคาถึง Stop Loss ก่อน Take Profit
```

หรือแบบ regression:

```text
ทำนาย next_return
ทำนาย next_high / next_low / next_close
```

ข้อดี:

* จับ relation ที่ซับซ้อนได้
* ใช้ feature จำนวนมากได้
* เหมาะกับระบบที่มีข้อมูลเยอะ

ข้อเสีย:

* Overfit ง่ายมาก
* อธิบายยาก
* ต้องจัดการ data leakage ดีมาก
* โมเดลแม่นแต่เทรดเจ๊งได้ ถ้า risk/execution แย่

ประโยคสำคัญ:

> ML model ไม่ใช่ trading system
> มันเป็นแค่ส่วนหนึ่งของ trading system

โมเดลอาจทำนายถูก 60% แต่พอร์ตเจ๊งได้
หรือทำนายถูก 45% แต่พอร์ตกำไรได้ ถ้า risk/reward ดี

---

# 15. Timeframe สำคัญยังไง

| Timeframe      | ลักษณะ                            |
| -------------- | --------------------------------- |
| Tick / Seconds | เร็วมาก แข่ง latency สูง          |
| 1m / 5m        | noise เยอะ ค่า cost มีผลสูง       |
| 15m / 30m      | สมดุลกว่า เหมาะกับ intraday       |
| 1H / 4H        | signal น้อยลง แต่ noise ลดลง      |
| Daily          | เหมาะกับ swing / portfolio system |

มือใหม่ไม่ควรเริ่มที่ timeframe ต่ำมาก เพราะค่า spread, slippage, noise จะกินระบบง่าย

โดยเฉพาะตลาด Forex/Gold ถ้าไปเล่น M1 โดยไม่มี execution ดี ๆ ระบบจะกลายเป็นอาหารปลาเร็วมาก

---

# 16. Concepts สำคัญที่ควรรู้

## 16.1 Trend Following

เชื่อว่า “ราคาที่กำลังไปทางหนึ่ง มีโอกาสไปต่อ”

ตัวอย่าง:

* Moving Average
* Breakout
* Donchian Channel
* Momentum

เหมาะกับตลาดที่มี trend ชัด

---

## 16.2 Mean Reversion

เชื่อว่า “ราคาที่เบี่ยงจากค่าเฉลี่ยมากเกินไป จะกลับเข้าหาค่าเฉลี่ย”

ตัวอย่าง:

* RSI
* Bollinger Bands
* Z-score
* Pair Trading

เหมาะกับตลาด sideway หรือสินทรัพย์ที่มี mean-reverting behavior

---

## 16.3 Momentum

สินทรัพย์ที่ขึ้นแรงอาจขึ้นต่อ สินทรัพย์ที่ลงแรงอาจลงต่อ

ตัวอย่าง:

```text
ถ้า return 20 วันที่ผ่านมาสูง → Buy
ถ้า return 20 วันที่ผ่านมาต่ำ → Sell
```

---

## 16.4 Volatility

Volatility คือความผันผวน

ใช้ทำอะไรได้บ้าง:

* วัดความเสี่ยง
* ตั้ง stop loss
* ปรับ position size
* กรองช่วงตลาด
* ตรวจ regime

ตัวอย่าง:

```text
ถ้า ATR สูงมาก → ลด position size
ถ้า ATR ต่ำมาก → รอ breakout
```

---

## 16.5 Market Regime

ตลาดไม่ได้มีนิสัยเดียวตลอดเวลา

บางช่วง:

* Trending
* Sideway
* High volatility
* Low volatility
* Crisis
* Recovery

กลยุทธ์หนึ่งอาจดีใน regime หนึ่ง แต่พังในอีก regime

เช่น:

| Regime          | Strategy ที่มักเหมาะ         |
| --------------- | ---------------------------- |
| Strong trend    | Trend following              |
| Sideway         | Mean reversion               |
| High volatility | Breakout / volatility filter |
| Low volatility  | Range strategy / wait mode   |

---

# 17. ตัวอย่าง Strategy แบบมี Regime Filter

แทนที่จะใช้ MA crossover ตลอดเวลา อาจเพิ่มตัวกรอง volatility

```text
ถ้า volatility สูงเกินไป → ไม่เทรด
ถ้า volatility ปกติ และ MA20 > MA50 → Buy
```

ตัวอย่าง:

```python
if atr_percent > 0.03:
    signal = 0
elif ma20 > ma50:
    signal = 1
else:
    signal = 0
```

แนวคิดคือบางช่วงตลาดมันมั่วเกิน ระบบควรรู้จัก “ไม่เล่น”

การไม่เทรดก็เป็น position หนึ่ง และบางครั้งเป็น position ที่ฉลาดที่สุด

---

# 18. Performance Metrics ที่ควรเข้าใจจริง ๆ

## 18.1 Win Rate

เปอร์เซ็นต์การชนะ

```text
Win Rate = Winning Trades / Total Trades
```

แต่ห้ามดูตัวนี้เดี่ยว ๆ

ระบบ win rate 80% อาจเจ๊ง
ระบบ win rate 35% อาจรวย

---

## 18.2 Profit Factor

```text
Profit Factor = Gross Profit / Gross Loss
```

ตัวอย่าง:

```text
Gross Profit = $5000
Gross Loss = $2500
Profit Factor = 2.0
```

โดยทั่วไป:

| Profit Factor | ความหมายคร่าว ๆ            |
| ------------- | -------------------------- |
| < 1.0         | ขาดทุน                     |
| 1.0 - 1.2     | บางมาก                     |
| 1.2 - 1.5     | พอมี edge                  |
| 1.5 - 2.0     | ดี                         |
| > 2.0         | ดีมาก แต่ต้องระวัง overfit |

---

## 18.3 Max Drawdown

การร่วงหนักสุดของพอร์ตจากจุดสูงสุด

ตัวอย่าง:

```text
พอร์ตขึ้นไป $12,000
จากนั้นร่วงเหลือ $9,000
Max Drawdown = 25%
```

Drawdown สำคัญมาก เพราะระบบที่กำไรเยอะ แต่ drawdown 70% อาจไม่มีมนุษย์คนไหนทนใช้มันไหว ยกเว้นเป็นหินหรือเป็น backtest report

---

## 18.4 Expectancy

ค่าเฉลี่ยกำไรต่อ trade

```text
Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
```

นี่สำคัญกว่า win rate

ตัวอย่าง:

```text
Win Rate = 45%
Avg Win = $200
Avg Loss = $100

Expectancy = (0.45 × 200) - (0.55 × 100)
Expectancy = 90 - 55
Expectancy = $35
```

แปลว่าเฉลี่ยแล้วระบบคาดหวังกำไร $35 ต่อ trade

---

# 19. Minimum Viable Trading System

ถ้าจะเริ่มทำ algo trading จริง ระบบขั้นต่ำควรมี:

```text
1. Data Loader
2. Feature Engineering
3. Signal Generator
4. Backtester
5. Risk Manager
6. Performance Report
7. Trade Logger
```

โครงสร้างโปรเจกต์แบบง่าย:

```text
algo_trading/
│
├── data/
│   └── XAUUSD_H1.csv
│
├── src/
│   ├── data_loader.py
│   ├── indicators.py
│   ├── strategy.py
│   ├── risk.py
│   ├── backtester.py
│   └── report.py
│
├── notebooks/
│   └── research.ipynb
│
└── main.py
```

---

# 20. ตัวอย่าง Workflow สำหรับเริ่ม Research

## Step 1: ตั้งสมมติฐาน

ไม่ใช่เริ่มจาก “ลอง indicator นี้สิ”

แต่ควรเริ่มจาก hypothesis เช่น:

```text
ตลาด XAUUSD ใน H1 มี momentum หลัง breakout จากกรอบ 20 แท่ง
```

## Step 2: แปลงเป็นกฎ

```text
ถ้า close > high สูงสุดของ 20 แท่งก่อนหน้า → Buy
SL = 1.5 × ATR
TP = 3 × ATR
```

## Step 3: Backtest

ทดสอบกับข้อมูลเก่า

## Step 4: ใส่ cost

* spread
* commission
* slippage

## Step 5: Walk-forward Test

แบ่งข้อมูลเป็นหลายช่วง เช่น

```text
Train: 2020-2021
Test: 2022

Train: 2021-2022
Test: 2023

Train: 2022-2023
Test: 2024
```

## Step 6: Evaluate

ดูว่า performance เสถียรไหม ไม่ใช่กำไรแค่ช่วงเดียว

## Step 7: Paper Trade

ทดลองกับบัญชีจำลองหรือ live ขนาดเล็ก

## Step 8: Deploy

ค่อยเอาเงินจริงเข้าแบบ conservative

---

# 21. Example: Breakout Strategy แบบละเอียด

## Hypothesis

ราคาที่ทะลุ high 20 แท่งล่าสุด มีโอกาสไปต่อ

## Rules

```text
Entry:
- ถ้า close ปัจจุบัน > high สูงสุดของ 20 แท่งก่อนหน้า → Buy

Exit:
- Stop Loss = Entry - 2 × ATR
- Take Profit = Entry + 4 × ATR
- Time Stop = 24 bars

Risk:
- เสี่ยง 1% ต่อ trade
```

## ทำไมใช้ ATR?

ATR วัดความผันผวน

ถ้าตลาดเหวี่ยงแรง stop ควรกว้างขึ้น
ถ้าตลาดนิ่ง stop ควรแคบลง

แบบนี้ยืดหยุ่นกว่า stop คงที่ เช่น 50 points ตลอดเวลา

---

# 22. Algorithmic Trading ไม่ได้มีแค่ Strategy

หลายคนคิดว่า algo trading = หาสูตรเข้า order

จริง ๆ ยังมีส่วนอื่น:

| Layer                  | หน้าที่                    |
| ---------------------- | -------------------------- |
| Alpha Model            | หาสัญญาณว่าควรซื้อ/ขายอะไร |
| Portfolio Construction | จัดสรรเงินแต่ละสินทรัพย์   |
| Risk Model             | จำกัดความเสี่ยง            |
| Execution Model        | ส่ง order ให้ต้นทุนต่ำ     |
| Monitoring             | ตรวจว่าระบบทำงานปกติไหม    |

สำหรับมือใหม่เริ่มจาก single strategy ได้ แต่ถ้าโตขึ้นควรคิดเป็นระบบหลายชั้น

---

# 23. Algo Trading แบบ Multi-Symbol

แทนที่จะเทรดแค่ XAUUSD อาจเทรดหลายสินทรัพย์ เช่น

```text
XAUUSD
EURUSD
GBPUSD
USDJPY
BTCUSD
US500
NAS100
```

ประโยชน์:

* เพิ่มจำนวนโอกาส
* ลดการพึ่งสินทรัพย์เดียว
* กระจาย regime
* ลด risk ที่ระบบพังเพราะตลาดเดียวเปลี่ยนนิสัย

แต่ต้องระวัง correlation

เช่น:

```text
NAS100 กับ US500 อาจวิ่งคล้ายกัน
EURUSD กับ GBPUSD อาจโดน USD factor เหมือนกัน
```

คิดว่ากระจาย แต่จริง ๆ คือถือความเสี่ยงก้อนเดียวในชุดคอสเพลย์หลายตัว

---

# 24. Basic Formula: Return

ผลตอบแทนแบบง่าย:

```text
Return = (Current Price - Previous Price) / Previous Price
```

ตัวอย่าง:

```text
ราคาก่อนหน้า = 100
ราคาปัจจุบัน = 105

Return = (105 - 100) / 100
Return = 0.05 หรือ 5%
```

ในโค้ด:

```python
data["return"] = data["close"].pct_change()
```

---

# 25. Basic Formula: Log Return

บางระบบนิยมใช้ log return

```text
Log Return = ln(Current Price / Previous Price)
```

ข้อดีคือเอาไปบวกสะสมได้สะดวกกว่า simple return

```python
import numpy as np

data["log_return"] = np.log(data["close"] / data["close"].shift(1))
```

สำหรับเริ่มต้นใช้ simple return ก่อนก็ได้ ไม่ต้องรีบทำตัวเป็นกองทุนเฮดจ์ฟันด์ในคืนเดียว

---

# 26. Basic Formula: Sharpe Ratio

ใช้วัดผลตอบแทนเทียบกับความเสี่ยง

```text
Sharpe Ratio = Average Return / Standard Deviation of Return
```

แบบ annualized:

```python
sharpe = (returns.mean() / returns.std()) * np.sqrt(252)
```

ถ้าเป็นข้อมูล daily ใช้ 252 เพราะตลาดหุ้นมีประมาณ 252 วันทำการต่อปี

สำหรับ H1, M30 ต้องปรับตามจำนวนแท่งต่อปี

---

# 27. สิ่งที่ควรเรียนตามลำดับ

ถ้าจะเรียนให้เป็นระบบ แนะนำลำดับนี้:

## Phase 1: Foundation

* Python
* Pandas
* Numpy
* Matplotlib
* OHLCV data
* Basic statistics

## Phase 2: Trading Basics

* Return
* Volatility
* Drawdown
* Position sizing
* Stop loss / take profit
* Order types

## Phase 3: Strategy Research

* Moving Average
* RSI
* Bollinger Bands
* Breakout
* ATR
* Momentum
* Mean reversion

## Phase 4: Backtesting

* Vectorized backtest
* Event-driven backtest
* Transaction cost
* Slippage
* Walk-forward validation
* Out-of-sample test

## Phase 5: Robustness

* Parameter sensitivity
* Monte Carlo simulation
* Multi-symbol testing
* Regime analysis
* Correlation analysis

## Phase 6: Automation

* Broker API
* Logging
* Error handling
* Monitoring
* Risk kill-switch
* Deployment

## Phase 7: ML / Advanced

* Feature engineering
* Classification
* Regression
* Triple barrier labeling
* Meta-labeling
* Reinforcement learning
* Portfolio optimization

---

# 28. Mini Example: Simple Backtest Logic

สมมติ strategy:

```text
ถ้า close วันนี้ > close เมื่อวาน → พรุ่งนี้ถือ long
ถ้า close วันนี้ < close เมื่อวาน → ไม่ถือ
```

โค้ดแนวคิด:

```python
import pandas as pd

data = pd.read_csv("data.csv")

data["return"] = data["close"].pct_change()

data["signal"] = 0
data.loc[data["close"] > data["close"].shift(1), "signal"] = 1

data["strategy_return"] = data["signal"].shift(1) * data["return"]

data["equity"] = (1 + data["strategy_return"]).cumprod()
```

จุดสำคัญคือ:

```python
data["signal"].shift(1)
```

เพราะ signal ที่เกิดจากข้อมูลวันนี้ ต้องใช้กับผลตอบแทนของวันถัดไป ไม่งั้นจะเกิด lookahead bias

---

# 29. Beginner Mistake ที่เจอบ่อยมาก

## Mistake 1: ดูแต่ Accuracy

สมมติโมเดลทำนายถูก 60%

ฟังดูดี แต่ถ้า:

```text
ถูกได้กำไรเฉลี่ย $10
ผิดเสียเฉลี่ย $30
```

ระบบยังขาดทุน

---

## Mistake 2: ไม่มี Stop Loss

ไม่มี stop loss ไม่ได้แปลว่าไม่ขาดทุน
มันแปลว่ายังไม่ยอมรับว่าขาดทุน

---

## Mistake 3: เทรดบ่อยเกินไป

ยิ่ง timeframe ต่ำ ยิ่งโดน cost กินง่าย

---

## Mistake 4: ใช้ Indicator เยอะเกิน

RSI + MACD + Bollinger + Stochastic + Ichimoku + Fibonacci + Moon Phase

ถ้าใส่เยอะเกินไป ระบบไม่ได้ฉลาดขึ้น แค่เริ่มเหมือนแผงควบคุมยานอวกาศที่ไม่มีใครรู้ว่าปุ่มไหนยิงจรวด

---

## Mistake 5: Backtest สวยเกินจริง

ถ้า equity curve เรียบสวยเหมือนบันไดขึ้นสวรรค์ ให้สงสัยไว้ก่อน:

* data leakage?
* lookahead bias?
* ไม่ใส่ cost?
* overfit?
* trade น้อยเกินไป?
* ใช้ราคาที่เข้าไม่ได้จริง?

---

# 30. Practical Roadmap สำหรับคุณ

ถ้าจะเริ่มจากศูนย์ถึงทำบอทได้จริง ผมแนะนำแบบนี้:

## Stage 1: ทำ Rule-Based ก่อน

เริ่มจาก 3 strategy:

```text
1. Moving Average Crossover
2. RSI Mean Reversion
3. ATR Breakout
```

อย่าเพิ่ง ML ทันที เพราะถ้า backtester ยังไม่แข็ง ML จะยิ่งทำให้มั่วแบบดูฉลาด

---

## Stage 2: ทำ Backtester แบบ Event-Based

ต้องรองรับ:

```text
- open position
- stop loss
- take profit
- time stop
- commission
- spread
- slippage
- trade log
```

---

## Stage 3: ทำ Performance Report

ต้องมี:

```text
- total return
- win rate
- profit factor
- max drawdown
- expectancy
- average R
- trade duration
- monthly returns
```

---

## Stage 4: ทำ Walk-Forward Test

ห้ามเชื่อผลจากการ test รอบเดียว

ควรแบ่งข้อมูลหลายช่วง เช่น:

```text
Round 1: Train 2020-2021 / Test 2022
Round 2: Train 2021-2022 / Test 2023
Round 3: Train 2022-2023 / Test 2024
```

---

## Stage 5: Multi-Symbol

เมื่อ strategy เริ่มนิ่ง ค่อยขยายไปหลายสินทรัพย์

เช่น:

```text
XAUUSD
EURUSD
GBPUSD
USDJPY
BTCUSD
US500
NAS100
```

แต่ต้องทำ portfolio risk ไม่ใช่แค่ copy strategy ไปทุก symbol

---

## Stage 6: ML

หลังจากระบบพื้นฐานแน่นแล้ว ค่อยเพิ่ม ML เช่น:

```text
- predict next return
- classify TP-before-SL
- triple barrier labeling
- meta-labeling
- regime classification
```

ML ควรเป็น “ตัวช่วยตัดสินใจ” ไม่ใช่พระเจ้าประจำพอร์ต

---

# 31. สรุปสั้นแบบจับแก่น

Algorithmic Trading คือการสร้างระบบซื้อขายจากกฎที่ชัดเจน ทดสอบได้ และควบคุมความเสี่ยงได้

สิ่งที่ต้องเข้าใจจริง ๆ คือ:

```text
1. Data: ใช้ข้อมูลอะไร
2. Signal: เข้าซื้อขายเมื่อไหร่
3. Risk: ถ้าผิดจะเสียเท่าไหร่
4. Position Size: เปิดไม้ใหญ่แค่ไหน
5. Backtest: ในอดีตรอดไหม
6. Robustness: รอดหลายช่วงตลาดไหม
7. Execution: เทรดจริงแล้ว cost กินไหม
8. Evaluation: ระบบมี edge จริงหรือแค่ฟลุ๊ก
```

ถ้าจะจำแค่ประโยคเดียว:

> กลยุทธ์ที่ดีไม่ใช่กลยุทธ์ที่ทำนายถูกตลอด แต่คือกลยุทธ์ที่เมื่อผิดแล้วยังไม่ตาย และเมื่อถูกแล้วได้คุ้มพอจะชดเชยความผิดพลาดทั้งหมดได้.
