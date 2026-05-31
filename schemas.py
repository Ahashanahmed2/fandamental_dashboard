# schemas.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import re

# ==================== Company Schemas ====================

class CompanyCreate(BaseModel):
    """কোম্পানি তৈরি/আপডেট করার জন্য স্কিমা"""
    name: str = Field(..., min_length=1, max_length=200, description="কোম্পানির পূর্ণ নাম")
    ticker: str = Field(..., min_length=1, max_length=20, description="স্টক টিকার সিম্বল (UPPERCASE)")
    sector: str = Field(..., description="কোম্পানির সেক্টর")
    sub_sector: Optional[str] = Field(None, max_length=200, description="সাব-সেক্টর (ঐচ্ছিক)")

    @field_validator('ticker')
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        """টিকার ভ্যালিডেশন - শুধু অক্ষর, সংখ্যা ও হাইফেন অনুমোদিত"""
        if not re.match(r'^[A-Za-z0-9\-\.]+$', v):
            raise ValueError('Ticker can only contain letters, numbers, hyphens and dots')
        return v.upper().strip()

    @field_validator('sector')
    @classmethod
    def validate_sector(cls, v: str) -> str:
        """সেক্টর ভ্যালিডেশন"""
        valid_sectors = [
            "Bank", "Pharmaceuticals", "Textile", "Telecom", 
            "Food", "Energy", "Cement", "General", "IT", 
            "Insurance", "NBFI", "Engineering", "Ceramic",
            "Tannery", "Paper", "Jute", "Services", "Miscellaneous"
        ]
        if v not in valid_sectors:
            # কাস্টম সেক্টর অনুমোদিত কিন্তু ওয়ার্নিং দেওয়া যেতে পারে
            pass
        return v

class CompanyResponse(BaseModel):
    """কোম্পানি রেসপন্স স্কিমা"""
    id: str = Field(alias="_id")
    name: str
    ticker: str
    sector: str
    sub_sector: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

