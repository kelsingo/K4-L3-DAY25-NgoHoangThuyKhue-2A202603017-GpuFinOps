"""M2 — Inference Cost Levers: $/1M-token, batch x cache x cascade (deck §7).

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num
from finops import pricing

# $/1M tokens (input, output) — illustrative 2026.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}

# Explicit synthetic assumptions because token_usage.csv has no prefix ID or
# reads-per-prefix field. Cache creation is assumed to cost 1.25x normal input;
# small-tier prefixes average one read (low reuse), large-tier prefixes four.
CACHE_WRITE_MULTIPLIER = 1.25
AVG_CACHE_READS = {"small": 1.0, "large": 4.0}


def _optimized_cost(rows: list[dict], reads_by_tier: dict[str, float]) -> tuple[float, dict]:
    """Apply cache only when amortized read savings repay its write charge."""
    total = 0.0
    decisions = {}
    for tier, (price_in, _) in MODEL_PRICES.items():
        write_cost = price_in * CACHE_WRITE_MULTIPLIER
        reads = reads_by_tier[tier]
        decisions[tier] = {
            "avg_reads": reads,
            "write_cost_per_m": write_cost,
            "break_even_reads": pricing.cache_break_even_reads(write_cost, price_in),
            "enabled": pricing.cache_is_worth_it(
                reads, write_cost, price_in_per_m=price_in
            ),
        }

    for r in rows:
        tier = r["route_tier"]
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        pin, pout = MODEL_PRICES[tier]
        decision = decisions[tier]
        applied_cached = cached if decision["enabled"] else 0
        total += pricing.request_cost(
            inp, out, pin, pout, cached_in=applied_cached, batch=is_batch
        )
        if applied_cached:
            # One write is shared by avg_cache_reads. Cache writes are assumed
            # not to receive the Batch API discount.
            total += (
                applied_cached
                / 1e6
                * decision["write_cost_per_m"]
                / decision["avg_reads"]
            )
    return total, decisions


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    base_cost = legacy_opt_cost = 0.0
    total_tokens = 0
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        total_tokens += inp + out
        # BASELINE: naive deployment — everything on the large model, no cache, no batch
        lin, lout = MODEL_PRICES["large"]
        base_cost += pricing.request_cost(inp, out, lin, lout)
        # OPTIMIZED: cascade (route_tier), prompt caching, batch API
        pin, pout = MODEL_PRICES[r["route_tier"]]
        legacy_opt_cost += pricing.request_cost(
            inp, out, pin, pout, cached_in=cached, batch=is_batch
        )

    opt_cost, cache_decisions = _optimized_cost(rows, AVG_CACHE_READS)
    low_read_cost, _ = _optimized_cost(rows, {"small": 1.0, "large": 1.0})
    high_read_cost, _ = _optimized_cost(rows, {"small": 8.0, "large": 8.0})

    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"old optimized (write ignored): ${legacy_opt_cost:,.2f}/day")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + economic caching + batch)")
        print(f"discount stack (batch + 100% cache): {pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive")
        print("\nCache economics (assumption: write = 1.25x normal input price):")
        print(f"{'tier':8}{'avg reads':>11}{'break-even':>13}{'cache?':>9}")
        for tier, decision in cache_decisions.items():
            print(
                f"{tier:8}{decision['avg_reads']:>11.1f}"
                f"{decision['break_even_reads']:>13.2f}"
                f"{str(decision['enabled']):>9}"
            )
        print(
            f"read scenarios: low (1 read) ${low_read_cost:,.2f}/day; "
            f"high (8 reads) ${high_read_cost:,.2f}/day"
        )

    return {
        "baseline_daily": round(base_cost, 2), "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3), "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1), "total_tokens": total_tokens,
        "legacy_optimized_daily": round(legacy_opt_cost, 2),
        "legacy_optimized_per_m": round(
            pricing.dollars_per_million(legacy_opt_cost, total_tokens), 3
        ),
        "cache_decisions": cache_decisions,
        "cache_scenarios": {
            "low_reads_daily": round(low_read_cost, 2),
            "high_reads_daily": round(high_read_cost, 2),
            "low_reads_per_m": round(
                pricing.dollars_per_million(low_read_cost, total_tokens), 3
            ),
            "high_reads_per_m": round(
                pricing.dollars_per_million(high_read_cost, total_tokens), 3
            ),
        },
    }


if __name__ == "__main__":
    run()
