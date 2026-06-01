# PropAMM Two-Phase Pricing — Calculation Details

Companion notes to [`pricing.py`](pricing.py). Token convention for the live BSC
pair: **X = WBNB**, **Y = USDT**, and the oracle price **P** is in USDT per WBNB.

## 1. The model

A swap is priced in two sequential phases:

1. **Stable phase** — the portion of the trade that *rebalances* the pool toward a
   50/50 value split executes at the flat oracle price `P` with **no slippage**
   (1 WBNB ↔ `P` USDT).
2. **Curve phase** — the remainder executes on a concentrated constant-product
   curve.

### Balance

Balance is measured in *value* terms. The pool is balanced when the two sides hold
equal value:

```
x · P  ==  y
```

Equivalently, the curve-implied price `cpPrice = y / x` equals the oracle `P`.

| condition        | state   | meaning           |
| ---------------- | ------- | ----------------- |
| `cpPrice < P`    | X-heavy | too much WBNB     |
| `cpPrice == P`   | balanced| —                 |
| `cpPrice > P`    | Y-heavy | too much USDT     |

The stable phase only runs while the pool is imbalanced **against** the incoming
trade, and stops the moment the pool reaches balance. The rest flows onto the curve.

## 2. Stable-phase capacity (the `/2` factors)

The stable phase can absorb only enough input to bring the pool exactly to balance
(`x·P == y`). The factor of 2 appears because a single swap moves **both** reserves
toward balance at once.

### Y → X (pay USDT, receive WBNB) — `pricing.py:83`

The pool must start X-heavy (`x·P > y`) for any stable capacity to exist. Putting
`s` units of Y in and taking `s/P` units of X out:

```
x1 = x − s/P
y1 = y + s
```

Solve for the `s` that reaches balance, `x1·P == y1`:

```
(x − s/P)·P  =  y + s
x·P − s      =  y + s
x·P − y      =  2s
s            =  (x·P − y) / 2          ← stable_capacity_y
```

Each unit of input closes the imbalance gap `(x·P − y)` by **2**: one unit from
adding to `y`, one from removing from `x` (scaled by `P`). The `max(0, …)` guard
zeroes the capacity when the pool is already balanced or Y-heavy.

### X → Y (pay WBNB, receive USDT) — `pricing.py:101`

Mirror case; the pool must start Y-heavy (`y > x·P`). Putting `s` units of X in and
taking `s·P` units of Y out:

```
x1 = x + s
y1 = y − s·P
```

Solve `x1·P == y1`:

```
(x + s)·P    =  y − s·P
x·P + s·P    =  y − s·P
2·s·P        =  y − x·P
s            =  (y − x·P) / (2·P)      ← stable_capacity_x
```

Same `/2`, plus an extra `/P` that converts the value gap `(y − x·P)` (measured in Y
units) into X input units.

## 3. Curve phase

The remainder, `curve_in = net_in − stable_in`, executes on a UniV2-style
constant-product curve that uses **virtual reserves** to concentrate liquidity:

```
(x + virtual_x)(y + virtual_y) = L²
virtual_x = x · (alpha − 1)
virtual_y = y · (alpha − 1)
```

This is algebraically identical to a UniV2 swap on *effective* reserves
`x·alpha` and `y·alpha`. The spot price is unchanged, but depth scales with `alpha`
(`alpha ≥ 1`; higher `alpha` ⇒ deeper book ⇒ less slippage). The output formula
(`_curve_out`, `pricing.py:45`):

```
eff_in  = reserve_in  · alpha
eff_out = reserve_out · alpha
out     = eff_out · amount_in / (eff_in + amount_in)
```

Only real token is withdrawn — the virtual part is never removed.

## 4. Fee

The fee is taken on the input token, up front; only the net swaps:

```
fee_charged = amount_in · fee_bps / 1e4
net_in      = amount_in − fee_charged
```

The reported `effective_price` uses the **gross** `amount_in`, so the fee is
reflected in the all-in price the trader pays (always quoted USDT per WBNB).

## 5. Spot bid/ask (`get_bid_ask`, `pricing.py:117`)

The rebalancing side quotes the flat oracle `P`; the imbalancing side quotes the
curve-implied price `cpPrice = y / x`:

```
ask = max(P, cpPrice)   # pool sells WBNB (you buy WBNB)
bid = min(P, cpPrice)   # pool buys WBNB  (you sell WBNB)
```

The **marginal** `cpPrice` is independent of `alpha` — alpha sets the slippage of
finite trades, not the spot quote.

## 6. Worked test cases

`P = 627 USDT/WBNB`, `amount_in = 500 USDT`, direction Y → X, `fee = 5 bps`
(assumed — not given in the assignment table; matches the Part 2 spread).

| Case | state                | cpPrice | bid    | ask    | out (WBNB) | eff price | fee    |
| ---- | -------------------- | ------- | ------ | ------ | ---------- | --------- | ------ |
| A    | balanced             | 627.00  | 627.00 | 627.00 | 0.790869   | 632.22    | 0.2500 |
| B    | Y-heavy              | 937.50  | 627.00 | 937.50 | 0.529607   | 944.10    | 0.2500 |
| C    | X-heavy              | 416.67  | 416.67 | 627.00 | 0.797049   | 627.31    | 0.2500 |
| D    | balanced, alpha=1.05 | 627.00  | 627.00 | 627.00 | 0.791045   | 632.08    | 0.2500 |

Reading the cases:

- **A (balanced):** no stable capacity on a Y→X trade (pool isn't X-heavy), so the
  whole net input runs on the curve → eff price slightly above `P` from slippage.
- **B (Y-heavy):** buying WBNB pushes *further* into the Y-heavy side, so again no
  stable phase and the curve quotes the rich `cpPrice` (937.50) — worst fill.
- **C (X-heavy):** the trade rebalances the pool, so a large slice fills flat at `P`
  before any curve slippage → eff price barely above `P` (627.31) — best fill.
- **D:** same as A but `alpha = 1.05` deepens the book, so slightly more output and a
  marginally better effective price than A.

Reproduce with:

```bash
python3 part1_pricing/pricing.py
```
