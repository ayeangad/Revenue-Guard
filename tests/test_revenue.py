from domain.revenue import estimate_counterfactual


def test_counterfactual_math():
    r = estimate_counterfactual(12000, 0.038, 0.025, 84.0)
    assert r.expected_orders == 456.0
    assert r.observed_orders == 300.0
    assert r.lost_orders == 156.0
    assert r.estimated_impact == 156.0 * 84.0
    assert r.reliable is True


def test_refuses_without_traffic():
    r = estimate_counterfactual(0, 0.038, 0.0, 84.0)
    assert r.reliable is False
