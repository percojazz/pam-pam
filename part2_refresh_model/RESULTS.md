# Part 2 — Optimal Refresh Frequency: Results

Companion writeup to the marimo notebook [`refresh_model.py`](refresh_model.py).
Run it with `uv run marimo edit refresh_model.py`.

`T` is the refresh interval in **seconds** (a refresh every `N = T / block_time`
blocks). All money figures are USD/day unless noted.

---

## 1. Objective function

Daily LP profit as a function of the refresh interval `T`:

```
Π(T)  =  V·s            (fee revenue, volume × spread)
       − C_gas·86400/T  (gas cost — falls as T grows)
       − κ·V·σ·√T       (adverse selection — rises as T grows)
```

Fee revenue `V·s` is, to first order, **independent of `T`** (you earn the spread on
uninformed flow regardless of refresh cadence), so it drops out and we **minimise
total cost**:

```
Cost(T) = A/T + B·√T ,   A = C_gas·86400 ,   B = κ·V·σ
```

The adverse-selection term follows the assignment's hint: over a stale window of
length `T`, the true price random-walks away from the quote by `~σ√T`, and informed
traders extract that drift. `κ` is the toxic/arb fraction of volume.

### Closed-form optimum

```
dCost/dT = −A/T² + B/(2√T) = 0   ⟹   T* = (2A / B)^(2/3)
```

```
T* = ( 2·C_gas·86400 / (κ·V·σ) )^(2/3)        ⟹        T* ∝ V^(−2/3)
```

At the optimum the two cost terms sit in a fixed **1 : 2 ratio** (gas : adverse
selection) — a handy operational invariant: if gas spend isn't ≈ ⅓ of modelled
staleness cost, `T` is mistuned.

---

## 2. Parameters

| Symbol | Meaning | Value | Source |
|---|---|---|---|
| `C_gas` | gas cost per refresh | $0.50 | given |
| `V` | expected daily volume | $50M | given |
| `s` | spread | 5 bps | given |
| `block_time` | BSC block time | 0.75 s | given |
| `σ_annual` | BNB realised vol | 50%/yr | **assumed** |
| `σ_sec` | per-√second frac. vol | 8.90×10⁻⁵ | `σ_annual / √(365·86400)` |
| `κ` | toxic fraction of volume | 0.20 | **assumed**, see §5 |

---

## 3. Sanity check vs the live system

The system runs at **7.2 BNB/day per chain**. Working backwards from the gas spend:

| Quantity | Value |
|---|---|
| Daily gas spend | 7.2 BNB → **$4,514/day** |
| Refreshes/day | $4,514 / $0.50 = **9,029** |
| Implied interval `T` | **9.6 s** |
| Implied blocks `N` | **12.8 blocks** |

~9.6 s / ~13 blocks matches the brief's "updates every few blocks" — the parameters
are mutually consistent and give a real anchor to calibrate against.

---

## 4. Base-case optimum

`V=$50M`, `σ=50%/yr`, `κ=0.20`:

| Quantity | Value |
|---|---|
| Optimal interval `T*` | **21.1 s** |
| Optimal blocks `N*` | **28.2 blocks** |
| Fee revenue | $25,000/day |
| Total cost at `T*` | **$6,137/day** |
|   — gas | $2,046/day (3.26 BNB/day) |
|   — adverse selection | $4,091/day |
| Net edge `Π(T*)` | ≈ $18,863/day |

The 1:2 gas:adverse-selection split holds ($2,046 : $4,091), as the closed form
predicts.

---

## 5. How optimal `T` changes with volume

Since `T* ∝ V^(−2/3)`, staleness cost scales with volume but gas cost does not, so
higher volume tips the balance toward fresher quotes.