class CompanyUpdate(BaseModel):
    """কোম্পানি আপডেট করার জন্য স্কিমা"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    ticker: Optional[str] = Field(None, min_length=1, max_length=20)
    sector: Optional[str] = None
    sub_sector: Optional[str] = Field(None, max_length=200)

# ==================== DCF Schemas ====================

class DCFInputs(BaseModel):
    """DCF ভ্যালুয়েশনের জন্য প্রয়োজনীয় ইনপুট"""
    projection_years: int = Field(default=5, ge=3, le=10, description="প্রজেকশন ইয়ার (৩-১০ বছর)")
    growth_rates: List[float] = Field(
        default_factory=lambda: [0.08, 0.07, 0.06, 0.05, 0.04],
        description="বার্ষিক গ্রোথ রেট (ডেসিমালে, যেমন ০.০৮ = ৮%)"
    )
    wacc: float = Field(default=0.15, ge=0.05, le=0.30, description="Weighted Average Cost of Capital (৫-৩০%)")
    terminal_growth: float = Field(default=0.03, ge=0.0, le=0.06, description="টার্মিনাল গ্রোথ রেট (০-৬%)")
    margin_of_safety: float = Field(default=0.20, ge=0.0, le=0.50, description="মার্জিন অফ সেফটি (০-৫০%)")
    tax_rate: float = Field(default=0.25, ge=0.0, le=0.50, description="ট্যাক্স রেট (০-৫০%)")

    # CAPM Advanced (Optional)
    risk_free_rate: Optional[float] = Field(None, ge=0.0, le=0.20, description="রিস্ক-ফ্রি রেট")
    market_risk_premium: Optional[float] = Field(None, ge=0.0, le=0.20, description="মার্কেট রিস্ক প্রিমিয়াম")
    beta: Optional[float] = Field(None, ge=0.0, le=3.0, description="বিটা (স্টক ভোলাটিলিটি)")

    @field_validator('growth_rates')
    @classmethod
    def validate_growth_rates(cls, v: List[float], info) -> List[float]:
        """গ্রোথ রেট ভ্যালিডেশন"""
        projection_years = info.data.get('projection_years', 5)
        if len(v) < projection_years:
            # শেষ গ্রোথ রেট দিয়ে পূর্ণ করা
            last_rate = v[-1] if v else 0.03
            v.extend([last_rate] * (projection_years - len(v)))
        # প্রথম projection_years সংখ্যক রেট নেওয়া
        return v[:projection_years]

    @field_validator('wacc')
    @classmethod
    def calculate_wacc_from_capm(cls, v: float, info) -> float:
        """CAPM থেকে WACC ক্যালকুলেট (যদি সব প্যারামিটার দেওয়া থাকে)"""
        risk_free = info.data.get('risk_free_rate')
        market_premium = info.data.get('market_risk_premium')
        beta = info.data.get('beta')
        
        if all(x is not None for x in [risk_free, market_premium, beta]):
            capm_wacc = risk_free + (beta * market_premium)
            # CAPM থেকে আসা WACC ব্যবহার (যদি ম্যানুয়াল WACC ডিফল্ট থাকে)
            if v == 0.15:  # ডিফল্ট WACC
                return round(capm_wacc, 4)
        return v

class DCFResult(BaseModel):
    """DCF ভ্যালুয়েশন রেজাল্ট স্কিমা"""
    inputs: Dict[str, Any]
    enterprise_value: float
    equity_value: float
    intrinsic_value_per_share: float
    mos_adjusted_value: float
    current_price: float
    upside_percent: Optional[float] = None
    signal: str  # BUY, HOLD, SELL
    signal_color: str
    fcf_projections: List[float]
    pv_fcf_sum: float
    pv_terminal: float
    terminal_value: float
    net_debt: float
    calculation_note: str

# ==================== Financial Data Schemas ====================

class FinancialDataCreate(BaseModel):
    """ফিন্যান্সিয়াল ডেটা ইনপুট + DCF প্যারামিটার্স"""

    # 📅 Core Report Info
    company_id: str = Field(..., description="কোম্পানির MongoDB ObjectId")
    report_type: str = Field(..., pattern="^(annual|quarterly)$", description="রিপোর্ট টাইপ: annual/quarterly")
    year: int = Field(..., ge=2000, le=2100, description="রিপোর্ট ইয়ার (২০০০-২১০০)")
    quarter: Optional[int] = Field(None, ge=1, le=4, description="কোয়ার্টার (১-৪, শুধু quarterly এর জন্য)")

    @field_validator('quarter')
    @classmethod
    def validate_quarter(cls, v: Optional[int], info) -> Optional[int]:
        """কোয়ার্টার ভ্যালিডেশন"""
        report_type = info.data.get('report_type')
        if report_type == 'quarterly' and v is None:
            raise ValueError('Quarter is required for quarterly reports')
        if report_type == 'annual' and v is not None:
            return None  # Annual এর জন্য quarter null
        return v

    # 📋 Balance Sheet (All values in millions/lakhs as per input)
    total_assets: float = Field(default=0.0, ge=0, description="মোট সম্পদ")
    total_liabilities: float = Field(default=0.0, ge=0, description="মোট দায়")
    shareholders_equity: float = Field(default=0.0, description="শেয়ারহোল্ডার ইকুইটি")
    total_debt: float = Field(default=0.0, ge=0, description="মোট ঋণ")
    cash_and_equivalents: float = Field(default=0.0, ge=0, description="নগদ ও নগদ সমতুল্য")
    current_assets: float = Field(default=0.0, ge=0, description="চলতি সম্পদ")
    current_liabilities: float = Field(default=0.0, ge=0, description="চলতি দায়")

    # 📈 Income Statement
    revenue: float = Field(default=0.0, ge=0, description="রাজস্ব/বিক্রয়")
    gross_profit: float = Field(default=0.0, description="গ্রস প্রফিট")
    operating_income: float = Field(default=0.0, description="অপারেটিং ইনকাম")
    ebit: float = Field(default=0.0, description="Earnings Before Interest & Tax")
    ebitda: float = Field(default=0.0, description="Earnings Before Interest, Tax, Depreciation & Amortization")
    interest_expense: float = Field(default=0.0, ge=0, description="সুদ ব্যয়")
    net_income: float = Field(default=0.0, description="নিট ইনকাম/লাভ")

    # 💵 Cash Flow
    operating_cash_flow: float = Field(default=0.0, description="অপারেটিং ক্যাশ ফ্লো")
    capex: float = Field(default=0.0, ge=0, description="ক্যাপিটাল এক্সপেন্ডিচার")
    free_cash_flow: float = Field(default=0.0, description="ফ্রি ক্যাশ ফ্লো")
    fcf_margin: Optional[float] = Field(None, ge=0, le=1, description="FCF মার্জিন (০-১)")

    # 📊 Per Share Data
    eps: float = Field(default=0.0, description="Earnings Per Share")
    dps: float = Field(default=0.0, ge=0, description="Dividend Per Share")
    shares_outstanding: float = Field(default=1.0, gt=0, description="শেয়ার সংখ্যা (মিলিয়নে)")
    current_price: float = Field(default=0.0, ge=0, description="বর্তমান শেয়ার প্রাইস")

    # 🏦 Bank Specific (Optional)
    total_deposits: Optional[float] = Field(None, ge=0, description="মোট ডিপোজিট (ব্যাংকের জন্য)")
    total_loans: Optional[float] = Field(None, ge=0, description="মোট লোন (ব্যাংকের জন্য)")
    net_interest_income: Optional[float] = Field(None, description="নিট ইন্টারেস্ট ইনকাম (ব্যাংকের জন্য)")
    npl_ratio: Optional[float] = Field(None, ge=0, le=100, description="NPL রেশিও % (ব্যাংকের জন্য)")
    car_ratio: Optional[float] = Field(None, ge=0, le=100, description="CAR রেশিও % (ব্যাংকের জন্য)")

    # 📊 DCF & Dividend (Optional)
    dcf_params: Optional[DCFInputs] = Field(None, description="DCF প্যারামিটার্স (ঐচ্ছিক)")
    dividend_growth_rate: Optional[float] = Field(None, ge=0, le=1, description="ডিভিডেন্ড গ্রোথ রেট")

    @field_validator('free_cash_flow')
    @classmethod
    def calculate_fcf_if_missing(cls, v: float, info) -> float:
        """FCF অটো-ক্যালকুলেট যদি না দেওয়া থাকে"""
        if v == 0.0:
            ocf = info.data.get('operating_cash_flow', 0)
            capex = info.data.get('capex', 0)
            if ocf > 0:
                return max(0, ocf - capex)
        return v

    @field_validator('shares_outstanding')
    @classmethod
    def validate_shares_outstanding(cls, v: float) -> float:
        """শেয়ার সংখ্যা কমপক্ষে ১ মিলিয়ন হতে হবে"""
        if v < 0.001:  # খুব ছোট সংখ্যা এড়ানো
            raise ValueError('Shares outstanding must be at least 0.001 million (1000 shares)')
        return v

class FinancialDataResponse(BaseModel):
    """ফিন্যান্সিয়াল ডেটা রেসপন্স স্কিমা"""
    id: str = Field(alias="_id")
    company_id: str
    report_type: str
    year: int
    quarter: Optional[int] = None
    total_assets: float
    total_liabilities: float
    shareholders_equity: float
    revenue: float
    net_income: float
    free_cash_flow: float
    eps: float
    current_price: float
    dcf_params: Optional[DCFInputs] = None
    created_at: datetime

    class Config:
        populate_by_name = True

# ==================== Analysis Result Schemas ====================

class MetricDetail(BaseModel):
    """ইন্ডিভিজুয়াল মেট্রিক ডিটেইল"""
    metric: str
    value: str
    score: float
    color: str
    color_name: str
    weight: Optional[float] = None
    benchmark: Optional[str] = None

class RatioDetail(BaseModel):
    """ফিন্যান্সিয়াল রেশিও ডিটেইল"""
    name: str
    value: float
    interpretation: Optional[str] = None

class AnalysisResultResponse(BaseModel):
    """অ্যানালাইসিস রেজাল্ট রেসপন্স স্কিমা"""
    id: str = Field(alias="_id")
    company_id: str
    financial_data_id: str
    company_name: str
    ticker: str
    sector: str
    report_type: str
    year: int
    quarter: Optional[int] = None
    overall_score: float
    overall_color: str
    overall_color_name: str
    metrics: List[MetricDetail]
    ratios: Dict[str, Any]
    dcf_valuation: Optional[DCFResult] = None
    created_at: datetime

    class Config:
        populate_by_name = True

# ==================== Comparison Schemas ====================

class SectorComparison(BaseModel):
    """সেক্টর কম্প্যারিজন স্কিমা"""
    company_name: str
    ticker: str
    overall_score: float
    overall_color: str
    dcf_signal: Optional[str] = None
    dcf_upside: Optional[float] = None

class SectorSummary(BaseModel):
    """সেক্টর সামারি স্কিমা"""
    sector: str
    total_companies: int
    average_score: float
    companies: List[SectorComparison]
    highest_scored: Optional[SectorComparison] = None
    lowest_scored: Optional[SectorComparison] = None

# ==================== Dividend Discount Model Schemas ====================

class DDMInputs(BaseModel):
    """Dividend Discount Model ইনপুট"""
    current_dividend: float = Field(..., ge=0, description="বর্তমান ডিভিডেন্ড পার শেয়ার")
    growth_rate: float = Field(..., ge=0, le=1, description="ডিভিডেন্ড গ্রোথ রেট")
    required_return: float = Field(default=0.15, ge=0.05, le=0.50, description="রিকোয়ার্ড রেট অফ রিটার্ন")
    growth_period: int = Field(default=10, ge=1, le=50, description="গ্রোথ পিরিয়ড (বছর)")
    terminal_growth: float = Field(default=0.03, ge=0, le=0.06, description="টার্মিনাল গ্রোথ রেট")

class DDMResult(BaseModel):
    """DDM ক্যালকুলেশন রেজাল্ট"""
    intrinsic_value: float
    current_price: float
    upside_percent: float
    signal: str
    present_value_dividends: float
    terminal_value: float
    calculation_details: Dict[str, Any]

# ==================== Advanced Validation Models ====================

class FinancialHealthScore(BaseModel):
    """কম্প্রিহেনসিভ ফিন্যান্সিয়াল হেলথ স্কোর"""
    # Profitability (20% weight)
    profitability_score: float = Field(..., ge=0, le=100)
    roe: Optional[float] = None
    roa: Optional[float] = None
    net_margin: Optional[float] = None
    
    # Efficiency (15% weight)
    efficiency_score: float = Field(..., ge=0, le=100)
    asset_turnover: Optional[float] = None
    inventory_turnover: Optional[float] = None
    
    # Liquidity (15% weight)
    liquidity_score: float = Field(..., ge=0, le=100)
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    
    # Solvency (20% weight)
    solvency_score: float = Field(..., ge=0, le=100)
    debt_to_equity: Optional[float] = None
    interest_coverage: Optional[float] = None
    
    # Valuation (15% weight)
    valuation_score: float = Field(..., ge=0, le=100)
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    peg_ratio: Optional[float] = None
    
    # Growth (15% weight)
    growth_score: float = Field(..., ge=0, le=100)
    revenue_growth: Optional[float] = None
    profit_growth: Optional[float] = None
    
    # Overall
    overall_score: float = Field(..., ge=0, le=100)
    overall_grade: str  # A+, A, A-, B+, B, B-, C+, C, C-, D, F

class HistoricalDataPoint(BaseModel):
    """হিস্টোরিকাল ফিন্যান্সিয়াল ডেটা পয়েন্ট"""
    year: int
    quarter: Optional[int] = None
    revenue: float
    net_income: float
    eps: float
    free_cash_flow: float
    total_assets: float
    shareholders_equity: float
    debt_to_equity: float
    roe: float
    current_ratio: float

class HistoricalAnalysis(BaseModel):
    """হিস্টোরিকাল ট্রেন্ড অ্যানালাইসিস"""
    company_id: str
    ticker: str
    data_points: List[HistoricalDataPoint]
    trend_analysis: Dict[str, Any]  # CAGR, volatility, etc.
    last_updated: datetime

# ==================== Export Schemas ====================

class ExportRequest(BaseModel):
    """ডেটা এক্সপোর্ট রিকোয়েস্ট"""
    company_id: str
    format: str = Field(default="json", pattern="^(json|csv|pdf)$")
    include_dcf: bool = True
    include_historical: bool = False
    date_range: Optional[Dict[str, str]] = None  # {"start": "2020-01-01", "end": "2024-12-31"}

# ==================== Utility Classes ====================

class PaginationParams(BaseModel):
    """পেজিনেশন প্যারামিটার্স"""
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)
    sort_by: Optional[str] = None
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")

class APIResponse(BaseModel):
    """স্ট্যান্ডার্ড API রেসপন্স র‍্যাপার"""
    success: bool = True
    message: str = "Operation successful"
    data: Optional[Any] = None
    errors: Optional[List[str]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ErrorResponse(BaseModel):
    """এরর রেসপন্স স্কিমা"""
    success: bool = False
    message: str
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)