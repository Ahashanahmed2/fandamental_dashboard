# schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List

class DCFInputs(BaseModel):
    """DCF ভ্যালুয়েশনের জন্য প্রয়োজনীয় ইনপুট"""
    # প্রজেকশন সেটিংস
    projection_years: int = Field(default=5, ge=3, le=10)  # ৩-১০ বছর
    revenue_growth_rates: List[float] = Field(default_factory=lambda: [0.08, 0.07, 0.06, 0.05, 0.04])
    
    # ডিসকাউন্ট রেট
    wacc: float = Field(default=0.15, ge=0.05, le=0.30)  # 5%-30%
    
    # টার্মিনাল ভ্যালু
    terminal_growth_rate: float = Field(default=0.03, ge=0.0, le=0.06)  # 0%-6%
    
    # অ্যাডভান্সড (ঐচ্ছিক)
    tax_rate: float = Field(default=0.25)  # কর্পোরেট ট্যাক্স
    risk_free_rate: Optional[float] = None  # CAPM-এর জন্য
    market_risk_premium: Optional[float] = None
    beta: Optional[float] = None
    
    # মার্জিন অফ সেফটি
    margin_of_safety: float = Field(default=0.20, ge=0.0, le=0.50)  # 0%-50%

class FinancialDataCreate(BaseModel):
    # ... আপনার এক্সিস্টিং ফিল্ডস ...
    
    # DCF সেকশন (নতুন)
    dcf_inputs: Optional[DCFInputs] = None
    
    # ডিভিডেন্ড ডিসকাউন্ট মডেলের জন্য (ঐচ্ছিক)
    dividend_growth_rate: Optional[float] = None