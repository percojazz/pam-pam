# pam-pam — Quant Developer Take-Home Assignment

> **Estimated time:** 6–12 hours · **Deadline:** 96 hours from receipt
> Language: any (Python/Rust preferred). Submit as a GitHub repo.

## Overview

Build across the full stack of a production **PropAMM** system: mathematical pricing
logic → system design → on-chain awareness. The reviewers value **practical reasoning,
clear trade-off analysis, and operational awareness** over mathematical sophistication.
A concise, well-reasoned solution beats excessive complexity or premature optimisation.

## System Context

The PropAMM:
- Quotes two-sided prices (bid/ask) for token pairs using an **oracle-anchored concentrated liquidity** model.
- Hedges delta exposure in real time via the **Binance spot API**.
- Refreshes on-chain quotes continuously via a bot that updates on-chain pricing params every few blocks.
- Manages LP capital across **two chains** simultaneously.

Live pairs:
- **BSC:** WBNB / USDT
- **Base:** WETH / USDC

---

## Part 1 — Pricing Model (Core Quant)

Two-phase pricing mechanism:
- **Stable phase:** trades that rebalance the pool toward 50/50 execute at the flat oracle price `P`.
- **Curve phase:** the remainder executes on a concentrated `xy=k` curve parameterised by `alpha` (concentration factor) and liquidity `L`.

The bid/ask spread emerges from the gap between oracle price `P` and the curve-implied price `cpPrice`.

Concentrated liquidity curve:
```
(x + virtual_x)(y + virtual_y) = L²
virtual_x = reserve_x × (alpha - 1)
virtual_y = reserve_y × (alpha - 1)
```

**Tasks:**
1. Implement `get_quote(reserve_x, reserve_y, price_P, alpha, fee_bps, amount_in, swap_x_to_y)`:
   - Compute stable-phase output (balance-improving trades at flat `P`).
   - Compute curve-phase output on the concentrated `xy=k` curve for the remainder.
   - Return `(amount_out, effective_price, fee_charged)`.
2. Implement `get_bid_ask(reserve_x, reserve_y, price_P, alpha)` → current bid and ask prices.
3. Test against the cases below and include results.

**Test cases** (`P` = 627 USDT/WBNB, `amount_in` = 500 USDT, direction Y→X):

| Case | reserve_x | reserve_y          | alpha |
|------|-----------|--------------------|-------|
| A    | 100 WBNB  | 62,700 USDT        | 1.02  |
| B    | 80 WBNB   | 75,000 USDT (Y-heavy) | 1.02 |
| C    | 120 WBNB  | 50,000 USDT (X-heavy) | 1.02 |
| D    | 100 WBNB  | 62,700 USDT        | 1.05  |

---

## Part 2 — Optimal Refresh Frequency (Quant Modelling)

The refresh bot pushes a new on-chain price every `N` blocks; each refresh costs gas.
The system currently runs at **7.2 BNB/day per chain**. Find the optimal refresh frequency.

Relevant dynamics: gas cost per refresh `C_gas`, fee revenue rate (volume × spread),
adverse-selection risk (rises with staleness), Binance WS ~2s silence every ~60s.

**Tasks:**
1. Define the objective function: what is maximised/minimised as a function of refresh interval `T`.
2. Derive/estimate the optimal `T` given:
   - Gas cost per refresh = **$0.50** (~1 BNB refresh at $627)
   - Expected daily volume = **$50M**
   - Spread = **5 bps**
   - BSC block time = **0.75 s**
   - Assume adverse-selection cost scales as **σ × √T** (extra constants/assumptions allowed).
3. Show how optimal `T` changes as a function of volume (plot or table).
4. Should the 2-second Binance WS silence be treated as a staleness event? Why or why not?

---

## Part 3 — Flashloan Arb Detection & Defence (On-Chain Awareness)

Observed attack on BSC:
1. Flashloan: borrow 10 USDT from Lista DAO.
2. PropAMM swap: 10 USDT → 0.01702 WBNB (implied ~$587/BNB).
3. Pamm swap: 0.01702 WBNB → 10.627 USDT (market ~$624/BNB).
4. Repay flashloan.
5. Profit: ~$0.63.

**Root cause:** a stale oracle price (~6% below market) during a test session.

**Tasks:**
1. **Diagnose** (max 300 words): why the attack was profitable and what PropAMM condition enabled it.
2. **Detect:** write `is_suspicious_trade(tx_data)` returning `True` if the pattern matches a flashloan arb against the PropAMM. Define expected `tx_data` fields and heuristics. (`tx_data` may contain: token transfers, swap events, protocol interaction labels, timestamps.)
3. **Defend:** propose a smart-contract- or oracle-level defence (pseudocode/plain English — no full Solidity needed).
4. **Threshold:** given the WS ~2s silence every ~60s, what should on-chain price expiry (in blocks) be for BSC (0.75s blocks) and Base (2s blocks)? Show your working.

---

## Part 4 — System Design (Engineering Judgement)

Production components: quote refresh bot, delta monitor, CEX hedge executor, and a daily
sweep (Treasury Safe → Gas Wallet → Operator Bot Wallet; LP fees periodically swept back to Treasury Safe).

**Tasks:**
1. **Failure mode matrix** — for each scenario, describe what happens and the correct automated response:
   - Binance API returns 429 (rate limit) during hedge execution
   - BSC RPC primary node goes down mid-refresh
   - Operator bot wallet runs out of BNB gas
   - On-chain price expiry fires but feed has not recovered yet
   - Delta exceeds $2,000 unhedged due to missed hedge fills
   - Safe signers unreachable for 24 hours
2. **Kill switch design** — triggerable by an authorised operator without SSH; halts all new LP positions and hedge orders within one polling cycle; does NOT require moving funds; remotely resettable.
3. **Gas wallet auto top-up** — pseudocode that: monitors the operator bot's BNB balance; tops up from the Treasury Safe below a threshold; handles a failed Safe top-up tx; prevents runaway top-ups on a monitoring bug.

---

## Submission Requirements

| Deliverable | Format |
|-------------|--------|
| Part 1 code | Runnable Python or Rust file with test output |
| Part 2 model | Jupyter notebook or PDF with plots/tables |
| Part 3 code + writeup | Python file + markdown or inline comments |
| Part 4 design | Markdown document or well-structured README section |
| README | Brief explanation of approach and any assumptions made |

**Repository structure:**
```
/part1_pricing/
/part2_refresh_model/
/part3_arb_defence/
/part4_system_design/
README.md
```

## Notes to Candidate
- Production-ready Solidity is not expected — pseudocode or Python is fine for contract-level questions.
- State simplifying assumptions clearly; intellectual honesty is valued over false precision.
- If you find an error or ambiguity in the problem statement, note it and how you handled it.
- Designed to be completable in 6–12 hours. Spending significantly more likely means over-engineering a section.
