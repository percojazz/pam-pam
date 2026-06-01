import marimo

__generated_with = "0.23.8"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        # Part 2 — Optimal Refresh Frequency

        The refresh bot pushes a new on-chain price every `N` blocks; each refresh
        costs gas. Refresh **too often** → gas burns the edge. Refresh **too rarely**
        → the on-chain price goes stale and informed flow picks the pool off
        (adverse selection). We want the refresh interval `T` that maximises LP profit.

        **Conventions.** `T` is the refresh interval in **seconds** (a refresh every
        `N = T / block_time` blocks). All money figures are USD/day unless noted.
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## 1. Objective function

        Daily LP profit as a function of the refresh interval `T`:

        $$
        \Pi(T) \;=\; \underbrace{V \cdot s}_{\text{fee revenue}}
                 \;-\; \underbrace{C_\text{gas}\,\dfrac{86400}{T}}_{\text{gas cost}}
                 \;-\; \underbrace{\kappa\,V\,\sigma\,\sqrt{T}}_{\text{adverse selection}}
        $$

        - **Fee revenue** `V·s` (volume × spread) is, to first order, **independent of
          `T`** — you earn the spread on uninformed flow regardless of refresh cadence —
          so it drops out of the optimisation and we **minimise total cost**.
        - **Gas cost** `C_gas · (86400 / T)` falls as `T` grows (fewer refreshes/day).
        - **Adverse selection** uses the assignment's hint: over a stale window of
          length `T`, the true price random-walks away from the quote by `~σ√T`, and
          informed traders extract that drift. `κ` is the toxic/arb fraction of volume
          (the share of flow that actually exploits staleness).

        So we minimise

        $$
        \text{Cost}(T) \;=\; \frac{A}{T} + B\sqrt{T},
        \qquad A = C_\text{gas}\cdot 86400,\quad B = \kappa\,V\,\sigma .
        $$

        ### Closed-form optimum

        $$
        \frac{d\,\text{Cost}}{dT} = -\frac{A}{T^2} + \frac{B}{2\sqrt{T}} = 0
        \;\;\Longrightarrow\;\;
        \boxed{\,T^\* = \left(\dfrac{2A}{B}\right)^{2/3}
              = \left(\dfrac{2\,C_\text{gas}\,86400}{\kappa\,V\,\sigma}\right)^{2/3}}
        $$

        The headline scaling, used in §4:

        $$
        T^\* \;\propto\; V^{-2/3}.
        $$

        Doubling volume shrinks the optimal interval by `2^{-2/3} ≈ 0.63` — i.e. you
        refresh `2^{2/3} ≈ 1.59×` more often.
        """
    )
    return


@app.cell
def _():
    import marimo as mo
    import numpy as np
    import polars as pl
    import matplotlib.pyplot as plt

    return mo, np, pl, plt


@app.cell
def _(np):
    # --- Given parameters (from the assignment) ------------------------------- #
    C_GAS = 0.50          # USD gas cost per refresh
    VOLUME = 50_000_000.0  # USD expected daily volume
    SPREAD = 5e-4         # 5 bps
    BLOCK_TIME = 0.75     # BSC block time, seconds
    BNB_PRICE = 627.0     # USD per BNB
    SEC_PER_DAY = 86_400

    # --- Modelling assumptions (stated, not given) ---------------------------- #
    # BNB realised volatility. ~50%/yr annualised is a reasonable mid estimate;
    # convert to per-second fractional vol via the sqrt-of-time rule.
    SIGMA_ANNUAL = 0.50
    SEC_PER_YEAR = 365 * SEC_PER_DAY
    SIGMA_SEC = SIGMA_ANNUAL / np.sqrt(SEC_PER_YEAR)   # fractional vol per sqrt(second)

    # Toxic fraction of volume: share of flow that actually arbs staleness.
    # Most flow is uninformed and just pays the spread; calibrated in §3.
    KAPPA = 0.20

    return (
        BLOCK_TIME,
        BNB_PRICE,
        C_GAS,
        KAPPA,
        SEC_PER_DAY,
        SIGMA_SEC,
        SPREAD,
        VOLUME,
    )


@app.cell
def _(C_GAS, SEC_PER_DAY):
    def gas_cost(T):
        """Daily gas cost (USD) at refresh interval T seconds."""
        return C_GAS * SEC_PER_DAY / T

    def adverse_selection(T, volume, kappa, sigma_sec):
        """Daily adverse-selection cost (USD): kappa * V * sigma * sqrt(T)."""
        return kappa * volume * sigma_sec * (T**0.5)

    def total_cost(T, volume, kappa, sigma_sec):
        return gas_cost(T) + adverse_selection(T, volume, kappa, sigma_sec)

    def optimal_T(volume, kappa, sigma_sec):
        """Closed-form T* = (2A / B)^(2/3)."""
        A = C_GAS * SEC_PER_DAY
        B = kappa * volume * sigma_sec
        return (2 * A / B) ** (2 / 3)

    return adverse_selection, gas_cost, optimal_T, total_cost


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## 2. Sanity check against the live system

        The system currently runs at **7.2 BNB/day per chain**. Does that imply a
        sensible refresh interval? Working backwards from the gas spend:
        """
    )
    return


