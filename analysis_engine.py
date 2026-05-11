# analysis_engine.py
from typing import Dict, Tuple, Optional

class AnalysisEngine:
    """
    Calculate financial health scores and return color codes
    Color Scheme:
    🟢 Green: Excellent
    🟡 Yellow: Average  
    🟠 Orange: Below Average
    🔴 Red: Poor
    """
    
    BENCHMARKS = {
        "Bank": {
            "debt_to_equity": (5, 8, 12),
            "roe": (15, 10, 5),
            "npl_ratio": (2, 5, 10),
            "car_ratio": (15, 12, 10),
        },
        "General": {
            "debt_to_equity": (0.5, 1.0, 2.0),
            "current_ratio": (2, 1.5, 1),
            "roe": (20, 15, 10),
            "roce": (20, 15, 10),
            "interest_coverage": (5, 3, 1.5),
            "net_margin": (15, 10, 5),
            "fcf_margin": (10, 5, 0),
            "payout_ratio": (40, 60, 80),
            "pe_ratio": (15, 20, 30),
            "ev_ebitda": (8, 12, 16),
            "roic": (15, 10, 5),
            "revenue_growth": (20, 10, 5),
            "eps_growth": (20, 10, 5),
        }
    }
    
    @staticmethod
    def get_color(value: float, benchmarks: Tuple[float, float, float], 
                  higher_is_better: bool = True) -> Tuple[str, str]:
        """
        Returns (color_name, hex_code)
        """
        excellent, average, poor = benchmarks
        
        if higher_is_better:
            if value >= excellent:
                return "Excellent", "#27ae60"
            elif value >= average:
                return "Good", "#2ecc71"
            elif value >= poor:
                return "Average", "#f39c12"
            else:
                return "Poor", "#e74c3c"
        else:
            if value <= excellent:
                return "Excellent", "#27ae60"
            elif value <= average:
                return "Good", "#2ecc71"
            elif value <= poor:
                return "Average", "#f39c12"
            else:
                return "Poor", "#e74c3c"
    
    @staticmethod
    def get_overall_health_color(score: int) -> Tuple[str, str]:
        """Overall health score 0-100"""
        if score >= 80:
            return "Excellent", "#27ae60"
        elif score >= 65:
            return "Good", "#2ecc71"
        elif score >= 50:
            return "Average", "#f39c12"
        elif score >= 35:
            return "Below Average", "#e67e22"
        else:
            return "Poor", "#e74c3c"

    @staticmethod
    def calculate_ratios(data: Dict) -> Dict:
        """Calculate all financial ratios from raw data"""
        ratios = {}
        
        # 1. Debt to Equity
        if data.get("shareholders_equity") and data["shareholders_equity"] > 0:
            ratios["debt_to_equity"] = round(
                data.get("total_debt", 0) / data["shareholders_equity"], 2
            )
        
        # 2. Current Ratio
        if data.get("current_liabilities") and data["current_liabilities"] > 0:
            ratios["current_ratio"] = round(
                data.get("current_assets", 0) / data["current_liabilities"], 2
            )
        
        # 3. ROE (Return on Equity)
        if data.get("shareholders_equity") and data["shareholders_equity"] > 0:
            ratios["roe"] = round(
                (data.get("net_income", 0) / data["shareholders_equity"]) * 100, 2
            )
        
        # 4. ROCE (Return on Capital Employed)
        capital_employed = data.get("shareholders_equity", 0) + data.get("total_debt", 0)
        if capital_employed > 0:
            ratios["roce"] = round(
                (data.get("ebit", 0) / capital_employed) * 100, 2
            )
        
        # 5. ROIC
        invested_capital = data.get("total_debt", 0) + data.get("shareholders_equity", 0) - data.get("cash_and_equivalents", 0)
        if invested_capital > 0:
            nopat = data.get("ebit", 0) * 0.75  # Approximate tax rate 25%
            ratios["roic"] = round((nopat / invested_capital) * 100, 2)
        
        # 6. Interest Coverage
        if data.get("interest_expense") and data["interest_expense"] > 0:
            ratios["interest_coverage"] = round(
                data.get("ebit", 0) / data["interest_expense"], 2
            )
        
        # 7. Net Profit Margin
        if data.get("revenue") and data["revenue"] > 0:
            ratios["net_margin"] = round(
                (data.get("net_income", 0) / data["revenue"]) * 100, 2
            )
            ratios["gross_margin"] = round(
                (data.get("gross_profit", 0) / data["revenue"]) * 100, 2
            )
            ratios["operating_margin"] = round(
                (data.get("operating_income", 0) / data["revenue"]) * 100, 2
            )
        
        # 8. FCF Margin
        if data.get("revenue") and data["revenue"] > 0:
            ratios["fcf_margin"] = round(
                (data.get("free_cash_flow", 0) / data["revenue"]) * 100, 2
            )
        
        # 9. Payout Ratio
        if data.get("eps") and data["eps"] > 0:
            ratios["payout_ratio"] = round(
                (data.get("dps", 0) / data["eps"]) * 100, 2
            )
        
        # 10. P/E Ratio
        if data.get("eps") and data["eps"] > 0:
            ratios["pe_ratio"] = round(
                data.get("current_price", 0) / data["eps"], 2
            )
        
        # 11. P/B Ratio
        if data.get("shares_outstanding") and data["shares_outstanding"] > 0:
            book_value_per_share = data.get("shareholders_equity", 0) / data["shares_outstanding"]
            if book_value_per_share > 0:
                ratios["pb_ratio"] = round(
                    data.get("current_price", 0) / book_value_per_share, 2
                )
        
        # 12. EV/EBITDA
        if data.get("ebitda") and data["ebitda"] > 0:
            enterprise_value = (data.get("current_price", 0) * data.get("shares_outstanding", 0)) + data.get("total_debt", 0) - data.get("cash_and_equivalents", 0)
            ratios["ev_ebitda"] = round(enterprise_value / data["ebitda"], 2)
        
        # 13. EV/Sales
        if data.get("revenue") and data["revenue"] > 0:
            enterprise_value = (data.get("current_price", 0) * data.get("shares_outstanding", 0)) + data.get("total_debt", 0) - data.get("cash_and_equivalents", 0)
            ratios["ev_sales"] = round(enterprise_value / data["revenue"], 2)
        
        # 14. FCF Yield
        if data.get("shares_outstanding") and data["shares_outstanding"] > 0 and data.get("current_price", 0) > 0:
            fcf_per_share = data.get("free_cash_flow", 0) / data["shares_outstanding"]
            ratios["fcf_yield"] = round((fcf_per_share / data["current_price"]) * 100, 2)
        
        return ratios

    @staticmethod
    def calculate_health_score(ratios: Dict, sector: str = "General") -> Dict:
        """Calculate weighted health score and return analysis with colors"""
        
        benchmarks = AnalysisEngine.BENCHMARKS.get(sector, AnalysisEngine.BENCHMARKS["General"])
        
        # Define metrics and their weights
        metrics = [
            {"name": "Debt to Equity", "key": "debt_to_equity", "weight": 10, "higher_better": False},
            {"name": "ROE (%)", "key": "roe", "weight": 15, "higher_better": True},
            {"name": "ROCE (%)", "key": "roce", "weight": 10, "higher_better": True},
            {"name": "ROIC (%)", "key": "roic", "weight": 10, "higher_better": True},
            {"name": "Interest Coverage", "key": "interest_coverage", "weight": 10, "higher_better": True},
            {"name": "Net Margin (%)", "key": "net_margin", "weight": 10, "higher_better": True},
            {"name": "FCF Margin (%)", "key": "fcf_margin", "weight": 10, "higher_better": True},
            {"name": "P/E Ratio", "key": "pe_ratio", "weight": 10, "higher_better": False},
            {"name": "EV/EBITDA", "key": "ev_ebitda", "weight": 10, "higher_better": False},
            {"name": "Payout Ratio (%)", "key": "payout_ratio", "weight": 5, "higher_better": False},
        ]
        
        results = []
        total_score = 0
        total_weight = 0
        
        for metric in metrics:
            value = ratios.get(metric["key"])
            if value is None:
                continue
            
            # Get benchmark for this metric or use General
            benchmark = benchmarks.get(metric["key"], None)
            if benchmark is None:
                benchmark = AnalysisEngine.BENCHMARKS["General"].get(metric["key"])
            if benchmark is None:
                continue
            
            color_name, hex_code = AnalysisEngine.get_color(
                value, benchmark, metric["higher_better"]
            )
            
            # Calculate score for this metric (0-100)
            excellent, average, poor = benchmark
            if metric["higher_better"]:
                if value >= excellent:
                    metric_score = 100
                elif value >= average:
                    metric_score = 75
                elif value >= poor:
                    metric_score = 50
                else:
                    metric_score = 25
            else:
                if value <= excellent:
                    metric_score = 100
                elif value <= average:
                    metric_score = 75
                elif value <= poor:
                    metric_score = 50
                else:
                    metric_score = 25
            
            weighted_score = (metric_score * metric["weight"]) / 100
            total_score += metric_score * metric["weight"]
            total_weight += metric["weight"]
            
            results.append({
                "metric": metric["name"],
                "value": value,
                "weight": metric["weight"],
                "color": hex_code,
                "color_name": color_name,
                "score": metric_score,
            })
        
        # Overall health score
        overall_score = round(total_score / total_weight, 2) if total_weight > 0 else 0
        overall_color_name, overall_color = AnalysisEngine.get_overall_health_color(overall_score)
        
        return {
            "overall_score": overall_score,
            "overall_color": overall_color,
            "overall_color_name": overall_color_name,
            "metrics": results,
            "ratios": ratios,
        }
