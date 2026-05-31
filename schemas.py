# schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List

class DCFInputs(BaseModel):
    """DCF ভ্যালুয়েশনের জন্য প্রয়োজনীয় ইনপুট"""
    projection_years: int = Field(default=5, ge=3, le=10)
    growth_rates: List[float] = Field(default_factory=lambda: [0.08, 0.07, 0.06, 0.05, 0.04])
    wacc: float = Field(default=0.15, ge=0.05, le=0.30)
    terminal_growth: float = Field(default=0.03, ge=0.0, le=0.06)
    margin_of_safety: float = Field(default=0.20, ge=0.0, le=0.50)
    tax_rate: float = Field(default=0.25)
    
    # CAPM Advanced (Optional)
    risk_free_rate: Optional[float] = None
    market_risk_premium: Optional[float] = None
    beta: Optional[float] = None

class FinancialDataCreate(BaseModel):
    """ফিন্যান্সিয়াল ডেটা ইনপুট + DCF প্যারামিটার্স"""
    
    # 📅 Core Report Info
    company_id: str
    report_type: str
    year: int
    quarter: Optional[int] = None

    # 📋 Balance Sheet
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    shareholders_equity: float = 0.0
    total_debt: float = 0.0
    cash_and_equivalents: float = 0.0
    current_assets: float = 0.0
    current_liabilities: float = 0.0

    # 📈 Income Statement
    revenue: float = 0.0
    gross_profit: float = 0.0
    operating_income: float = 0.0
    ebit: float = 0.0
    ebitda: float = 0.0
    interest_expense: float = 0.0
    net_income: float = 0.0

    # 💵 Cash Flow
    operating_cash_flow: float = 0.0
    capex: float = 0.0
    free_cash_flow: float = 0.0

    # 📊 Per Share Data
    eps: float = 0.0
    dps: float = 0.0
    shares_outstanding: float = 0.0
    current_price: float = 0.0

    # 🏦 Bank Specific (Optional)
    total_deposits: Optional[float] = None
    total_loans: Optional[float] = None
    net_interest_income: Optional[float] = None
    npl_ratio: Optional[float] = None
    car_ratio: Optional[float] = None

    # 📊 DCF & Dividend (Optional)
    dcf_params: Optional[DCFInputs] = None
    dividend_growth_rate: Optional[float] = None