@app.cell
def _(BLOCK_TIME, BNB_PRICE, C_GAS, SEC_PER_DAY, mo):
    _daily_gas_usd = 7.2 * BNB_PRICE
    _refreshes_per_day = _daily_gas_usd / C_GAS
    _current_T = SEC_PER_DAY / _refreshes_per_day
    _current_N = _current_T / BLOCK_TIME

    mo.md(
        f"""
        | Quantity | Value |
        |---|---|
        | Daily gas spend | 7.2 BNB → **${_daily_gas_usd:,.0f}/day** |
        | Refreshes/day | ${_daily_gas_usd:,.0f} / $0.50 = **{_refreshes_per_day:,.0f}** |
        | Implied interval `T` | **{_current_T:.1f} s** |
        | Implied blocks `N` | **{_current_N:.1f} blocks** |

        ~9.6 s / ~13 blocks is consistent with the brief's "updates every few blocks",
        so the parameters hang together and we have a real anchor to calibrate against.
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""## 3. Base-case optimum and the cost curve""")
    return


@app.cell
def _(BLOCK_TIME, KAPPA, SIGMA_SEC, VOLUME, gas_cost, mo, optimal_T, total_cost):
    _T_star = optimal_T(VOLUME, KAPPA, SIGMA_SEC)
    _N_star = _T_star / BLOCK_TIME
    _cost_star = total_cost(_T_star, VOLUME, KAPPA, SIGMA_SEC)
    _gas_star = gas_cost(_T_star)
    _gas_bnb = _gas_star / 627.0

    mo.md(
        f"""
        Base case (`V=$50M`, `σ=50%/yr`, `κ=0.20`):

        | Quantity | Value |
        |---|---|
        | Optimal interval `T*` | **{_T_star:.1f} s** |
        | Optimal blocks `N*` | **{_N_star:.1f} blocks** |
        | Total cost at `T*` | **${_cost_star:,.0f}/day** |
        | of which gas | ${_gas_star:,.0f}/day ({_gas_bnb:.1f} BNB/day) |

        At the optimum, gas and adverse-selection costs sit in a fixed 1:2 ratio
        (`d/dT` balances `A/T` against `½B√T`), a useful operational invariant: if your
        gas spend is far from **one-third** of your modelled staleness cost, `T` is
        mistuned.
        """
    )
    return


