"""PropAMM two-phase pricing model (Part 1).

The pool prices a swap in two phases:

  * Stable phase  - the portion of the trade that rebalances the pool toward a
                    50/50 value split executes at the flat oracle price ``P``
                    (no slippage: 1 WBNB <-> P USDT).
  * Curve phase   - the remainder executes on a concentrated xy=k curve

        (x + virtual_x)(y + virtual_y) = L^2
        virtual_x = reserve_x * (alpha - 1)
        virtual_y = reserve_y * (alpha - 1)

    which is equivalent to a UniV2 constant-product swap on the *effective*
    reserves ``x*alpha`` and ``y*alpha``. ``alpha`` (>= 1) concentrates
    liquidity: higher alpha => deeper book => less slippage.

Balance is measured in value terms: the pool is balanced when
``reserve_x * P == reserve_y``. Equivalently the curve-implied price
``cpPrice = reserve_y / reserve_x`` equals the oracle ``P``.

  * cpPrice < P  -> X-heavy (too much WBNB)
  * cpPrice > P  -> Y-heavy (too much USDT)

Token convention for the live BSC pair: X = WBNB, Y = USDT, and ``P`` is the
oracle price in USDT per WBNB. ``amount_in`` is denominated in the input token.
"""

from __future__ import annotations

from typing import NamedTuple


class Quote(NamedTuple):
    amount_out: float       # output token received
    effective_price: float  # all-in price the trader pays, USDT per WBNB
    fee_charged: float      # fee taken, denominated in the input token


class BidAsk(NamedTuple):
    bid: float  # price the pool buys WBNB at (USDT per WBNB)
    ask: float  # price the pool sells WBNB at (USDT per WBNB)


def _curve_out(reserve_in: float, reserve_out: float, alpha: float, amount_in: float) -> float:
    """UniV2 constant-product output on alpha-concentrated effective reserves.

    Effective reserves are ``reserve * alpha`` (the virtual reserves shift the
    curve so the spot price is unchanged but depth scales with alpha). The
    amount withdrawn is real token, since the virtual part is never removed.
    """
    eff_in = reserve_in * alpha
    eff_out = reserve_out * alpha
    return eff_out * amount_in / (eff_in + amount_in)


def get_quote(
    reserve_x: float,
    reserve_y: float,
    price_P: float,
    alpha: float,
    fee_bps: float,
    amount_in: float,
    swap_x_to_y: bool,
) -> Quote:
    """Price a swap through the stable phase then the curve phase.

    Returns ``(amount_out, effective_price, fee_charged)`` where
    ``effective_price`` is always quoted as USDT per WBNB (Y per X).
    """
    if amount_in <= 0:
        return Quote(0.0, price_P, 0.0)

    # Fee is charged on the input token, up front; the rest is swapped.
    fee_charged = amount_in * fee_bps / 1e4
    net_in = amount_in - fee_charged

    x, y = reserve_x, reserve_y

    if not swap_x_to_y:
        # Y -> X : pay USDT (Y), receive WBNB (X). Pushes the pool Y-heavy.
        # Stable phase applies only while the pool is X-heavy (x*P > y).
        stable_capacity_y = max(0.0, (x * price_P - y) / 2.0)
        stable_in = min(net_in, stable_capacity_y)

        out_stable = stable_in / price_P          # flat oracle price, no slippage
        # Reserves at the curve entry point (balanced if stable phase ran).
        x1 = x - out_stable
        y1 = y + stable_in

        curve_in = net_in - stable_in
        out_curve = _curve_out(y1, x1, alpha, curve_in) if curve_in > 0 else 0.0

        amount_out = out_stable + out_curve
        # USDT in per WBNB out (uses gross input so the fee is reflected).
        effective_price = amount_in / amount_out if amount_out > 0 else price_P
        return Quote(amount_out, effective_price, fee_charged)

    # X -> Y : pay WBNB (X), receive USDT (Y). Pushes the pool X-heavy.
    # Stable phase applies only while the pool is Y-heavy (y > x*P).
    stable_capacity_x = max(0.0, (y - x * price_P) / (2.0 * price_P))
    stable_in = min(net_in, stable_capacity_x)

    out_stable = stable_in * price_P              # flat oracle price, no slippage
    x1 = x + stable_in
    y1 = y - out_stable

    curve_in = net_in - stable_in
    out_curve = _curve_out(x1, y1, alpha, curve_in) if curve_in > 0 else 0.0

    amount_out = out_stable + out_curve
    # WBNB in per USDT out -> invert to keep USDT-per-WBNB convention.
    effective_price = amount_out / amount_in if amount_in > 0 else price_P
    return Quote(amount_out, effective_price, fee_charged)


def get_bid_ask(reserve_x: float, reserve_y: float, price_P: float, alpha: float) -> BidAsk:
    """Current two-sided quote (USDT per WBNB).

    The rebalancing side quotes the flat oracle ``P``; the imbalancing side
    quotes the curve-implied price ``cpPrice = reserve_y / reserve_x``:

        ask = max(P, cpPrice)   # buying WBNB
        bid = min(P, cpPrice)   # selling WBNB

    Note: the marginal ``cpPrice`` is independent of ``alpha`` - alpha sets the
    depth/slippage of finite trades, not the spot quote. ``alpha`` is accepted
    for signature symmetry with ``get_quote``.
    """
    _ = alpha
    cp_price = reserve_y / reserve_x
    return BidAsk(bid=min(price_P, cp_price), ask=max(price_P, cp_price))


# --------------------------------------------------------------------------- #
# Test cases from the assignment (P = 627 USDT/WBNB, amount_in = 500 USDT, Y->X).
# fee_bps is not given in the table; we assume 5 bps (matches the Part 2 spread)
# and state it as an assumption.
# --------------------------------------------------------------------------- #
ASSUMED_FEE_BPS = 5.0

_CASES = [
    ("A", 100.0, 62_700.0, 627.0, 1.02, 500.0, False, "balanced"),
    ("B", 80.0, 75_000.0, 627.0, 1.02, 500.0, False, "Y-heavy"),
    ("C", 120.0, 50_000.0, 627.0, 1.02, 500.0, False, "X-heavy"),
    ("D", 100.0, 62_700.0, 627.0, 1.05, 500.0, False, "balanced, alpha=1.05"),
]


def _main() -> None:
    print(f"Two-phase PropAMM pricing  (fee = {ASSUMED_FEE_BPS:g} bps, assumed)\n")
    header = f"{'Case':<5}{'state':<22}{'cpPrice':>10}{'bid':>9}{'ask':>9}{'out (WBNB)':>13}{'eff price':>12}{'fee':>8}"
    print(header)
    print("-" * len(header))
    for name, rx, ry, p, alpha, amt, x2y, note in _CASES:
        q = get_quote(rx, ry, p, alpha, ASSUMED_FEE_BPS, amt, x2y)
        ba = get_bid_ask(rx, ry, p, alpha)
        cp = ry / rx
        print(
            f"{name:<5}{note:<22}{cp:>10.2f}{ba.bid:>9.2f}{ba.ask:>9.2f}"
            f"{q.amount_out:>13.6f}{q.effective_price:>12.2f}{q.fee_charged:>8.4f}"
        )


if __name__ == "__main__":
    _main()
