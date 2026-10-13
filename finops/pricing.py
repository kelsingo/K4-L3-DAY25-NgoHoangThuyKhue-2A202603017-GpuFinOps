"""Pricing & purchasing economics — measure in $/1M-token, not $/GPU-hr.

Figures are June-2026 as-of snapshots from the deck's RESEARCH dossier; treat
live prices as fast-moving (re-baseline before each cohort).
"""
from __future__ import annotations

import math


# Synthetic planning assumptions, not live provider SLAs.  These deliberately
# vary by GPU so that spot risk is priced instead of treating every market as
# equally reliable.  Re-baseline from the target provider before purchasing.
SPOT_INTERRUPTION_RATE_BY_GPU = {
    "H100": 0.03,
    "H200": 0.04,
    "A100": 0.06,
    "A10G": 0.10,
    "L4": 0.08,
    "B200": 0.05,
    "MI300X": 0.07,
}


def request_cost(
    input_tok: int,
    output_tok: int,
    price_in_per_m: float,
    price_out_per_m: float,
    cached_in: int = 0,
    cache_discount: float = 0.10,   # Anthropic cached-read ~0.1x (=-90%)
    batch: bool = False,
    batch_discount: float = 0.50,   # Batch API ~ -50%
) -> float:
    """USD cost of a single request. Cached input billed at cache_discount x price."""
    cached_in = min(max(0, cached_in), input_tok)
    uncached_in = input_tok - cached_in
    cost = (
        (uncached_in / 1e6) * price_in_per_m
        + (cached_in / 1e6) * price_in_per_m * cache_discount
        + (output_tok / 1e6) * price_out_per_m
    )
    if batch:
        cost *= batch_discount
    return cost


def dollars_per_million(total_cost_usd: float, total_tokens: int) -> float:
    """Aggregate unit economics: $ per 1,000,000 tokens served."""
    if total_tokens <= 0:
        return 0.0
    return total_cost_usd / (total_tokens / 1e6)


def discount_stack(
    batch: bool = False,
    cache_hit_frac: float = 0.0,
    batch_discount: float = 0.50,
    cache_discount: float = 0.10,
) -> float:
    """Effective fraction of the naive bill after stacking discounts (input-heavy view).

    Discounts MULTIPLY: cache applies to the cached share of input, batch to the
    whole bill. batch + 100% cache-hit -> 0.5 * 0.1 = 0.05 (~95% off).
    """
    cache_mult = cache_hit_frac * cache_discount + (1.0 - cache_hit_frac)
    batch_mult = batch_discount if batch else 1.0
    return cache_mult * batch_mult


def break_even_utilization(discount_frac: float) -> float:
    """Utilization at which a commitment pays off ~= 1 - discount.

    A 45% reserved discount needs ~55% utilization (~13.2h/day) to beat on-demand.
    """
    return max(0.0, min(1.0, 1.0 - discount_frac))


def cache_break_even_reads(
    write_cost_per_m: float,
    price_in_per_m: float,
    read_discount: float = 0.10,
) -> float:
    """Return cache reads needed for read savings to repay one cache write.

    ``write_cost_per_m`` is the incremental cache-creation charge per million
    cached tokens.  A normal uncached read costs ``price_in_per_m``; a cached
    read costs ``read_discount`` of that amount.
    """
    saved_per_read = price_in_per_m * (1.0 - read_discount)
    if write_cost_per_m <= 0:
        return 0.0
    if saved_per_read <= 0:
        return math.inf
    return write_cost_per_m / saved_per_read


def cache_is_worth_it(
    avg_cache_reads: float,
    write_cost_per_m: float,
    read_discount: float = 0.10,
    price_in_per_m: float = 1.0,
) -> bool:
    """Whether repeated-read savings strictly exceed cache-write cost."""
    return avg_cache_reads > cache_break_even_reads(
        write_cost_per_m, price_in_per_m, read_discount
    )


def recommend_tier(
    hours_per_day: float,
    interruptible: bool,
    reserved_discount: float = 0.45,
    *,
    gpu_type: str | None = None,
    job_days: int | None = None,
    on_demand_hr: float | None = None,
    spot_hr: float | None = None,
    reserved_1yr_hr: float | None = None,
    reserved_3yr_hr: float | None = None,
    return_details: bool = False,
) -> str | dict:
    """Pick a purchasing tier using duty cycle, duration, and spot risk.

    The optional price inputs enable the extended policy.  Spot is selected
    only when its interruption-adjusted hourly cost beats on-demand.  Stable
    high-duty work uses a 1-year rate for jobs shorter than three years and a
    3-year rate only when the supplied duration covers that commitment.

    The plain string return keeps the original public API compatible.  M3 asks
    for details to obtain ``rate_plan`` and the interruption assumption.
    """
    duty = max(0.0, hours_per_day) / 24.0
    be = break_even_utilization(reserved_discount)
    rate = SPOT_INTERRUPTION_RATE_BY_GPU.get(gpu_type or "", 0.05)
    spot_effective_hr = None

    if spot_hr is not None:
        spot_effective_hr = spot_hr * (1.03 + rate * 0.5)

    if interruptible and hours_per_day < 24 and (
        on_demand_hr is None or spot_effective_hr is None or spot_effective_hr < on_demand_hr
    ):
        tier, rate_plan = "spot", "spot"
    elif duty >= be:
        tier = "reserved"
        # Do not claim a 3-year price for a workload whose known horizon is
        # shorter.  With no detailed prices, retain legacy behavior.
        if job_days is not None and reserved_1yr_hr is not None:
            use_3yr = job_days >= 3 * 365 and reserved_3yr_hr is not None
            rate_plan = "reserved_3yr" if use_3yr else "reserved_1yr"
        else:
            rate_plan = "reserved_3yr"
    else:
        tier, rate_plan = "on_demand", "on_demand"

    if not return_details:
        return tier
    return {
        "tier": tier,
        "rate_plan": rate_plan,
        "interruption_rate": rate,
        "spot_effective_hr": spot_effective_hr,
        "duty_cycle": duty,
    }


def spot_checkpoint_cost(
    job_hours: float,
    spot_hr: float,
    on_demand_hr: float,
    interrupt_rate: float = 0.05,      # per-hour chance (H100 spot ~<5%)
    ckpt_overhead_frac: float = 0.03,  # steady cost of writing checkpoints
    rework_hours_per_interrupt: float = 0.5,
) -> dict:
    """Effective cost of running a checkpointable job on spot vs on-demand.

    Interruptions waste the compute since the last checkpoint (rework); checkpointing
    adds a small steady overhead. Spot still wins for interruptible jobs.
    """
    expected_interrupts = job_hours * interrupt_rate
    rework_hours = expected_interrupts * rework_hours_per_interrupt
    effective_hours = job_hours * (1.0 + ckpt_overhead_frac) + rework_hours
    spot_cost = effective_hours * spot_hr
    on_demand_cost = job_hours * on_demand_hr
    savings_pct = (1.0 - spot_cost / on_demand_cost) * 100.0 if on_demand_cost > 0 else 0.0
    return {
        "spot_effective_hours": round(effective_hours, 2),
        "spot_cost": round(spot_cost, 2),
        "on_demand_cost": round(on_demand_cost, 2),
        "savings_pct": round(savings_pct, 1),
    }
