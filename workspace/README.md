# Compound interest

Run the example with Python 3:

```sh
python3 compound_interest.py
```

The example invests $1,000 at a decimal annual rate of 0.05, compounded
monthly for 10 years. It displays a final balance of $1,647.01 and interest
earned of $647.01.

Reuse the function:

```python
from compound_interest import compound_interest
balance = compound_interest(1000, 0.05, 12, 10)
interest = balance - 1000
```

Arguments are principal, annual decimal rate, positive integer compounding
frequency per year, and duration in years (fractional years supported).
Principal, rate, and duration must be finite nonnegative real numbers;
invalid inputs raise `ValueError`. Boolean inputs are not accepted.
The formula is `P * (1 + r / n) ** (n * t)`. Calculations use Python's
floating-point precision, with no currency rounding until display.
There are no runtime dependencies beyond the standard library.

Install and run tests:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q
```

Run the task validation (after installing pytest in `.venv`):

```sh
sh /app/workspace/validate-task-20261021-c3ffe2.sh
```
