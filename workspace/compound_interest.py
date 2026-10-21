"""Calculate compound interest without rounding intermediate values."""

from math import isfinite
from numbers import Real


def compound_interest(principal, rate, frequency, years):
    """Return the final balance; rate is decimal and frequency is per year.

    Raise ValueError for invalid or non-finite inputs. Currency rounding is
    left to the caller so the returned balance retains calculation precision.
    """
    for name, value in (("principal", principal), ("rate", rate), ("years", years)):
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must be a finite nonnegative number")
        if not isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a finite nonnegative number")
    if isinstance(frequency, bool) or not isinstance(frequency, int) or frequency <= 0:
        raise ValueError("frequency must be a positive integer")
    return principal * (1 + rate / frequency) ** (frequency * years)


if __name__ == "__main__":
    principal = 1000
    balance = compound_interest(principal, 0.05, 12, 10)
    print(f"Final balance: ${balance:,.2f}")
    print(f"Interest earned: ${balance - principal:,.2f}")
