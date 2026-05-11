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
    
    # Build HTML directly (no Jinja2)
    html = """<!DOCTYPE html>
<html>
<head>
    <title>Financial Analyzer</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body style="background:#0f172a;color:white;padding:40px;font-family:Arial;">
    <div style="max-width:800px;margin:0 auto;">
        <h1>📊 Financial Analyzer</h1>
        <a href="/add-company" style="background:#3b82f6;color:white;padding:10px 24px;border-radius:8px;text-decoration:none;display:inline-block;margin-bottom:20px;">+ Add Company</a>
"""
    
    if companies:
        for c in companies:
            html += f"""
        <div style="background:#1e293b;padding:16px;border-radius:10px;margin-bottom:12px;">
            <strong>{c['name']}</strong> ({c['ticker']}) | {c.get('sector','')}
            <div style="margin-top:8px;">
                <a href="/input-data/{c['_id']}" style="color:#10b981;margin-right:12px;">📝 Input Data</a>
                <a href="/analysis/{c['_id']}" style="color:#06b6d4;">📊 View Analysis</a>
            </div>
        </div>"""
    else:
        html += '<p style="margin-top:30px;color:#94a3b8;">No companies added yet. Click "Add Company" to get started.</p>'
    
    html += """
    </div>
</body>
</html>"""
    
    return HTMLResponse(content=html)

@app.get("/add-company", response_class=HTMLResponse)
async def add_company_page(request: Request):
    """Form to add new company"""
    html = """<!DOCTYPE html>
<html>
<head>
    <title>Add Company</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body style="background:#0f172a;color:white;padding:40px;font-family:Arial;">
    <div style="max-width:500px;margin:60px auto;background:#1e293b;padding:30px;border-radius:15px;">
        <h3>➕ Add New Company</h3>
        <form id="f">
            <input id="n" class="form-control mb-2" placeholder="Company Name" required style="background:#334155;color:white;border:1px solid #475569;">
            <input id="t" class="form-control mb-2" placeholder="Ticker" required style="background:#334155;color:white;border:1px solid #475569;">
            <select id="s" class="form-control mb-3" style="background:#334155;color:white;border:1px solid #475569;">
                <option value="Bank">🏦 Bank</option>
                <option value="Pharmaceuticals">💊 Pharma</option>
                <option value="Telecom">📱 Telecom</option>
                <option value="General">📦 General</option>
            </select>
            <button type="submit" class="btn btn-primary w-100">💾 Save Company</button>
        </form>
        <a href="/" style="color:#94a3b8;display:block;margin-top:12px;text-align:center;">⬅ Back</a>
    </div>
    <script>
        document.getElementById('f').addEventListener('submit',async e=>{
            e.preventDefault();
            let r=await fetch('/api/companies',{
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                    name:document.getElementById('n').value,
                    ticker:document.getElementById('t').value,
                    sector:document.getElementById('s').value
                })
            });
            if(r.ok)window.location.href='/';
            else alert('Error');
        });
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)
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
