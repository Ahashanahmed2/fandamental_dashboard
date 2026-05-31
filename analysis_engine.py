# analysis_engine.py
import numpy as np
from typing import Dict, List, Optional, Any
from schemas import DCFInputs

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
            fcf_values.append(max(0, projected))

        return fcf_values

    @staticmethod
    def calculate_terminal_value(
        final_fcf: float,
        terminal_growth: float,
        wacc: float
    ) -> float:
        """Gordon Growth Model দিয়ে টার্মিনাল ভ্যালু"""
        if wacc <= terminal_growth:
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
        dcf_inputs,  # DCFInputs অথবা Dict - দুটোই accept করবে
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

        # ২. DCF প্যারামিটার্স এক্সট্রাক্ট (DCFInputs অথবা Dict থেকে)
        if isinstance(dcf_inputs, DCFInputs):
            # DCFInputs অবজেক্ট থেকে
            wacc = dcf_inputs.wacc
            projection_years = dcf_inputs.projection_years
            growth_rates = dcf_inputs.growth_rates[:projection_years]
            terminal_growth = dcf_inputs.terminal_growth
            margin_of_safety = dcf_inputs.margin_of_safety
            tax_rate = dcf_inputs.tax_rate
            
            # CAPM parameters (optional)
            beta = dcf_inputs.beta
            risk_free_rate = dcf_inputs.risk_free_rate
            market_risk_premium = dcf_inputs.market_risk_premium
        else:
            # Dict থেকে
            wacc = dcf_inputs.get("wacc", 0.15)
            projection_years = dcf_inputs.get("projection_years", 5)
            growth_rates = dcf_inputs.get("growth_rates", [0.08, 0.07, 0.06, 0.05, 0.04])[:projection_years]
            terminal_growth = dcf_inputs.get("terminal_growth", 0.03)
            margin_of_safety = dcf_inputs.get("margin_of_safety", 0.20)
            tax_rate = dcf_inputs.get("tax_rate", 0.25)
            
            # CAPM parameters (optional)
            beta = dcf_inputs.get("beta")
            risk_free_rate = dcf_inputs.get("risk_free_rate")
            market_risk_premium = dcf_inputs.get("market_risk_premium")

        # WACC ক্যালকুলেশন (CAPM থেকে যদি প্যারামিটার থাকে)
        if beta and risk_free_rate and market_risk_premium:
            cost_of_equity = risk_free_rate + beta * market_risk_premium
            equity_value = current_price * shares_outstanding if current_price > 0 else 1
            debt_value = financial_data.get("total_debt", 0) or 0
            wacc = DCFValuation.calculate_wacc(
                equity_value, 
                debt_value,
                cost_of_equity, 
                wacc * 0.7,
                tax_rate
            )

        # ৩. FCF প্রজেকশন
        fcf_projections = DCFValuation.project_fcf(
            current_fcf, 
            growth_rates,
            revenue,
            fcf_margin
        )

        # ৪. টার্মিনাল ভ্যালু
        terminal_value = DCFValuation.calculate_terminal_value(
            fcf_projections[-1] if fcf_projections else 0,
            terminal_growth,
            wacc
        )

        # ৫. ডিসকাউন্টিং
        discounted = DCFValuation.discount_cash_flows(fcf_projections, terminal_value, wacc)

        # ৬. ইকুইটি ভ্যালু ও শেয়ার প্রাইস
        enterprise_value = discounted["enterprise_value"]
        equity_value = enterprise_value - net_debt
        intrinsic_value_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else 0

        # ৭. মার্জিন অফ সেফটি অ্যাপ্লাই
        mos_adjusted_value = intrinsic_value_per_share * (1 - margin_of_safety)

        # ৮. ভ্যালুয়েশন সিগন্যাল
        if current_price > 0:
            upside = ((intrinsic_value_per_share - current_price) / current_price) * 100
            if intrinsic_value_per_share > current_price * (1 + margin_of_safety):
                signal = "BUY"
                signal_color = "#10b981"
            elif intrinsic_value_per_share < current_price * (1 - margin_of_safety):
                signal = "SELL"
                signal_color = "#ef4444"
            else:
                signal = "HOLD"
                signal_color = "#f59e0b"
        else:
            upside = None
            signal = "N/A"
            signal_color = "#64748b"

        return {
            "inputs": {
                "wacc_percent": round(wacc * 100, 2),
                "terminal_growth_percent": round(terminal_growth * 100, 2),
                "projection_years": projection_years,
                "margin_of_safety_percent": round(margin_of_safety * 100, 2),
                "growth_rates_percent": [round(g*100, 1) for g in growth_rates]
            },
            "enterprise_value": round(enterprise_value, 2),
            "equity_value": round(equity_value, 2),
            "intrinsic_value_per_share": round(intrinsic_value_per_share, 2),
            "mos_adjusted_value": round(mos_adjusted_value, 2),
            "current_price": current_price,
            "upside_percent": round(upside, 2) if upside else None,
            "signal": signal,
            "signal_color": signal_color,
            "fcf_projections": [round(f, 2) for f in fcf_projections],
            "pv_fcf_sum": round(discounted["pv_fcf"], 2),
            "pv_terminal": round(discounted["pv_terminal"], 2),
            "terminal_value": round(terminal_value, 2),
            "net_debt": round(net_debt, 2),
            "calculation_note": "DCF based on Free Cash Flow projection with Gordon Growth Terminal Value"
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
                final_fcf = base_fcf * np.prod([1+g for g in growth_rates])
                tv = (final_fcf * (1+tg)) / (wacc - tg)
                pv_tv = tv / (1+wacc)**len(growth_rates)
                equity = pv_tv - net_debt
                value_per_share = equity / shares if shares > 0 else 0
                row["values"][f"{round(tg*100,1)}%"] = round(value_per_share, 2)
            results.append(row)

        return results


# ==================== Analysis Engine ====================

class AnalysisEngine:
    """Financial Analysis Engine - Core analysis logic"""

    def __init__(self):
        self.benchmarks = {
            "Bank": {
                "debt_to_equity": 10.0,
                "current_ratio": 1.0,
                "roe": 12.0,
                "npl_ratio": 5.0,
                "car_ratio": 10.0
            },
            "Pharmaceuticals": {
                "debt_to_equity": 1.0,
                "current_ratio": 1.5,
                "roe": 15.0,
                "gross_margin": 40.0
            },
            "General": {
                "debt_to_equity": 1.5,
                "current_ratio": 1.5,
                "roe": 12.0,
                "gross_margin": 25.0
            }
        }

    def calculate_ratios(self, data: Dict) -> Dict:
        """Calculate financial ratios from raw data"""
        ratios = {}

        total_assets = data.get('total_assets', 0)
        total_liabilities = data.get('total_liabilities', 0)
        shareholders_equity = data.get('shareholders_equity', 0)
        total_debt = data.get('total_debt', 0)
        current_assets = data.get('current_assets', 0)
        current_liabilities = data.get('current_liabilities', 0)

        revenue = data.get('revenue', 0)
        gross_profit = data.get('gross_profit', 0)
        operating_income = data.get('operating_income', 0)
        ebit = data.get('ebit', 0)
        ebitda = data.get('ebitda', 0)
        interest_expense = data.get('interest_expense', 0)
        net_income = data.get('net_income', 0)

        operating_cash_flow = data.get('operating_cash_flow', 0)
        capex = data.get('capex', 0)
        free_cash_flow = data.get('free_cash_flow', 0)

        eps = data.get('eps', 0)
        dps = data.get('dps', 0)
        shares_outstanding = data.get('shares_outstanding', 1)
        current_price = data.get('current_price', 0)

        # Calculate Ratios
        ratios['debt_to_equity'] = round(total_debt / shareholders_equity, 2) if shareholders_equity > 0 else 0
        ratios['current_ratio'] = round(current_assets / current_liabilities, 2) if current_liabilities > 0 else 0
        ratios['quick_ratio'] = round((current_assets - 0) / current_liabilities, 2) if current_liabilities > 0 else 0

        ratios['gross_margin'] = round((gross_profit / revenue) * 100, 2) if revenue > 0 else 0
        ratios['operating_margin'] = round((operating_income / revenue) * 100, 2) if revenue > 0 else 0
        ratios['net_margin'] = round((net_income / revenue) * 100, 2) if revenue > 0 else 0

        ratios['roe'] = round((net_income / shareholders_equity) * 100, 2) if shareholders_equity > 0 else 0
        ratios['roa'] = round((net_income / total_assets) * 100, 2) if total_assets > 0 else 0

        ratios['interest_coverage'] = round(ebit / interest_expense, 2) if interest_expense > 0 else 999

        ratios['pe_ratio'] = round(current_price / eps, 2) if eps > 0 else 0
        ratios['pb_ratio'] = round(current_price / (shareholders_equity / shares_outstanding), 2) if shares_outstanding > 0 and shareholders_equity > 0 else 0
        ratios['dividend_yield'] = round((dps / current_price) * 100, 2) if current_price > 0 else 0
        ratios['payout_ratio'] = round((dps / eps) * 100, 2) if eps > 0 else 0

        ratios['ev_to_ebitda'] = round((total_debt + (current_price * shares_outstanding) - data.get('cash_and_equivalents', 0)) / ebitda, 2) if ebitda > 0 else 0

        ratios['fcf_yield'] = round((free_cash_flow / (current_price * shares_outstanding)) * 100, 2) if current_price > 0 and shares_outstanding > 0 else 0

        if data.get('total_deposits'):
            ratios['npl_ratio'] = data.get('npl_ratio', 0)
            ratios['car_ratio'] = data.get('car_ratio', 0)
            ratios['loan_to_deposit'] = round((data.get('total_loans', 0) / data.get('total_deposits', 1)) * 100, 2)

        return ratios

    def calculate_health_score(self, ratios: Dict, sector: str = "General") -> Dict:
        """Calculate overall financial health score"""
        sector_benchmarks = self.benchmarks.get(sector, self.benchmarks["General"])
        metrics = []
        total_score = 0
        total_weight = 0

        scoring_criteria = [
            {
                "metric": "Debt to Equity",
                "value": f"{ratios.get('debt_to_equity', 0):.2f}x",
                "actual": ratios.get('debt_to_equity', 0),
                "benchmark": sector_benchmarks.get('debt_to_equity', 1.5),
                "weight": 10,
                "lower_is_better": True
            },
            {
                "metric": "Current Ratio",
                "value": f"{ratios.get('current_ratio', 0):.2f}x",
                "actual": ratios.get('current_ratio', 0),
                "benchmark": sector_benchmarks.get('current_ratio', 1.5),
                "weight": 10,
                "lower_is_better": False
            },
            {
                "metric": "ROE",
                "value": f"{ratios.get('roe', 0):.1f}%",
                "actual": ratios.get('roe', 0),
                "benchmark": sector_benchmarks.get('roe', 12),
                "weight": 15,
                "lower_is_better": False
            },
            {
                "metric": "Net Margin",
                "value": f"{ratios.get('net_margin', 0):.1f}%",
                "actual": ratios.get('net_margin', 0),
                "benchmark": 10,
                "weight": 15,
                "lower_is_better": False
            },
            {
                "metric": "Interest Coverage",
                "value": f"{ratios.get('interest_coverage', 0):.2f}x",
                "actual": ratios.get('interest_coverage', 0),
                "benchmark": 3,
                "weight": 15,
                "lower_is_better": False
            },
            {
                "metric": "P/E Ratio",
                "value": f"{ratios.get('pe_ratio', 0):.2f}x",
                "actual": ratios.get('pe_ratio', 0),
                "benchmark": 15,
                "weight": 15,
                "lower_is_better": True
            },
            {
                "metric": "Dividend Yield",
                "value": f"{ratios.get('dividend_yield', 0):.1f}%",
                "actual": ratios.get('dividend_yield', 0),
                "benchmark": 3,
                "weight": 10,
                "lower_is_better": False
            },
            {
                "metric": "FCF Yield",
                "value": f"{ratios.get('fcf_yield', 0):.1f}%",
                "actual": ratios.get('fcf_yield', 0),
                "benchmark": 5,
                "weight": 10,
                "lower_is_better": False
            }
        ]

        for criteria in scoring_criteria:
            actual = criteria['actual']
            benchmark = criteria['benchmark']
            weight = criteria['weight']

            if criteria['lower_is_better']:
                if actual <= 0:
                    score = 0
                else:
                    ratio = benchmark / actual
                    score = min(100, ratio * 50)
            else:
                if benchmark <= 0:
                    score = 0
                else:
                    ratio = actual / benchmark
                    score = min(100, ratio * 50)

            if score >= 80:
                color = "#10b981"
                color_name = "Excellent"
            elif score >= 60:
                color = "#3b82f6"
                color_name = "Good"
            elif score >= 40:
                color = "#f59e0b"
                color_name = "Average"
            elif score >= 20:
                color = "#ef4444"
                color_name = "Poor"
            else:
                color = "#dc2626"
                color_name = "Critical"

            metrics.append({
                "metric": criteria['metric'],
                "value": criteria['value'],
                "score": round(score, 1),
                "color": color,
                "color_name": color_name,
                "weight": weight
            })

            total_score += score * weight
            total_weight += weight

        overall_score = round(total_score / total_weight, 1) if total_weight > 0 else 0

        if overall_score >= 80:
            overall_color = "#10b981"
            overall_color_name = "Excellent"
        elif overall_score >= 60:
            overall_color = "#3b82f6"
            overall_color_name = "Good"
        elif overall_score >= 40:
            overall_color = "#f59e0b"
            overall_color_name = "Average"
        elif overall_score >= 20:
            overall_color = "#ef4444"
            overall_color_name = "Poor"
        else:
            overall_color = "#dc2626"
            overall_color_name = "Critical"

        return {
            "overall_score": overall_score,
            "overall_color": overall_color,
            "overall_color_name": overall_color_name,
            "metrics": metrics,
            "ratios": ratios
        }