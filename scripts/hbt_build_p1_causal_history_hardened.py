#!/usr/bin/env python3
"""Deterministic identity hardening for HBT-1.2R P1 causal research.

Research-only provider naming aliases. No predictive coefficients or feature
formulas are changed here.
"""
from __future__ import annotations
import hbt_build_p1_causal_history as builder

builder.ALIASES.update({
    "lille osc": "losc lille",
    "olympique lyonnais": "olympique lyon",
})

if __name__ == "__main__":
    raise SystemExit(builder.main())
