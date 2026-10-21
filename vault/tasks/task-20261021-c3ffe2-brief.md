---
id: "task-20261021-c3ffe2"
type: "task-brief"
agent: "natasha"
target_lead: "meti"
created_at: "2026-10-21"
links: []
---
# Task: Implement and test a Python compound-interest calculator

## Assignment
- **Target Lead:** METI

## Objective
Create a simple Python script exposing a reusable function that calculates the final balance using A = P * (1 + r / n) ** (n * t), where P is the principal, r is the annual interest rate expressed as a decimal, n is the positive integer number of compounding periods per year, and t is the duration in years. Make the script runnable with a small example and report both final balance and interest earned (A - P). Validate inputs: principal, rate, and duration must be nonnegative, and compounding frequency must be a positive integer. Keep calculation precision internally and round only displayed currency values. Add pytest tests covering a known compound-interest example, zero principal, zero interest, zero duration, different compounding frequencies, fractional-year durations, and invalid inputs. Use pytest.approx for floating-point assertions. Include brief instructions for running the script and installing and running pytest. Keep the implementation minimal, with no unnecessary dependencies.

## Scope & Questions
