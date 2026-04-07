# =============================================================================
# valuation/buffett.py — Warren Buffett Owner Earnings Method
#
# Owner Earnings = Net Profit + Depreciation − Maintenance Capex
# Maintenance Capex ≈ Total Capex × 0.6 (rule of thumb)
#
# IV = Owner Earnings / (Discount Rate − Growth Rate)
#    = Owner Earnings × 16.67  (at r=12%, g=6%)
#
# Also computes Earnings Yield vs G-Sec yield comparison.
# =============================================================================

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    get_discount_rate, TERMINAL_GROWTH_RATE,
    MAINTENANCE_CAPEX_RATIO, GSEC_10Y_YIELD
)


def calculate(data: dict) -> dict:
    """
    Returns:
      {
        "model"             : "Buffett",
        "iv"                : float or None,
        "owner_earnings"    : float,
        "owner_earnings_ps" : float,   # per share
        "multiplier"        : float,
        "earnings_yield"    : float,   # % — compare vs G-Sec
        "gsec_yield"        : float,
        "yield_verdict"     : str,
        "inputs_used"       : dict,
        "note"              : str,
        "valid"             : bool
      }
    """
    net_profit  = data.get("net_profit_ttm")
    depreciation= data.get("depreciation_ttm") or 0
    capex       = data.get("capex_ttm") or 0
    shares      = data.get("shares_outstanding")
    eps         = data.get("eps_ttm")
    cmp         = data.get("cmp")
    g_rate      = data.get("eps_growth_5y") or 0.06
    beta        = data.get("beta") or 1.0

    # ── Validation ─────────────────────────────────────────────────────────
    if not net_profit:
        return _invalid("Net Profit missing — Owner Earnings cannot be computed")

    if net_profit <= 0:
        return _invalid("Net Profit is negative — Owner Earnings not applicable")

    # ── Owner Earnings (Trend-Based) ────────────────────────────────────────
    # Buffett's Rule: Maintenance Capex is the expense required to maintain unit volume.
    # Technical Heuristic: Use 5-year averages to "smooth" out one-time growth capex.
    
    capex_5y = [abs(v) for v in (data.get("capex_5y") or []) if v is not None]
    depr_5y  = [v for v in (data.get("depreciation_5y") or []) if v is not None]
    
    if len(capex_5y) >= 3 and len(depr_5y) >= 3:
        avg_capex = sum(capex_5y) / len(capex_5y)
        avg_depr  = sum(depr_5y) / len(depr_5y)
        
        # If Average Capex > Average Depreciation, the company is likely spending on growth.
        # Depreciation is the best proxy for "maintenance" in a steady state.
        maintenance_capex = min(avg_capex, avg_depr)
        maint_method = "5Y Trend (Min of Avg Capex/Depr)"
    else:
        # Fallback to TTM snapshot if history is missing
        if depreciation and capex:
            maintenance_capex = min(capex, depreciation)
            maint_method = "TTM Snapshot (Min Capex/Depr)"
        else:
            maintenance_capex = capex * MAINTENANCE_CAPEX_RATIO if capex else depreciation
            maint_method = "Fallback Ratio/Depr"

    owner_earnings = net_profit + depreciation - maintenance_capex

    if owner_earnings <= 0:
        return _invalid(
            f"Owner Earnings negative after {maint_method} deduction "
            "(very capital-intensive business)"
        )

    # ── Sustainable Growth Rate ─────────────────────────────────────────────
    # Use lower of: reported growth or 12% cap for terminal assumption
    g = min(g_rate, 0.12)
    r = get_discount_rate(beta)

    if r <= g:
        g = r * 0.5   # Fallback if growth >= discount rate

    # ── Multiplier & Intrinsic Value ────────────────────────────────────────
    # Gordon Growth style: IV = Owner Earnings / (r - g)
    multiplier = 1 / (r - g)
    total_iv   = owner_earnings * multiplier

    # Add cash, subtract debt
    cash = data.get("cash") or 0
    debt = data.get("total_debt") or 0
    equity_value = total_iv + cash - debt

    # Per share
    if not shares or shares <= 0:
        return _invalid("Shares outstanding missing")

    iv_per_share       = equity_value / shares
    owner_earnings_ps  = owner_earnings / shares

    # ── Earnings Yield ──────────────────────────────────────────────────────
    if eps and cmp and cmp > 0:
        earnings_yield = (eps / cmp) * 100
    elif owner_earnings_ps and cmp and cmp > 0:
        earnings_yield = (owner_earnings_ps / cmp) * 100
    else:
        earnings_yield = None

    gsec = GSEC_10Y_YIELD * 100  # as %
    if earnings_yield:
        if earnings_yield >= gsec + 2:
            yield_verdict = f"STOCK ATTRACTIVE (EY {earnings_yield:.1f}% >> G-Sec {gsec:.1f}%)"
        elif earnings_yield >= gsec:
            yield_verdict = f"STOCK MARGINALLY BETTER (EY {earnings_yield:.1f}% > G-Sec {gsec:.1f}%)"
        else:
            yield_verdict = f"BONDS BETTER (G-Sec {gsec:.1f}% > EY {earnings_yield:.1f}%)"
    else:
        yield_verdict = "N/A"

    note = (
        f"Maintenance capex = {MAINTENANCE_CAPEX_RATIO*100:.0f}% of total capex. "
        f"Growth capped at {g*100:.1f}% for terminal assumption."
    )

    return {
        "model"             : "Buffett",
        "iv"                : round(max(iv_per_share, 0), 2),
        "owner_earnings"    : round(owner_earnings, 2),
        "owner_earnings_ps" : round(owner_earnings_ps, 2),
        "multiplier"        : round(multiplier, 2),
        "earnings_yield"    : round(earnings_yield, 2) if earnings_yield else None,
        "gsec_yield"        : gsec,
        "yield_verdict"     : yield_verdict,
        "inputs_used"       : {
            "net_profit_cr"    : round(net_profit / 1e7, 1),
            "depreciation_cr"  : round(depreciation / 1e7, 1),
            "maint_capex_cr"   : round(maintenance_capex / 1e7, 1),
            "owner_earnings_cr": round(owner_earnings / 1e7, 1),
            "growth_used"      : f"{g*100:.1f}%",
            "discount_rate"    : f"{r*100:.1f}%",
            "multiplier"       : round(multiplier, 2),
        },
        "note"  : note,
        "valid" : True
    }


def _invalid(reason: str) -> dict:
    return {
        "model": "Buffett", "iv": None,
        "owner_earnings": None, "owner_earnings_ps": None,
        "multiplier": None, "earnings_yield": None,
        "gsec_yield": GSEC_10Y_YIELD * 100,
        "yield_verdict": "N/A",
        "inputs_used": {}, "note": reason, "valid": False
    }
