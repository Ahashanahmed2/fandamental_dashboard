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
            <input id="t" class="form-control mb-2" placeholder="Ticker (e.g., CITYBANK)" required style="background:#334155;color:white;border:1px solid #475569;">
            <select id="s" class="form-control mb-3" style="background:#334155;color:white;border:1px solid #475569;">
                <option value="Bank">🏦 Bank</option>
                <option value="Pharmaceuticals">💊 Pharmaceuticals</option>
                <option value="Textile">👕 Textile</option>
                <option value="Telecom">📱 Telecom</option>
                <option value="Food">🍔 Food & Beverage</option>
                <option value="Energy">⚡ Energy</option>
                <option value="Cement">🏗️ Cement</option>
                <option value="General">📦 General</option>
            </select>
            <input id="sub" class="form-control mb-3" placeholder="Sub Sector (Optional)" style="background:#334155;color:white;border:1px solid #475569;">
            <button type="submit" class="btn btn-primary w-100">💾 Save Company</button>
        </form>
        <a href="/" style="color:#94a3b8;display:block;margin-top:12px;text-align:center;">⬅ Back to Dashboard</a>
    </div>
    <script>
        document.getElementById('f').addEventListener('submit',async e=>{
            e.preventDefault();
            let r=await fetch('/api/companies',{
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({
                    name:document.getElementById('n').value,
                    ticker:document.getElementById('t').value.toUpperCase(),
                    sector:document.getElementById('s').value,
                    sub_sector:document.getElementById('sub').value||null
                })
            });
            if(r.ok){window.location.href='/';}
            else{let err=await r.json();alert('Error: '+(err.detail||'Failed'));}
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
    
    company_id_str = str(company["_id"])
    company_name = company["name"]
    company_ticker = company["ticker"]
    company_sector = company["sector"]
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Input Data - {company_name}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background: #f5f6fa; padding: 20px; font-family: Arial; }}
        .form-section {{ background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .section-title {{ background: #2c3e50; color: white; padding: 10px 15px; border-radius: 5px; margin-bottom: 20px; }}
        .bank-fields {{ display: none; }}
        .btn-submit {{ background: #27ae60; color: white; font-weight: bold; padding: 12px 40px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; }}
        .btn-submit:hover {{ background: #219a52; }}
        label {{ font-weight: 600; margin-top: 8px; }}
        input, select {{ margin-bottom: 6px; }}
    </style>
</head>
<body>
    <div class="container">
        <h2 class="mb-4">📊 Financial Data Input - {company_name} ({company_ticker})</h2>
        <span class="badge bg-info mb-3">{company_sector} Sector</span>
        <a href="/" class="btn btn-sm btn-secondary float-end">⬅ Back to Dashboard</a>

        <form id="financialForm">
            <input type="hidden" id="companyId" value="{company_id_str}">
            
            <div class="form-section">
                <h5 class="section-title">📅 Report Information</h5>
                <div class="row">
                    <div class="col-md-3">
                        <label>Report Type *</label>
                        <select class="form-control" id="reportType" required>
                            <option value="annual">Annual</option>
                            <option value="quarterly">Quarterly</option>
                        </select>
                    </div>
                    <div class="col-md-3">
                        <label>Year *</label>
                        <input type="number" class="form-control" id="year" placeholder="2024" required>
                    </div>
                    <div class="col-md-3" id="quarterDiv" style="display:none;">
                        <label>Quarter</label>
                        <select class="form-control" id="quarter">
                            <option value="1">Q1</option>
                            <option value="2">Q2</option>
                            <option value="3">Q3</option>
                            <option value="4">Q4</option>
                        </select>
                    </div>
                </div>
            </div>

            <div class="form-section">
                <h5 class="section-title">📋 Balance Sheet</h5>
                <div class="row">
                    <div class="col-md-4"><label>Total Assets</label><input type="number" step="0.01" class="form-control" id="totalAssets" placeholder="0.00"></div>
                    <div class="col-md-4"><label>Total Liabilities</label><input type="number" step="0.01" class="form-control" id="totalLiabilities" placeholder="0.00"></div>
                    <div class="col-md-4"><label>Shareholders' Equity</label><input type="number" step="0.01" class="form-control" id="shareholdersEquity" placeholder="0.00"></div>
                </div>
                <div class="row mt-3">
                    <div class="col-md-4"><label>Total Debt</label><input type="number" step="0.01" class="form-control" id="totalDebt" placeholder="0.00"></div>
                    <div class="col-md-4"><label>Cash & Equivalents</label><input type="number" step="0.01" class="form-control" id="cash" placeholder="0.00"></div>
                    <div class="col-md-4"><label>Current Assets</label><input type="number" step="0.01" class="form-control" id="currentAssets" placeholder="0.00"></div>
                </div>
                <div class="row mt-3">
                    <div class="col-md-4"><label>Current Liabilities</label><input type="number" step="0.01" class="form-control" id="currentLiabilities" placeholder="0.00"></div>
                </div>
            </div>

            <div class="form-section">
                <h5 class="section-title">📈 Income Statement</h5>
                <div class="row">
                    <div class="col-md-4"><label>Revenue</label><input type="number" step="0.01" class="form-control" id="revenue" placeholder="0.00"></div>
                    <div class="col-md-4"><label>Gross Profit</label><input type="number" step="0.01" class="form-control" id="grossProfit" placeholder="0.00"></div>
                    <div class="col-md-4"><label>Operating Income</label><input type="number" step="0.01" class="form-control" id="operatingIncome" placeholder="0.00"></div>
                </div>
                <div class="row mt-3">
                    <div class="col-md-3"><label>EBIT</label><input type="number" step="0.01" class="form-control" id="ebit" placeholder="0.00"></div>
                    <div class="col-md-3"><label>EBITDA</label><input type="number" step="0.01" class="form-control" id="ebitda" placeholder="0.00"></div>
                    <div class="col-md-3"><label>Interest Expense</label><input type="number" step="0.01" class="form-control" id="interestExpense" placeholder="0.00"></div>
                    <div class="col-md-3"><label>Net Income</label><input type="number" step="0.01" class="form-control" id="netIncome" placeholder="0.00"></div>
                </div>
            </div>

            <div class="form-section">
                <h5 class="section-title">💵 Cash Flow</h5>
                <div class="row">
                    <div class="col-md-4"><label>Operating Cash Flow</label><input type="number" step="0.01" class="form-control" id="ocf" placeholder="0.00"></div>
                    <div class="col-md-4"><label>CAPEX</label><input type="number" step="0.01" class="form-control" id="capex" placeholder="0.00"></div>
                    <div class="col-md-4"><label>Free Cash Flow</label><input type="number" step="0.01" class="form-control" id="fcf" placeholder="0.00"></div>
                </div>
            </div>

            <div class="form-section">
                <h5 class="section-title">📊 Per Share Data</h5>
                <div class="row">
                    <div class="col-md-3"><label>EPS</label><input type="number" step="0.01" class="form-control" id="eps" placeholder="0.00"></div>
                    <div class="col-md-3"><label>DPS</label><input type="number" step="0.01" class="form-control" id="dps" placeholder="0.00"></div>
                    <div class="col-md-3"><label>Shares Outstanding (M)</label><input type="number" step="0.01" class="form-control" id="sharesOut" placeholder="0.00"></div>
                    <div class="col-md-3"><label>Current Stock Price</label><input type="number" step="0.01" class="form-control" id="currentPrice" placeholder="0.00"></div>
                </div>
            </div>

            <div class="form-section bank-fields" id="bankFields">
                <h5 class="section-title">🏦 Bank Specific</h5>
                <div class="row">
                    <div class="col-md-4"><label>Total Deposits</label><input type="number" step="0.01" class="form-control" id="totalDeposits" placeholder="0.00"></div>
                    <div class="col-md-4"><label>Total Loans</label><input type="number" step="0.01" class="form-control" id="totalLoans" placeholder="0.00"></div>
                    <div class="col-md-4"><label>Net Interest Income</label><input type="number" step="0.01" class="form-control" id="nii" placeholder="0.00"></div>
                </div>
                <div class="row mt-3">
                    <div class="col-md-4"><label>NPL Ratio (%)</label><input type="number" step="0.01" class="form-control" id="nplRatio" placeholder="0.00"></div>
                    <div class="col-md-4"><label>CAR (%)</label><input type="number" step="0.01" class="form-control" id="carRatio" placeholder="0.00"></div>
                </div>
            </div>

            <button type="submit" class="btn-submit btn-lg mt-3">📊 Analyze & Save</button>
        </form>
    </div>

    <script>
        document.getElementById('reportType').addEventListener('change', function() {{
            document.getElementById('quarterDiv').style.display = this.value === 'quarterly' ? 'block' : 'none';
        }});
        
        var sector = "{company_sector}";
        if (sector === "Bank") {{
            document.getElementById('bankFields').style.display = 'block';
        }}

        document.getElementById('financialForm').addEventListener('submit', async function(e) {{
            e.preventDefault();
            var btn = this.querySelector('button[type="submit"]');
            btn.disabled = true;
            btn.innerHTML = '⏳ Analyzing...';
            
            var data = {{
                company_id: document.getElementById('companyId').value,
                report_type: document.getElementById('reportType').value,
                year: parseInt(document.getElementById('year').value),
                quarter: document.getElementById('reportType').value === 'quarterly' ? parseInt(document.getElementById('quarter').value) : null,
                total_assets: parseFloat(document.getElementById('totalAssets').value) || 0,
                total_liabilities: parseFloat(document.getElementById('totalLiabilities').value) || 0,
                shareholders_equity: parseFloat(document.getElementById('shareholdersEquity').value) || 0,
                total_debt: parseFloat(document.getElementById('totalDebt').value) || 0,
                cash_and_equivalents: parseFloat(document.getElementById('cash').value) || 0,
                current_assets: parseFloat(document.getElementById('currentAssets').value) || 0,
                current_liabilities: parseFloat(document.getElementById('currentLiabilities').value) || 0,
                revenue: parseFloat(document.getElementById('revenue').value) || 0,
                gross_profit: parseFloat(document.getElementById('grossProfit').value) || 0,
                operating_income: parseFloat(document.getElementById('operatingIncome').value) || 0,
                ebit: parseFloat(document.getElementById('ebit').value) || 0,
                ebitda: parseFloat(document.getElementById('ebitda').value) || 0,
                interest_expense: parseFloat(document.getElementById('interestExpense').value) || 0,
                net_income: parseFloat(document.getElementById('netIncome').value) || 0,
                operating_cash_flow: parseFloat(document.getElementById('ocf').value) || 0,
                capex: parseFloat(document.getElementById('capex').value) || 0,
                free_cash_flow: parseFloat(document.getElementById('fcf').value) || 0,
                eps: parseFloat(document.getElementById('eps').value) || 0,
                dps: parseFloat(document.getElementById('dps').value) || 0,
                shares_outstanding: parseFloat(document.getElementById('sharesOut').value) || 0,
                current_price: parseFloat(document.getElementById('currentPrice').value) || 0,
                total_deposits: parseFloat(document.getElementById('totalDeposits')?.value) || null,
                total_loans: parseFloat(document.getElementById('totalLoans')?.value) || null,
                npl_ratio: parseFloat(document.getElementById('nplRatio')?.value) || null,
                car_ratio: parseFloat(document.getElementById('carRatio')?.value) || null,
                net_interest_income: parseFloat(document.getElementById('nii')?.value) || null
            }};
            
            try {{
                var response = await fetch('/api/financial-data', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(data)
                }});
                var result = await response.json();
                if (response.ok) {{
                    window.location.href = '/result/' + result.financial_id;
                }} else {{
                    alert('Error: ' + (result.detail || 'Something went wrong'));
                    btn.disabled = false;
                    btn.innerHTML = '📊 Analyze & Save';
                }}
            }} catch (error) {{
                alert('Error: ' + error.message);
                btn.disabled = false;
                btn.innerHTML = '📊 Analyze & Save';
            }}
        }});
    </script>
</body>
</html>"""
    
    return HTMLResponse(content=html)

@app.get("/analysis/{company_id}", response_class=HTMLResponse)
async def view_analysis(request: Request, company_id: str):
    """View analysis results"""
    try:
        company = await db.companies.find_one({"_id": ObjectId(company_id)})
    except:
        raise HTTPException(400, "Invalid company ID")

    if not company:
        raise HTTPException(404, "Company not found")

    company_id_str = str(company["_id"])
    company_name = company["name"]
    company_ticker = company["ticker"]
    company_sector = company.get("sector", "")

    financials = await db.financial_data.find(
        {"company_id": ObjectId(company_id)}
    ).sort([("year", -1), ("quarter", -1)]).to_list(10)

    analyses_html = ""
    for fin in financials:
        fin_id = str(fin["_id"])
        analysis = await db.analysis_results.find_one({"financial_data_id": fin_id})
        if analysis:
            rtype = fin.get("report_type", "").title()
            year = fin.get("year", "")
            quarter = f" Q{fin.get('quarter')}" if fin.get("quarter") else ""
            score = analysis.get("overall_score", 0)
            color = analysis.get("overall_color", "#fff")
            color_name = analysis.get("overall_color_name", "")
            
            metrics_rows = ""
            for m in analysis.get("metrics", []):
                metrics_rows += f"""<tr>
                    <td>{m.get('metric','')}</td>
                    <td>{m.get('value','')}</td>
                    <td>{m.get('score','')}%</td>
                    <td style="background:{m.get('color','')};color:white;font-weight:bold;">{m.get('color_name','')}</td>
                </tr>"""
            
            analyses_html += f"""
            <div style="background:#1e293b;padding:20px;border-radius:15px;margin-bottom:20px;">
                <h4>{rtype} - {year}{quarter}</h4>
                <div style="text-align:center;margin:25px 0;">
                    <h2 style="color:{color};font-size:3rem;">{score}/100</h2>
                    <h4 style="color:{color};">{color_name}</h4>
                </div>
                <table style="width:100%;border-collapse:collapse;">
                    <thead><tr style="background:#334155;"><th style="padding:12px;text-align:left;">Metric</th><th style="padding:12px;">Value</th><th style="padding:12px;">Score</th><th style="padding:12px;">Status</th></tr></thead>
                    <tbody>{metrics_rows}</tbody>
                </table>
            </div>"""
    
    if not analyses_html:
        analyses_html = '<div style="text-align:center;padding:40px;"><h4>No analysis data found</h4><a href="/input-data/' + company_id_str + '" style="color:#10b981;">📝 Add Financial Data</a></div>'

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Analysis - {company_name}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body style="background:#0f172a;color:white;padding:30px;font-family:Arial;">
    <div style="max-width:900px;margin:0 auto;">
        <div style="background:#1e293b;padding:25px;border-radius:15px;margin-bottom:25px;">
            <h2>{company_name} ({company_ticker})</h2>
            <span style="background:#06b6d4;padding:5px 14px;border-radius:20px;">{company_sector}</span>
            <a href="/input-data/{company_id_str}" style="float:right;background:#10b981;color:white;padding:10px 20px;border-radius:8px;text-decoration:none;">📝 Add New Data</a>
        </div>
        {analyses_html}
        <a href="/" style="display:inline-block;margin-top:20px;color:#94a3b8;">⬅ Back to Dashboard</a>
    </div>
</body>
</html>"""
    
    return HTMLResponse(content=html)

@app.get("/result/{financial_id}", response_class=HTMLResponse)
async def view_result(request: Request, financial_id: str):
    """View single analysis result"""
    analysis = await db.analysis_results.find_one({"financial_data_id": financial_id})
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    
    name = analysis.get("company_name", "")
    ticker = analysis.get("ticker", "")
    sector = analysis.get("sector", "")
    rtype = analysis.get("report_type", "").title()
    year = analysis.get("year", "")
    quarter = f" Q{analysis.get('quarter')}" if analysis.get("quarter") else ""
    score = analysis.get("overall_score", 0)
    color = analysis.get("overall_color", "#fff")
    color_name = analysis.get("overall_color_name", "")
    
    metrics_rows = ""
    for m in analysis.get("metrics", []):
        metrics_rows += f"""<tr>
            <td>{m.get('metric','')}</td>
            <td>{m.get('value','')}</td>
            <td>{m.get('score','')}%</td>
            <td style="background:{m.get('color','')};color:white;font-weight:bold;">{m.get('color_name','')}</td>
        </tr>"""
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Result - {name}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body style="background:#0f172a;color:white;padding:30px;font-family:Arial;">
    <div style="max-width:900px;margin:0 auto;background:#1e293b;padding:30px;border-radius:15px;">
        <h3 style="text-align:center;">{name} ({ticker})</h3>
        <p style="text-align:center;color:#94a3b8;">{rtype} - {year}{quarter}</p>
        <div style="text-align:center;margin:25px 0;">
            <div style="width:150px;height:150px;border-radius:50%;background:{color};display:flex;align-items:center;justify-content:center;margin:0 auto;font-size:2.5rem;font-weight:bold;">{score}</div>
            <h4 style="color:{color};margin-top:12px;">{color_name}</h4>
        </div>
        <table style="width:100%;border-collapse:collapse;">
            <thead><tr style="background:#334155;"><th style="padding:12px;text-align:left;">Metric</th><th style="padding:12px;">Value</th><th style="padding:12px;">Score</th><th style="padding:12px;">Status</th></tr></thead>
            <tbody>{metrics_rows}</tbody>
        </table>
        <a href="/" style="display:inline-block;margin-top:20px;color:#94a3b8;">← Back to Dashboard</a>
    </div>
</body>
</html>"""
    
    return HTMLResponse(content=html)

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
    try:
        company_oid = ObjectId(data.company_id)
    except:
        raise HTTPException(400, "Invalid company ID format")

    company = await db.companies.find_one({"_id": company_oid})
    if not company:
        raise HTTPException(404, "Company not found")

    doc = data.model_dump()
    doc["company_id"] = company_oid
    doc["created_at"] = datetime.utcnow()

    result = await db.financial_data.insert_one(doc)
    financial_id = str(result.inserted_id)

    ratios = engine.calculate_ratios(doc)
    health_analysis = engine.calculate_health_score(ratios, company.get("sector", "General"))

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