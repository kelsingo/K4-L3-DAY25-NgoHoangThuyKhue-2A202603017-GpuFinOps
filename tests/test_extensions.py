"""Student-authored tests for Your Turn Extensions 1 and 3."""
from finops import pricing


def test_cache_break_even_and_decision():
    # Write costs 1.25x input; each cached read saves 0.9x input.
    threshold = pricing.cache_break_even_reads(1.25, 1.0, read_discount=0.10)
    assert abs(threshold - (1.25 / 0.9)) < 1e-9
    assert not pricing.cache_is_worth_it(1.0, 1.25, price_in_per_m=1.0)
    assert pricing.cache_is_worth_it(2.0, 1.25, price_in_per_m=1.0)


def test_tier_uses_gpu_risk_and_reservation_duration():
    spot = pricing.recommend_tier(
        8,
        True,
        gpu_type="A10G",
        job_days=30,
        on_demand_hr=1.0,
        spot_hr=0.4,
        reserved_1yr_hr=0.8,
        reserved_3yr_hr=0.6,
        return_details=True,
    )
    assert spot["tier"] == "spot"
    assert spot["interruption_rate"] == 0.10

    one_year = pricing.recommend_tier(
        24,
        False,
        gpu_type="A100",
        job_days=365,
        reserved_1yr_hr=1.4,
        reserved_3yr_hr=1.0,
        return_details=True,
    )
    three_year = pricing.recommend_tier(
        24,
        False,
        gpu_type="A100",
        job_days=3 * 365,
        reserved_1yr_hr=1.4,
        reserved_3yr_hr=1.0,
        return_details=True,
    )
    assert one_year["rate_plan"] == "reserved_1yr"
    assert three_year["rate_plan"] == "reserved_3yr"
