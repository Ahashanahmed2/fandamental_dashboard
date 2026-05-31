# analysis_engine.py
import numpy as np
from typing import Dict, List, Optional
from schemas import DCFInputs  # 🆕 DCFInputs ইমপোর্ট অ্যাড করা হয়েছে

class DCFValuation:
    """Discounted Cash Flow ভ্যালুয়েশন ইঞ্জিন"""

    @staticmethod
    def calculate_wacc(
        equity_value: float,
        debt_value: float,
        cost_of_equity: float,
        cost_of_debt: float,
        tax_rate: float = 0.25
    ) -> float:
        """WACC ক্যালকুলেশন (ঐচ্ছিক - CAPM সাপোর্ট)"""
        total_value = equity_value + debt_value
        if total_value == 0:
            return cost_of_equity

        we = equity_value / total_value
        wd = debt_value / total_value
        return (we * cost_of_equity) + (wd * cost_of_debt * (1 - tax_rate))

    @staticmethod
    def project_fcf(
        current_fcf: float,
        growth_rates: List[float],
        revenue: float,
        fcf_margin: float
    ) -> List[float]:
        """ফিউচার FCF প্রজেকশন"""
        fcf_values = []
        base_fcf = current_fcf if current_fcf > 0 else revenue * fcf_margin

        for i, growth in enumerate(growth_rates):
            if i == 0:
                projected = base_fcf * (1 + growth)
            else:
                projected = fcf_values[-1] * (1 + growth)
            fcf_values.append(max(0, projected))  # নেগেটিভ FCF হ্যান্ডেল

        return fcf_values

    @staticmethod
    def calculate_terminal_value(
        final_fcf: float,
        terminal_growth: float,
        wacc: float    ) -> float:
        """Gordon Growth Model দিয়ে টার্মিনাল ভ্যালু"""  # 🆕 নিউলাইন ফিক্স
        if wacc <= terminal_growth:
            # সেফটি চেক: wacc অবশ্যই terminal growth-এর চেয়ে বড় হতে হবে
            terminal_growth = wacc - 0.02
        return (final_fcf * (1 + terminal_growth)) / (wacc - terminal_growth)

    @staticmethod
    def discount_cash_flows(
        fcf_values: List[float],
        terminal_value: float,
        wacc: float
    ) -> Dict[str, float]:
        """সব ক্যাশ ফ্লোকে ডিসকাউন্ট করে Present Value বের করা"""
        pv_fcf = sum([fcf / (1 + wacc)**(i+1) for i, fcf in enumerate(fcf_values)])
        pv_terminal = terminal_value / (1 + wacc)**len(fcf_values)

        return {
            "pv_fcf": pv_fcf,
            "pv_terminal": pv_terminal,
            "enterprise_value": pv_fcf + pv_terminal
        }

    @staticmethod
    def run_dcf(
        financial_data: Dict,
        dcf_inputs: DCFInputs,  # ✅ এখন DCFImports ইমপোর্টেড আছে
        company_info: Dict
    ) -> Dict:
        """মেইন DCF ক্যালকুলেশন ফাংশন"""

        # ১. বেসিক ডেটা এক্সট্রাক্ট
        revenue = financial_data.get("revenue", 0) or 0
        current_fcf = financial_data.get("free_cash_flow", 0) or 0
        fcf_margin = financial_data.get("fcf_margin", 0) or (current_fcf / revenue if revenue > 0 else 0.05)

        shares_outstanding = financial_data.get("shares_outstanding", 1) or 1
        net_debt = (financial_data.get("total_debt", 0) or 0) - (financial_data.get("cash_and_equivalents", 0) or 0)
        current_price = financial_data.get("current_price", 0) or 0

        # ২. WACC ক্যালকুলেশন (ইনপুট বা অটো)
        wacc = dcf_inputs.wacc
        if dcf_inputs.beta and dcf_inputs.risk_free_rate and dcf_inputs.market_risk_premium:
            # CAPM: Cost of Equity = Rf + β(Rm - Rf)
            cost_of_equity = dcf_inputs.risk_free_rate + dcf_inputs.beta * dcf_inputs.market_risk_premium
            equity_value = current_price * shares_outstanding if current_price > 0 else 1
            debt_value = financial_data.get("total_debt", 0) or 0
            wacc = DCFValuation.calculate_wacc(
                equity_value, 
                debt_value,                 cost_of_equity, 
                dcf_inputs.wacc * 0.7,  # cost_of_debt estimate
                dcf_inputs.tax_rate  # 🆕 কমা ফিক্স করা হয়েছে
            )

        # ৩. FCF প্রজেকশন
        growth_rates = dcf_inputs.revenue_growth_rates[:dcf_inputs.projection_years]
        fcf_projections = DCFValuation.project_fcf(
            current_fcf, 
            growth_rates,
            revenue,
            fcf_margin
        )

        # ৪. টার্মিনাল ভ্যালু
        terminal_value = DCFValuation.calculate_terminal_value(
            fcf_projections[-1] if fcf_projections else 0,
            dcf_inputs.terminal_growth_rate,
            wacc
        )

        # ৫. ডিসকাউন্টিং
        discounted = DCFValuation.discount_cash_flows(fcf_projections, terminal_value, wacc)

        # ৬. ইকুইটি ভ্যালু ও শেয়ার প্রাইস
        enterprise_value = discounted["enterprise_value"]
        equity_value = enterprise_value - net_debt
        intrinsic_value_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else 0

        # ৭. মার্জিন অফ সেফটি অ্যাপ্লাই
        mos_adjusted_value = intrinsic_value_per_share * (1 - dcf_inputs.margin_of_safety)

        # ৮. ভ্যালুয়েশন সিগন্যাল
        if current_price > 0:
            upside = ((intrinsic_value_per_share - current_price) / current_price) * 100
            if intrinsic_value_per_share > current_price * (1 + dcf_inputs.margin_of_safety):
                signal = "BUY"
                signal_color = "#10b981"
            elif intrinsic_value_per_share < current_price * (1 - dcf_inputs.margin_of_safety):
                signal = "SELL"
                signal_color = "#ef4444"
            else:
                signal = "HOLD"
                signal_color = "#f59e0b"
        else:
            upside = None
            signal = "N/A"
            signal_color = "#64748b"

        return {            # ইনপুট সামারি
            "inputs": {
                "wacc": round(wacc * 100, 2),
                "terminal_growth": round(dcf_inputs.terminal_growth_rate * 100, 2),
                "projection_years": dcf_inputs.projection_years,
                "margin_of_safety": round(dcf_inputs.margin_of_safety * 100, 2)
            },
            # রেজাল্ট
            "enterprise_value": round(enterprise_value, 2),
            "equity_value": round(equity_value, 2),
            "intrinsic_value_per_share": round(intrinsic_value_per_share, 2),
            "mos_adjusted_value": round(mos_adjusted_value, 2),
            "current_price": current_price,
            "upside_percent": round(upside, 2) if upside else None,
            "signal": signal,
            "signal_color": signal_color,
            # ডিটেইলস
            "fcf_projections": [round(f, 2) for f in fcf_projections],
            "pv_fcf": round(discounted["pv_fcf"], 2),
            "pv_terminal": round(discounted["pv_terminal"], 2),
            "terminal_value": round(terminal_value, 2),
            # মেটাডেটা
            "calculation_date": financial_data.get("created_at"),
            "company_ticker": company_info.get("ticker")
        }

    @staticmethod
    def sensitivity_analysis(
        base_fcf: float,
        growth_rates: List[float],
        terminal_growth: float,
        shares: float,
        net_debt: float,
        wacc_range: List[float] = None,
        growth_range: List[float] = None
    ) -> List[Dict]:
        """সেনসিটিভিটি অ্যানালাইসিস: WACC vs Terminal Growth ম্যাট্রিক্স"""
        if wacc_range is None:
            wacc_range = [0.12, 0.14, 0.16, 0.18, 0.20]
        if growth_range is None:
            growth_range = [0.02, 0.03, 0.04, 0.05]

        results = []
        for wacc in wacc_range:
            row = {"wacc": round(wacc*100, 1), "values": {}}
            for tg in growth_range:
                if wacc <= tg:
                    continue
                # সিম্পল টার্মিনাল-ফোকাসড ক্যালকুলেশন
                final_fcf = base_fcf * np.prod([1+g for g in growth_rates])                tv = (final_fcf * (1+tg)) / (wacc - tg)
                pv_tv = tv / (1+wacc)**len(growth_rates)
                equity = pv_tv - net_debt
                value_per_share = equity / shares if shares > 0 else 0  # 🆕 নিউলাইন ফিক্স
                row["values"][f"{round(tg*100,1)}%"] = round(value_per_share, 2)
            results.append(row)

        return results