| Daily volume | `T*` (s) | `N*` (blocks) | refreshes/day |
|---:|---:|---:|---:|
| $5M | 98.0 | 130.7 | 881 |
| $10M | 61.7 | 82.3 | 1,399 |
| $25M | 33.5 | 44.7 | 2,577 |
| $50M | 21.1 | 28.2 | 4,091 |
| $100M | 13.3 | 17.7 | 6,495 |
| $250M | 7.2 | 9.6 | 11,964 |
| $500M | 4.5 | 6.1 | 18,991 |
| $1B | 2.9 | 3.8 | 30,146 |

**Rule of thumb:** doubling volume ⇒ refresh `2^(2/3) ≈ 1.59×` more often (interval
shrinks to `2^(−2/3) ≈ 0.63×`). Note the live 9.6 s point lines up with the model
optimum at ~$250M/day — i.e. the current cadence is optimal *if* effective toxic
volume is ~5× the headline $50M, which is plausible once arb flow is included.

---

## 6. Sensitivity to assumed constants

`T*` depends on `σ` and `κ` only through `(κ·σ)^(−2/3)`, so it is robust: a 4× error
in `κ·σ` moves `T*` by only `4^(2/3) ≈ 2.5×`. Optimal `T*` (seconds):

| `κ` ＼ `σ` | 30%/yr | 50%/yr | 80%/yr |
|---:|---:|---:|---:|
| 0.05 | 74.8 | 53.2 | 38.9 |
| 0.10 | 47.1 | 33.5 | 24.5 |
| 0.20 | 29.7 | **21.1** | 15.4 |
| 0.40 | 18.7 | 13.3 | 9.7 |

Across the whole plausible range `T*` stays within ~10–75 s (≈13–100 blocks). The
live 9.6 s sits at the aggressive corner (high `κ·σ`), so the system is currently
tuned as if flow is quite toxic — defensible, but at the fresh/expensive end.

---

## 7. Should the ~2 s Binance WS silence be a staleness event?

**No.**

| Quantity | Value |
|---|---|
| WS silence window | 2 s |
| Expected drift `σ·√T` | **1.26 bps** |
| Spread | 5 bps |
| Drift / spread | **25%** |

1. **The price barely moves in 2 s** — expected drift ≈ 1.3 bps, well inside the
   5 bps spread, so the quote is still profitable to trade against.
2. **It's periodic and predictable, not a feed failure** — recurs every ~60 s.
   Treating each gap as a staleness event would force a halt/refresh every minute:
   self-inflicted downtime and wasted gas.

**Correct handling:** on a routine gap, hold the last-good price (optionally widen
the spread slightly as a cheap hedge). Only escalate to a *staleness event* if
silence persists beyond a threshold — several expected gap-lengths, or once drift
could plausibly exceed the spread. This sets a floor on the on-chain **price-expiry
window**: it must comfortably exceed `2 s + refresh latency`, which feeds directly
into Part 3's "expiry in blocks" question.

---

## 8. Summary

- **Objective:** maximise `Π(T) = V·s − C_gas·86400/T − κ·V·σ·√T`; revenue is ~flat in
  `T`, so minimise `Cost(T) = A/T + B√T`.
- **Optimum:** `T* = (2A/B)^(2/3)` → **~21 s / ~28 blocks** base case.
- **Volume scaling:** `T* ∝ V^(−2/3)` — double the volume ⇒ refresh ~1.6× more often.
- **Robustness:** `T*` depends on `(κσ)^(−2/3)`; even large errors in the assumed
  constants keep it within ~10–75 s.
- **WS silence:** not a staleness event — 2 s drift (~1.3 bps) is well inside the
  5 bps spread and the gap is predictable.

### Caveats / extensions

- The `σ√T` term is the assignment's first-order hint. A sharper model counts adverse
  selection only *above* the fee + half-spread threshold (LVR-style), which raises
  `T*` since small drifts aren't actually toxic.
- We treat volume and volatility as constant. In practice both spike together, so the
  ideal controller shortens `T` dynamically in high-vol regimes rather than holding a
  static interval.
- `κ` is the least-pinned input; it should be calibrated from realised
  adverse-selection PnL (fills that were stale-side at refresh time) rather than
  assumed.
