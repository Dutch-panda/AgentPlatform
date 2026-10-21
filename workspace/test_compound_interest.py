import pytest

from compound_interest import compound_interest


def test_known_example():
    balance = compound_interest(1000, 0.05, 12, 10)
    assert balance == pytest.approx(1647.00949769028)
    assert balance - 1000 == pytest.approx(647.00949769028)
    assert balance != round(balance, 2)


@pytest.mark.parametrize('principal,rate,frequency,years,expected', [
    (0, 0.05, 12, 10, 0),
    (1000, 0, 12, 10, 1000),
    (1000, 0.05, 12, 0, 1000),
    (1000, 0.12, 1, 1, 1120),
    (1000, 0.12, 2, 1, 1123.6),
    (1000, 0.12, 12, 1, 1126.82503013197),
    (1000, 0.12, 4, 0.5, 1060.9),
    (1000, 0.21, 1, 0.5, 1100),
])
def test_balances(principal, rate, frequency, years, expected):
    assert compound_interest(principal, rate, frequency, years) == pytest.approx(expected)


@pytest.mark.parametrize('position,bad_value', [
    (0, -1), (1, -0.01), (3, -1),
    (2, 0), (2, -12), (2, 1.5), (2, 12.0), (2, True),
    (0, float('nan')), (1, float('inf')), (3, float('-inf')),
    (0, '1000'), (1, None), (3, True),
])
def test_invalid_inputs(position, bad_value):
    args = [1000, 0.05, 12, 10]
    args[position] = bad_value
    with pytest.raises(ValueError):
        compound_interest(*args)
