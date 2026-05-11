from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from bson import ObjectId
from datetime import datetime
from typing import Optional
import json
import os

from database import db, init_db
from schemas import CompanyCreate, FinancialDataCreate
from analysis_engine import AnalysisEngine

app = FastAPI(title="Financial Health Analyzer")

# Static files & templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.cache = None

# Analysis Engine instance
engine = AnalysisEngine()

# ---------------------- Startup ----------------------
@app.on_event("startup")
async def startup():
    await init_db()
    print("✅ Database connected & indexes created!")

# ---------------------- Pages ----------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Landing page - Company list"""
    companies = await db.companies.find({"is_active": True}).to_list(100)
    for c in companies:
        c["_id"] = str(c["_id"])
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "companies": companies,
    })

@app.get("/add-company", response_class=HTMLResponse)
async def add_company_page(request: Request):
    """Form to add new company"""
    return templates.TemplateResponse("add_company.html", {"request": request})

@app.get("/input-data/{company_id}", response_class=HTMLResponse)
async def input_data_page(request: Request, company_id: str):
    """Form to input financial data"""
    try:
        company = await db.companies.find_one({"_id": ObjectId(company_id)})
    except:
        raise HTTPException(400, "Invalid company ID")
    
    if not company:
        raise HTTPException(404, "Company not found")
    company["_id"] = str(company["_id"])
    return templates.TemplateResponse("input_form.html", {
        "request": request,
        "company": company,
    })

@app.get("/analysis/{company_id}", response_class=HTMLResponse)
async def view_analysis(request: Request, company_id: str):
    """View analysis results"""
    try:
        company = await db.companies.find_one({"_id": ObjectId(company_id)})
    except:
        raise HTTPException(400, "Invalid company ID")
    
    if not company:
        raise HTTPException(404, "Company not found")
    
    # Get latest financial data
    financials = await db.financial_data.find(
        {"company_id": ObjectId(company_id)}
    ).sort([("year", -1), ("quarter", -1)]).to_list(10)
    
    analyses = []
    for fin in financials:
        fin["_id"] = str(fin["_id"])
        fin["company_id"] = str(fin["company_id"])
        # Check if analysis exists
        analysis = await db.analysis_results.find_one({"financial_data_id": fin["_id"]})
        if analysis:
            analysis["_id"] = str(analysis["_id"])
            analyses.append({
                "financial": fin,
                "analysis": analysis,
            })
    
    company["_id"] = str(company["_id"])
    return templates.TemplateResponse("analysis_result.html", {
        "request": request,
        "company": company,
        "analyses": analyses,
    })

@app.get("/result/{financial_id}", response_class=HTMLResponse)
async def view_result(request: Request, financial_id: str):
    """View single analysis result"""
    analysis = await db.analysis_results.find_one({"financial_data_id": financial_id})
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    analysis["_id"] = str(analysis["_id"])
    return templates.TemplateResponse("result.html", {
        "request": request,
        "analysis": analysis,
    })

# ---------------------- API Endpoints ----------------------
@app.post("/api/companies")
async def create_company(company: CompanyCreate):
    """Create a new company"""
    existing = await db.companies.find_one({"ticker": company.ticker.upper()})
    if existing:
        raise HTTPException(400, "Company with this ticker already exists")
    
    doc = {
        "name": company.name,
        "ticker": company.ticker.upper(),
        "sector": company.sector,
        "sub_sector": company.sub_sector,
        "is_active": True,
        "created_at": datetime.utcnow(),
    }
    result = await db.companies.insert_one(doc)
    return {"id": str(result.inserted_id), "message": "Company created successfully"}

@app.get("/api/companies")
async def list_companies():
    """List all active companies"""
    companies = await db.companies.find({"is_active": True}).to_list(100)
    for c in companies:
        c["_id"] = str(c["_id"])
    return companies

@app.post("/api/financial-data")
async def create_financial_data(data: FinancialDataCreate):
    """Input financial data and run analysis"""
    # Verify company exists
    try:
        company_oid = ObjectId(data.company_id)
    except:
        raise HTTPException(400, "Invalid company ID format")
    
    company = await db.companies.find_one({"_id": company_oid})
    if not company:
        raise HTTPException(404, "Company not found")
    
    # Convert to dict and fix ObjectId
    doc = data.model_dump()
    doc["company_id"] = company_oid
    doc["created_at"] = datetime.utcnow()
    
    # Save financial data
    result = await db.financial_data.insert_one(doc)
    financial_id = str(result.inserted_id)
    
    # Run analysis
    ratios = engine.calculate_ratios(doc)
    health_analysis = engine.calculate_health_score(ratios, company.get("sector", "General"))
    
    # Save analysis result
    analysis_doc = {
        "company_id": company_oid,
        "financial_data_id": financial_id,
        "company_name": company["name"],
        "ticker": company["ticker"],
        "sector": company["sector"],
        "report_type": data.report_type,
        "year": data.year,
        "quarter": data.quarter,
        "overall_score": health_analysis["overall_score"],
        "overall_color": health_analysis["overall_color"],
        "overall_color_name": health_analysis["overall_color_name"],
        "metrics": health_analysis["metrics"],
        "ratios": health_analysis["ratios"],
        "created_at": datetime.utcnow(),
    }
    await db.analysis_results.insert_one(analysis_doc)
    
    return {
        "financial_id": financial_id,
        "analysis": health_analysis,
    }

@app.get("/api/analysis/{financial_data_id}")
async def get_analysis(financial_data_id: str):
    """Get analysis for specific financial data"""
    analysis = await db.analysis_results.find_one({"financial_data_id": financial_data_id})
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    analysis["_id"] = str(analysis["_id"])
    return analysis

@app.get("/api/compare/{sector}")
async def compare_companies(sector: str):
    """Compare all companies in a sector"""
    companies = await db.companies.find({"sector": sector, "is_active": True}).to_list(50)
    
    comparison = []
    for company in companies:
        # Get latest analysis
        analysis = await db.analysis_results.find_one(
            {"company_id": company["_id"]}
        ).sort("created_at", -1)
        
        if analysis:
            comparison.append({
                "company_name": company["name"],
                "ticker": company["ticker"],
                "overall_score": analysis["overall_score"],
                "overall_color": analysis["overall_color"],
            })
    
    return sorted(comparison, key=lambda x: x["overall_score"], reverse=True)

# ---------------------- Run Config ----------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
