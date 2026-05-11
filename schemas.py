# schemas.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=1)
    ticker: str = Field(..., min_length=1, max_length=10)
    sector: str  # "Bank", "Pharma", "Textile", "General"
    sub_sector: Optional[str] = None

class CompanyResponse(BaseModel):
    id: str
    name: str
    ticker: str
    sector: str
    sub_sector: Optional[str]
    is_active: bool

class FinancialDataCreate(BaseModel):
    company_id: str
    report_type: str  # "annual" or "quarterly"
    year: int
    quarter: Optional[int] = None
    
    # Balance Sheet
    total_assets: float = 0
    total_liabilities: float = 0
    shareholders_equity: float = 0
    total_debt: float = 0
    cash_and_equivalents: float = 0
    current_assets: float = 0
    current_liabilities: float = 0
    
    # Income Statement
    revenue: float = 0
    operating_income: float = 0
    ebit: float = 0
    ebitda: float = 0
    interest_expense: float = 0
    net_income: float = 0
    gross_profit: float = 0
    
    # Cash Flow
    operating_cash_flow: float = 0
    capex: float = 0
    free_cash_flow: float = 0
    
    # Per Share
    eps: float = 0
    dps: float = 0
    shares_outstanding: float = 0
    current_price: float = 0
    
    # Bank Specific
    total_deposits: Optional[float] = None
    total_loans: Optional[float] = None
    npl_ratio: Optional[float] = None
    car_ratio: Optional[float] = None
    net_interest_income: Optional[float] = None

class AnalysisResponse(BaseModel):
    company_name: str
    ticker: str
    sector: str
    report_type: str
    year: int
    quarter: Optional[int]
    overall_score: float
    overall_color: str
    overall_color_name: str
    metrics: list
    ratios: dict