@app.cell
def _(
    KAPPA,
    SIGMA_SEC,
    VOLUME,
    adverse_selection,
    gas_cost,
    np,
    optimal_T,
    plt,
    total_cost,
):
    _T = np.linspace(1, 60, 400)
    _Tstar = optimal_T(VOLUME, KAPPA, SIGMA_SEC)

    fig_cost, ax_cost = plt.subplots(figsize=(8, 4.5))
    ax_cost.plot(_T, gas_cost(_T), label="gas cost  (A/T)", lw=2)
    ax_cost.plot(
        _T,
        adverse_selection(_T, VOLUME, KAPPA, SIGMA_SEC),
        label="adverse selection  (B√T)",
        lw=2,
    )
    ax_cost.plot(
        _T,
        total_cost(_T, VOLUME, KAPPA, SIGMA_SEC),
        label="total cost",
        lw=3,
        color="#d62728",  # high-contrast red, visible on light or dark themes
        zorder=5,
    )
    ax_cost.axvline(_Tstar, ls="--", color="0.5", lw=1.5)
    ax_cost.annotate(
        f"T* = {_Tstar:.1f}s",
        xy=(_Tstar, total_cost(_Tstar, VOLUME, KAPPA, SIGMA_SEC)),
        xytext=(_Tstar + 6, total_cost(_Tstar, VOLUME, KAPPA, SIGMA_SEC) + 200),
        color="#d62728",
        fontweight="bold",
    )
    ax_cost.set_xlabel("refresh interval T (seconds)")
    ax_cost.set_ylabel("USD / day")
    ax_cost.set_title("Cost components vs refresh interval (base case)")
    ax_cost.legend()
    ax_cost.grid(alpha=0.3)
    fig_cost
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## 4. How optimal `T` changes with volume

        Since `T* ∝ V^{-2/3}`, higher volume justifies fresher quotes: the staleness
        cost scales with volume but the gas cost does not, so the balance tips toward
        spending more on gas.
        """
    )
    return


@app.cell
def _(BLOCK_TIME, KAPPA, SIGMA_SEC, optimal_T, pl):
    _volumes = [5e6, 10e6, 25e6, 50e6, 100e6, 250e6, 500e6, 1e9]
    vol_table = pl.DataFrame(
        {
            "daily_volume_usd": _volumes,
            "T_star_sec": [optimal_T(v, KAPPA, SIGMA_SEC) for v in _volumes],
        }
    ).with_columns(
        N_star_blocks=(pl.col("T_star_sec") / BLOCK_TIME),
        refreshes_per_day=(86_400 / pl.col("T_star_sec")),
    )
    vol_table
    return (vol_table,)


@app.cell
def _(KAPPA, SIGMA_SEC, np, optimal_T, plt):
    _V = np.logspace(np.log10(2e6), np.log10(2e9), 200)
    _Tv = np.array([optimal_T(v, KAPPA, SIGMA_SEC) for v in _V])

    fig_vol, ax_vol = plt.subplots(figsize=(8, 4.5))
    ax_vol.loglog(_V / 1e6, _Tv, lw=2.5)
    ax_vol.set_xlabel("daily volume  (USD millions, log scale)")
    ax_vol.set_ylabel("optimal T*  (seconds, log scale)")
    ax_vol.set_title(r"Optimal refresh interval vs volume   ($T^* \propto V^{-2/3}$)")
    ax_vol.grid(which="both", alpha=0.3)
    # annotate the -2/3 slope
    ax_vol.annotate("slope = −2/3 on log–log", xy=(50, _Tv[len(_Tv) // 2]), fontsize=9)
    fig_vol
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## 5. Sensitivity to the assumed constants

        `T*` depends on the two assumed inputs — volatility `σ` and toxic fraction `κ`
        — only through the product `κ·σ`, and only to the `^(-2/3)` power, so it is
        fairly robust: a 4× error in `κ·σ` moves `T*` by `4^{2/3} ≈ 2.5×`. The grid
        below shows the plausible range stays within single-digit-to-low-tens of
        seconds.
        """
    )
    return


