#!/usr/bin/env python3
"""Dynamic-scope wrapper for the exploratory HBT learning assessment.

Includes every dated forensic audit currently preserved in the registry, while
retaining the v1 downstream-only/no-retune semantics.
"""
from __future__ import annotations

import re
import hbt_learning_assessment_v1 as base


def forensic_dates() -> list[str]:
    out=[]
    for p in base.FORENSIC.glob('hbt_forensic_*.json'):
        m=re.fullmatch(r'hbt_forensic_(\d{4}-\d{2}-\d{2})\.json',p.name)
        if m: out.append(m.group(1))
    return sorted(set(out))


def main() -> int:
    dates=forensic_dates()
    if not dates: raise SystemExit('no dated forensic evidence available')
    base.DATES=dates
    base.VERSION='HBT-LEARNING-ASSESSMENT-2-DYNAMIC-SCOPE'
    return base.main()


if __name__=='__main__':raise SystemExit(main())