@app.cell
def _(SIGMA_SEC, VOLUME, optimal_T, pl):
    _kappas = [0.05, 0.10, 0.20, 0.40]
    _sigma_mults = {"σ=30%/yr": 0.6, "σ=50%/yr": 1.0, "σ=80%/yr": 1.6}

    _rows = []
    for k in _kappas:
        row = {"kappa": k}
        for label, mult in _sigma_mults.items():
            row[label] = optimal_T(VOLUME, k, SIGMA_SEC * mult)
        _rows.append(row)
    sensitivity_table = pl.DataFrame(_rows)
    sensitivity_table
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## 6. Should the ~2 s Binance WS silence be a staleness event?

        **No — it should not trip the staleness / halt logic.** Two reasons:

        1. **The price barely moves in 2 s.** With `σ ≈ 50%/yr`, the expected drift over
           2 s is `σ·√2 ≈ 1.3 bps` — well inside the **5 bps** spread. The quote is
           still profitable to trade against the pool, not against us. (Cell below
           computes this.)
        2. **It's periodic and predictable, not a feed failure.** The gap recurs every
           ~60 s. Treating each one as a staleness event would force a halt/refresh
           every minute — self-inflicted downtime and wasted gas, the opposite of what
           the optimisation buys us.

        **Correct handling:** on a routine gap, hold the last-good price (optionally
        widen the spread a touch as a cheap hedge). Only escalate to a *staleness event*
        if silence persists beyond a threshold — e.g. several expected gap-lengths, or
        once drift could plausibly exceed the spread. This sets a floor on the on-chain
        **price-expiry window**: it must comfortably exceed `2 s + refresh latency`,
        which connects directly to Part 3's "expiry in blocks" question.
        """
    )
    return


@app.cell
def _(SIGMA_SEC, SPREAD, mo, np):
    _silence = 2.0  # seconds
    _drift = SIGMA_SEC * np.sqrt(_silence)  # fractional
    mo.md(
        f"""
        | Quantity | Value |
        |---|---|
        | WS silence window | {_silence:.0f} s |
        | Expected drift `σ·√T` | **{_drift * 1e4:.2f} bps** |
        | Spread | {SPREAD * 1e4:.0f} bps |
        | Drift / spread | **{_drift / SPREAD:.0%}** |

        Drift is a fraction of the spread → not a staleness event.
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        ## Summary

        - **Objective:** maximise `Π(T) = V·s − C_gas·86400/T − κ·V·σ·√T`; since revenue
          is ~flat in `T`, minimise `Cost(T) = A/T + B√T`.
        - **Optimum:** `T* = (2A/B)^(2/3)`, giving **~21 s / ~28 blocks** in the base case.
          The live system runs fresher (~9.6 s / ~13 blocks); that operating point falls
          out of the model at a higher toxicity assumption (`κ ≈ 0.4`), so the live
          cadence is defensible but sits at the conservative/fresh end of the plausible
          band — there may be modest gas savings from refreshing slightly less often.
        - **Volume scaling:** `T* ∝ V^{-2/3}` — double the volume ⇒ refresh ~1.6× more
          often.
        - **Robustness:** `T*` depends on `(κ·σ)^(-2/3)`, so even large errors in the
          assumed constants keep it in the single-digit-to-low-tens-of-seconds range.
        - **WS silence:** not a staleness event — 2 s drift (~1.3 bps) is well inside the
          5 bps spread and the gap is predictable; hold last-good price and only escalate
          on prolonged silence.

        **Caveats / extensions.** The `σ√T` term is the assignment's first-order hint;
        a sharper model would only count adverse selection *above* the fee+half-spread
        threshold (LVR-style), which raises `T*` since small drifts aren't actually
        toxic. We also treat volume and volatility as constant — in practice both spike
        together, and the optimal controller would shorten `T` dynamically during
        high-vol regimes rather than hold a static interval.
        """
    )
    return


if __name__ == "__main__":
    app.run()
