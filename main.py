from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from bson import ObjectId
from datetime import datetime
from typing import Optional, List, Dict
import json
import os
import math

from database import db, init_db
from schemas import CompanyCreate, FinancialDataCreate, FinancialDataUpdate
from analysis_engine import AnalysisEngine

app = FastAPI(title="Financial Health Analyzer")

# Static files & templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.cache = None

# Analysis Engine instance
engine = AnalysisEngine()

# ==================== 🆕 DCF VALUATION ENGINE (নতুন অ্যাড করা হয়েছে) ====================
class DCFValuation:
    """Discounted Cash Flow ভ্যালুয়েশন ইঞ্জিন - সরল ও এফিশিয়েন্ট"""

    @staticmethod
    def calculate_terminal_value(final_fcf: float, terminal_growth: float, wacc: float) -> float:
        """Gordon Growth Model: TV = FCFₙ₊₁ / (WACC - g)"""
        if wacc <= terminal_growth:
            terminal_growth = wacc - 0.02
        return (final_fcf * (1 + terminal_growth)) / (wacc - terminal_growth)

    @staticmethod
    def discount_value(future_value: float, wacc: float, year: int) -> float:
        """Present Value ক্যালকুলেশন: PV = FV / (1+r)^n"""
        return future_value / ((1 + wacc) ** year)

    @staticmethod
    def run_dcf(financial_data: Dict, dcf_params: Dict, company_info: Dict) -> Dict:
        """মেইন DCF ক্যালকুলেশন ফাংশন"""

        # ১. বেসিক ডেটা এক্সট্রাক্ট
        revenue = financial_data.get("revenue", 0) or 0
        current_fcf = financial_data.get("free_cash_flow", 0) or 0
        fcf_margin = financial_data.get("fcf_margin", 0) or (current_fcf / revenue if revenue > 0 else 0.05)
        shares_outstanding = financial_data.get("shares_outstanding", 1) or 1
        net_debt = (financial_data.get("total_debt", 0) or 0) - (financial_data.get("cash_and_equivalents", 0) or 0)
        current_price = financial_data.get("current_price", 0) or 0

        # ২. DCF প্যারামিটার্স (ডিফল্ট ভ্যালু সহ)
        projection_years = dcf_params.get("projection_years", 5)
        growth_rates = dcf_params.get("growth_rates", [0.08, 0.07, 0.06, 0.05, 0.04])[:projection_years]
        wacc = dcf_params.get("wacc", 0.15)
        terminal_growth = dcf_params.get("terminal_growth", 0.03)
        margin_of_safety = dcf_params.get("margin_of_safety", 0.20)

        # ৩. FCF প্রজেকশন (কনজারভেটিভ অ্যাপ্রোচ)
        base_fcf = current_fcf if current_fcf > 0 else revenue * fcf_margin
        fcf_projections = []
        for i, growth in enumerate(growth_rates):
            if i == 0:
                projected = base_fcf * (1 + growth)
            else:
                projected = fcf_projections[-1] * (1 + growth)
            fcf_projections.append(max(0, projected))

        # ৪. PV of Projected FCF
        pv_fcf_sum = sum([DCFValuation.discount_value(fcf, wacc, i+1) for i, fcf in enumerate(fcf_projections)])

        # ৫. Terminal Value & PV
        terminal_value = DCFValuation.calculate_terminal_value(fcf_projections[-1], terminal_growth, wacc)
        pv_terminal = DCFValuation.discount_value(terminal_value, wacc, projection_years)

        # ৬. Enterprise Value → Equity Value → Per Share Value
        enterprise_value = pv_fcf_sum + pv_terminal
        equity_value = enterprise_value - net_debt
        intrinsic_value_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else 0

        # ৭. Margin of Safety Adjusted Value
        mos_adjusted_value = intrinsic_value_per_share * (1 - margin_of_safety)

        # ৮. Investment Signal (BUY/HOLD/SELL)
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
            "upside_percent": round(upside, 2) if upside is not None else None,
            "signal": signal,
            "signal_color": signal_color,
            "fcf_projections": [round(f, 2) for f in fcf_projections],
            "pv_fcf_sum": round(pv_fcf_sum, 2),
            "pv_terminal": round(pv_terminal, 2),
            "terminal_value": round(terminal_value, 2),
            "net_debt": round(net_debt, 2),
            "calculation_note": "DCF based on Free Cash Flow projection with Gordon Growth Terminal Value"
        }
# ==================== ✅ DCF ENGINE END ====================


# ---------------------- Startup ----------------------
@app.on_event("startup")
async def startup():
    await init_db()
    print("✅ Database connected & indexes created!")

# ---------------------- Health Check ----------------------
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Financial Analyzer is running"}

@app.head("/health")
async def health_check_head():
    """HEAD request for UptimeRobot"""
    return HTMLResponse(content="", status_code=200)

# ---------------------- Pages ----------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Landing page - Company list with Edit/Delete"""
    companies = await db.companies.find({"is_active": True}).to_list(100)
    for c in companies:
        c["_id"] = str(c["_id"])

    html = """<!DOCTYPE html>
<html>
<head>
    <title>Financial Analyzer</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
    <link rel="manifest" href="/static/manifest.json">
    <meta name="theme-color" content="#3b82f6">
    <style>
        body { background: #0f172a; color: white; padding: 40px; font-family: Arial; }
        .company-card {
            background: #1e293b; padding: 16px; border-radius: 10px;
            margin-bottom: 12px; transition: all 0.3s;
        }
        .company-card:hover { background: #334155; }
        .btn-action {
            padding: 6px 12px; border-radius: 6px; text-decoration: none;
            font-size: 13px; margin-right: 6px; border: none; cursor: pointer;
            transition: all 0.2s; display: inline-block;
        }
        .btn-edit { background: #f59e0b; color: white; }
        .btn-edit:hover { background: #d97706; }
        .btn-delete { background: #ef4444; color: white; }
        .btn-delete:hover { background: #dc2626; }
        .btn-input { background: #10b981; color: white; }
        .btn-input:hover { background: #059669; }
        .btn-analysis { background: #06b6d4; color: white; }
        .btn-analysis:hover { background: #0891b2; }
        .modal-overlay {
            display: none; position: fixed; top: 0; left: 0;
            width: 100%; height: 100%; background: rgba(0,0,0,0.7);
            z-index: 1000; justify-content: center; align-items: center;
        }
        .modal-box {
            background: #1e293b; padding: 30px; border-radius: 15px;
            width: 90%; max-width: 500px; color: white;
        }
        .toast {
            position: fixed; bottom: 20px; right: 20px; padding: 12px 20px;
            border-radius: 8px; color: white; z-index: 2000; display: none;
        }
        .toast-success { background: #10b981; }
        .toast-error { background: #ef4444; }
    </style>
</head>
<body>
    <div style="max-width:800px;margin:0 auto;">
        <h1>📊 Financial Analyzer</h1>
        <a href="/add-company" style="background:#3b82f6;color:white;padding:10px 24px;border-radius:8px;text-decoration:none;display:inline-block;margin-bottom:20px;">+ Add Company</a>
        <div id="companyList">
"""

    if companies:
        for c in companies:
            html += f"""
            <div class="company-card" id="company-{c['_id']}">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
                    <div>
                        <strong>{c['name']}</strong> ({c['ticker']}) | 
                        <span style="background:#06b6d4;padding:2px 10px;border-radius:20px;font-size:12px;">{c.get('sector','')}</span>
                    </div>
                    <div>
                        <button class="btn-action btn-edit" onclick="editCompany('{c['_id']}')" title="Edit">
                            <i class="bi bi-pencil"></i> Edit
                        </button>
                        <button class="btn-action btn-delete" onclick="deleteCompany('{c['_id']}')" title="Delete">
                            <i class="bi bi-trash"></i> Delete
                        </button>
                    </div>
                </div>
                <div style="margin-top:8px;">
                    <a href="/input-data/{c['_id']}" class="btn-action btn-input">
                        <i class="bi bi-pencil-square"></i> Input Data
                    </a>
                    <a href="/analysis/{c['_id']}" class="btn-action btn-analysis">
                        <i class="bi bi-graph-up"></i> View Analysis
                    </a>
                </div>
            </div>"""
    else:
        html += '<p style="margin-top:30px;color:#94a3b8;">No companies added yet. Click "Add Company" to get started.</p>'

    html += """
        </div>
    </div>

    <!-- Edit Modal -->
    <div class="modal-overlay" id="editModal">
        <div class="modal-box">
            <h3>✏️ Edit Company</h3>
            <form id="editForm">
                <input type="hidden" id="editCompanyId">
                <div class="mb-3">
                    <label>Company Name</label>
                    <input type="text" id="editName" class="form-control" required 
                           style="background:#334155;color:white;border:1px solid #475569;">
                </div>
                <div class="mb-3">
                    <label>Ticker</label>
                    <input type="text" id="editTicker" class="form-control" required 
                           style="background:#334155;color:white;border:1px solid #475569;">
                </div>
                <div class="mb-3">
                    <label>Sector</label>
                    <select id="editSector" class="form-control" 
                            style="background:#334155;color:white;border:1px solid #475569;">
                        <option value="Bank">🏦 Bank</option>
                        <option value="Pharmaceuticals">💊 Pharmaceuticals</option>
                        <option value="Textile">👕 Textile</option>
                        <option value="Telecom">📱 Telecom</option>
                        <option value="Food">🍔 Food & Beverage</option>
                        <option value="Energy">⚡ Energy</option>
                        <option value="Cement">🏗️ Cement</option>
                        <option value="General">📦 General</option>
                    </select>
                </div>
                <div class="mb-3">
                    <label>Sub Sector (Optional)</label>
                    <input type="text" id="editSubSector" class="form-control" 
                           style="background:#334155;color:white;border:1px solid #475569;">
                </div>
                <div style="display:flex;gap:10px;">
                    <button type="submit" class="btn btn-primary" style="flex:1;">💾 Save Changes</button>
                    <button type="button" class="btn btn-secondary" onclick="closeEditModal()" style="flex:1;">Cancel</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Toast Notification -->
    <div class="toast" id="toast"></div>

    <script>
        // Register Service Worker
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/static/sw.js');
        }

        // Show Toast
        function showToast(message, type = 'success') {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast toast-' + type;
            toast.style.display = 'block';
            setTimeout(() => { toast.style.display = 'none'; }, 3000);
        }

        // Edit Company
        async function editCompany(companyId) {
            try {
                const response = await fetch('/api/companies');
                const companies = await response.json();
                const company = companies.find(c => c._id === companyId);
                
                if (company) {
                    document.getElementById('editCompanyId').value = company._id;
                    document.getElementById('editName').value = company.name;
                    document.getElementById('editTicker').value = company.ticker;
                    document.getElementById('editSector').value = company.sector;
                    document.getElementById('editSubSector').value = company.sub_sector || '';
                    document.getElementById('editModal').style.display = 'flex';
                }
            } catch (error) {
                showToast('Error loading company data', 'error');
            }
        }

        function closeEditModal() {
            document.getElementById('editModal').style.display = 'none';
        }

        document.getElementById('editForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const companyId = document.getElementById('editCompanyId').value;
            
            try {
                const response = await fetch('/api/companies/' + companyId, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: document.getElementById('editName').value,
                        ticker: document.getElementById('editTicker').value.toUpperCase(),
                        sector: document.getElementById('editSector').value,
                        sub_sector: document.getElementById('editSubSector').value || null
                    })
                });
                
                if (response.ok) {
                    closeEditModal();
                    showToast('Company updated successfully!');
                    setTimeout(() => location.reload(), 500);
                } else {
                    const err = await response.json();
                    showToast('Error: ' + (err.detail || 'Update failed'), 'error');
                }
            } catch (error) {
                showToast('Error updating company', 'error');
            }
        });

        // Delete Company
        async function deleteCompany(companyId) {
            const companyCard = document.getElementById('company-' + companyId);
            const companyName = companyCard.querySelector('strong').textContent;
            
            if (confirm('Are you sure you want to delete "' + companyName + '"?\\n\\nThis action cannot be undone!')) {
                try {
                    const response = await fetch('/api/companies/' + companyId, {
                        method: 'DELETE'
                    });
                    
                    if (response.ok) {
                        companyCard.remove();
                        showToast('Company deleted successfully!');
                        
                        // Check if no companies left
                        const remaining = document.querySelectorAll('.company-card');
                        if (remaining.length === 0) {
                            document.getElementById('companyList').innerHTML = 
                                '<p style="margin-top:30px;color:#94a3b8;">No companies added yet. Click "Add Company" to get started.</p>';
                        }
                    } else {
                        const err = await response.json();
                        showToast('Error: ' + (err.detail || 'Delete failed'), 'error');
                    }
                } catch (error) {
                    showToast('Error deleting company', 'error');
                }
            }
        }

        // Close modal on outside click
        document.getElementById('editModal').addEventListener('click', function(e) {
            if (e.target === this) closeEditModal();
        });
    </script>
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
        .dcf-note {{ font-size: 12px; color: #64748b; margin-top: 4px; }}
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

            <!-- 🆕 DCF Valuation Settings Section -->
            <div class="form-section" id="dcfSection">
                <h5 class="section-title">📊 DCF Valuation Settings <small style="font-weight:normal;color:#64748b;">(Optional - Auto-calculated if skipped)</small></h5>
                <p class="dcf-note">💡 DCF uses your FCF + Revenue data. Adjust assumptions below for custom valuation.</p>
                
                <div class="row mb-3">
                    <div class="col-md-3">
                        <label>Projection Years</label>
                        <select class="form-control" id="dcfYears">
                            <option value="5">5 Years</option>
                            <option value="7">7 Years</option>
                            <option value="10">10 Years</option>
                        </select>
                    </div>
                    <div class="col-md-3">
                        <label>WACC (%)</label>
                        <input type="number" step="0.1" class="form-control" id="dcfWacc" value="15.0" min="5" max="30">
                        <small class="dcf-note">Discount rate for Bangladesh market</small>
                    </div>
                    <div class="col-md-3">
                        <label>Terminal Growth (%)</label>
                        <input type="number" step="0.1" class="form-control" id="dcfTermGrowth" value="3.0" min="0" max="6">
                        <small class="dcf-note">Long-term GDP growth assumption</small>
                    </div>
                    <div class="col-md-3">
                        <label>Margin of Safety (%)</label>
                        <input type="number" step="1" class="form-control" id="dcfMos" value="20" min="0" max="50">
                        <small class="dcf-note">Buffer for uncertainty</small>
                    </div>
                </div>
                
                <!-- Growth Rates Input -->
                <div class="mb-3">
                    <label>Annual Growth Rates (%) for FCF Projection</label>
                    <div id="growthRatesContainer" class="d-flex gap-2 flex-wrap">
                        <!-- JavaScript will populate this -->
                    </div>
                    <small class="dcf-note">Year-by-year growth assumption for Free Cash Flow</small>
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
        // Report Type Toggle
        document.getElementById('reportType').addEventListener('change', function() {{
            document.getElementById('quarterDiv').style.display = this.value === 'quarterly' ? 'block' : 'none';
        }});
        
        // Bank Fields Toggle
        var sector = "{company_sector}";
        if (sector === "Bank") {{
            document.getElementById('bankFields').style.display = 'block';
        }}

        // 🆕 DCF: Dynamic Growth Rate Inputs
        function renderGrowthInputs(years = 5) {{
            const container = document.getElementById('growthRatesContainer');
            container.innerHTML = '';
            const defaults = [8, 7, 6, 5, 4, 3.5, 3, 2.5, 2, 1.5];
            for(let i = 0; i < years; i++) {{
                container.innerHTML += `
                    <div style="min-width:75px;">
                        <label style="font-size:11px;">Y${{i+1}}</label>
                        <input type="number" step="0.1" class="form-control form-control-sm growth-rate" 
                               value="${{defaults[i] || 3}}" min="0" max="50" data-year="${{i+1}}">
                    </div>
                `;
            }}
        }}
        renderGrowthInputs(5);
        document.getElementById('dcfYears').addEventListener('change', (e) => {{
            renderGrowthInputs(parseInt(e.target.value));
        }});

        // Form Submit Handler
        document.getElementById('financialForm').addEventListener('submit', async function(e) {{
            e.preventDefault();
            var btn = this.querySelector('button[type="submit"]');
            btn.disabled = true;
            btn.innerHTML = '⏳ Analyzing...';
            
            // Collect basic financial data
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
                net_interest_income: parseFloat(document.getElementById('nii')?.value) || null,
                // 🆕 DCF Parameters
                dcf_params: {{
                    projection_years: parseInt(document.getElementById('dcfYears').value),
                    growth_rates: Array.from(document.querySelectorAll('.growth-rate')).map(inp => parseFloat(inp.value)/100),
                    wacc: parseFloat(document.getElementById('dcfWacc').value)/100,
                    terminal_growth: parseFloat(document.getElementById('dcfTermGrowth').value)/100,
                    margin_of_safety: parseFloat(document.getElementById('dcfMos').value)/100
                }}
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

@app.get("/edit-data/{financial_id}", response_class=HTMLResponse)
async def edit_data_page(request: Request, financial_id: str):
    """Edit existing financial data"""
    try:
        financial_data = await db.financial_data.find_one({"_id": ObjectId(financial_id)})
        if not financial_data:
            raise HTTPException(404, "Financial data not found")
        
        company = await db.companies.find_one({"_id": financial_data["company_id"]})
        if not company:
            raise HTTPException(404, "Company not found")
    except:
        raise HTTPException(400, "Invalid ID format")

    company_name = company["name"]
    company_ticker = company["ticker"]
    company_sector = company.get("sector", "")
    financial_id_str = str(financial_data["_id"])
    company_id_str = str(company["_id"])

    def get_val(key, default=""):
        val = financial_data.get(key)
        return val if val is not None and val != 0 else default

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Edit Data - {company_name}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
    <style>
        body {{ background: #f5f6fa; padding: 20px; font-family: Arial; }}
        .form-section {{ background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .section-title {{ background: #2c3e50; color: white; padding: 10px 15px; border-radius: 5px; margin-bottom: 20px; }}
        .bank-fields {{ display: none; }}
        .btn-submit {{ background: #f59e0b; color: white; font-weight: bold; padding: 12px 40px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; }}
        .btn-submit:hover {{ background: #d97706; }}
        .btn-delete {{ background: #ef4444; color: white; padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; }}
        .btn-delete:hover {{ background: #dc2626; }}
        label {{ font-weight: 600; margin-top: 8px; }}
        input, select {{ margin-bottom: 6px; }}
        .badge-edit {{ background: #f59e0b; color: white; padding: 5px 12px; border-radius: 12px; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h2 class="mb-4">✏️ Edit Financial Data - {company_name} ({company_ticker})</h2>
        <span class="badge bg-info mb-3">{company_sector} Sector</span>
        <span class="badge-edit ms-2">Edit Mode</span>
        <div class="float-end">
            <button class="btn-delete" onclick="deleteRecord()"><i class="bi bi-trash"></i> Delete Record</button>
            <a href="/analysis/{company_id_str}" class="btn btn-sm btn-info ms-2">📊 View Analysis</a>
            <a href="/" class="btn btn-sm btn-secondary ms-2">⬅ Back</a>
        </div>

        <form id="editForm">
            <input type="hidden" id="financialId" value="{financial_id_str}">
            <input type="hidden" id="companyId" value="{company_id_str}">
            
            <div class="form-section">
                <h5 class="section-title">📅 Report Information</h5>
                <div class="row">
                    <div class="col-md-3">
                        <label>Report Type</label>
                        <select class="form-control" id="reportType">
                            <option value="annual" {'selected' if financial_data.get('report_type') == 'annual' else ''}>Annual</option>
                            <option value="quarterly" {'selected' if financial_data.get('report_type') == 'quarterly' else ''}>Quarterly</option>
                        </select>
                    </div>
                    <div class="col-md-3">
                        <label>Year</label>
                        <input type="number" class="form-control" id="year" value="{get_val('year', 2024)}">
                    </div>
                    <div class="col-md-3" id="quarterDiv" style="display:{'block' if financial_data.get('report_type') == 'quarterly' else 'none'};">
                        <label>Quarter</label>
                        <select class="form-control" id="quarter">
                            <option value="1" {'selected' if get_val('quarter') == 1 else ''}>Q1</option>
                            <option value="2" {'selected' if get_val('quarter') == 2 else ''}>Q2</option>
                            <option value="3" {'selected' if get_val('quarter') == 3 else ''}>Q3</option>
                            <option value="4" {'selected' if get_val('quarter') == 4 else ''}>Q4</option>
                        </select>
                    </div>
                </div>
            </div>

            <div class="form-section">
                <h5 class="section-title">📋 Balance Sheet</h5>
                <div class="row">
                    <div class="col-md-4"><label>Total Assets</label><input type="number" step="0.01" class="form-control" id="totalAssets" value="{get_val('total_assets')}"></div>
                    <div class="col-md-4"><label>Total Liabilities</label><input type="number" step="0.01" class="form-control" id="totalLiabilities" value="{get_val('total_liabilities')}"></div>
                    <div class="col-md-4"><label>Shareholders' Equity</label><input type="number" step="0.01" class="form-control" id="shareholdersEquity" value="{get_val('shareholders_equity')}"></div>
                </div>
                <div class="row mt-3">
                    <div class="col-md-4"><label>Total Debt</label><input type="number" step="0.01" class="form-control" id="totalDebt" value="{get_val('total_debt')}"></div>
                    <div class="col-md-4"><label>Cash & Equivalents</label><input type="number" step="0.01" class="form-control" id="cash" value="{get_val('cash_and_equivalents')}"></div>
                    <div class="col-md-4"><label>Current Assets</label><input type="number" step="0.01" class="form-control" id="currentAssets" value="{get_val('current_assets')}"></div>
                </div>
                <div class="row mt-3">
                    <div class="col-md-4"><label>Current Liabilities</label><input type="number" step="0.01" class="form-control" id="currentLiabilities" value="{get_val('current_liabilities')}"></div>
                </div>
            </div>

            <div class="form-section">
                <h5 class="section-title">📈 Income Statement</h5>
                <div class="row">
                    <div class="col-md-4"><label>Revenue</label><input type="number" step="0.01" class="form-control" id="revenue" value="{get_val('revenue')}"></div>
                    <div class="col-md-4"><label>Gross Profit</label><input type="number" step="0.01" class="form-control" id="grossProfit" value="{get_val('gross_profit')}"></div>
                    <div class="col-md-4"><label>Operating Income</label><input type="number" step="0.01" class="form-control" id="operatingIncome" value="{get_val('operating_income')}"></div>
                </div>
                <div class="row mt-3">
                    <div class="col-md-3"><label>EBIT</label><input type="number" step="0.01" class="form-control" id="ebit" value="{get_val('ebit')}"></div>
                    <div class="col-md-3"><label>EBITDA</label><input type="number" step="0.01" class="form-control" id="ebitda" value="{get_val('ebitda')}"></div>
                    <div class="col-md-3"><label>Interest Expense</label><input type="number" step="0.01" class="form-control" id="interestExpense" value="{get_val('interest_expense')}"></div>
                    <div class="col-md-3"><label>Net Income</label><input type="number" step="0.01" class="form-control" id="netIncome" value="{get_val('net_income')}"></div>
                </div>
            </div>

            <div class="form-section">
                <h5 class="section-title">💵 Cash Flow</h5>
                <div class="row">
                    <div class="col-md-4"><label>Operating Cash Flow</label><input type="number" step="0.01" class="form-control" id="ocf" value="{get_val('operating_cash_flow')}"></div>
                    <div class="col-md-4"><label>CAPEX</label><input type="number" step="0.01" class="form-control" id="capex" value="{get_val('capex')}"></div>
                    <div class="col-md-4"><label>Free Cash Flow</label><input type="number" step="0.01" class="form-control" id="fcf" value="{get_val('free_cash_flow')}"></div>
                </div>
            </div>

            <div class="form-section">
                <h5 class="section-title">📊 Per Share Data</h5>
                <div class="row">
                    <div class="col-md-3"><label>EPS</label><input type="number" step="0.01" class="form-control" id="eps" value="{get_val('eps')}"></div>
                    <div class="col-md-3"><label>DPS</label><input type="number" step="0.01" class="form-control" id="dps" value="{get_val('dps')}"></div>
                    <div class="col-md-3"><label>Shares Outstanding (M)</label><input type="number" step="0.01" class="form-control" id="sharesOut" value="{get_val('shares_outstanding')}"></div>
                    <div class="col-md-3"><label>Current Stock Price</label><input type="number" step="0.01" class="form-control" id="currentPrice" value="{get_val('current_price')}"></div>
                </div>
            </div>

            <div class="form-section bank-fields" id="bankFields">
                <h5 class="section-title">🏦 Bank Specific</h5>
                <div class="row">
                    <div class="col-md-4"><label>Total Deposits</label><input type="number" step="0.01" class="form-control" id="totalDeposits" value="{get_val('total_deposits')}"></div>
                    <div class="col-md-4"><label>Total Loans</label><input type="number" step="0.01" class="form-control" id="totalLoans" value="{get_val('total_loans')}"></div>
                    <div class="col-md-4"><label>Net Interest Income</label><input type="number" step="0.01" class="form-control" id="nii" value="{get_val('net_interest_income')}"></div>
                </div>
                <div class="row mt-3">
                    <div class="col-md-4"><label>NPL Ratio (%)</label><input type="number" step="0.01" class="form-control" id="nplRatio" value="{get_val('npl_ratio')}"></div>
                    <div class="col-md-4"><label>CAR (%)</label><input type="number" step="0.01" class="form-control" id="carRatio" value="{get_val('car_ratio')}"></div>
                </div>
            </div>

            <button type="submit" class="btn-submit btn-lg mt-3">💾 Update & Re-analyze</button>
        </form>
    </div>

    <script>
        // Report Type Toggle
        document.getElementById('reportType').addEventListener('change', function() {{
            document.getElementById('quarterDiv').style.display = this.value === 'quarterly' ? 'block' : 'none';
        }});
        
        // Bank Fields Toggle
        var sector = "{company_sector}";
        if (sector === "Bank") {{
            document.getElementById('bankFields').style.display = 'block';
        }}

        // Delete Record
        async function deleteRecord() {{
            if (confirm('Are you sure you want to delete this financial record?\\n\\nThis action cannot be undone!')) {{
                const financialId = document.getElementById('financialId').value;
                const companyId = document.getElementById('companyId').value;
                
                try {{
                    const response = await fetch('/api/financial-data/' + financialId, {{
                        method: 'DELETE'
                    }});
                    
                    if (response.ok) {{
                        alert('Record deleted successfully!');
                        window.location.href = '/analysis/' + companyId;
                    }} else {{
                        const err = await response.json();
                        alert('Error: ' + (err.detail || 'Delete failed'));
                    }}
                }} catch (error) {{
                    alert('Error deleting record: ' + error.message);
                }}
            }}
        }}

        // Form Submit Handler
        document.getElementById('editForm').addEventListener('submit', async function(e) {{
            e.preventDefault();
            var btn = this.querySelector('button[type="submit"]');
            btn.disabled = true;
            btn.innerHTML = '⏳ Updating...';
            
            const financialId = document.getElementById('financialId').value;
            
            var data = {{
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
                var response = await fetch('/api/financial-data/' + financialId, {{
                    method: 'PUT',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(data)
                }});
                var result = await response.json();
                if (response.ok) {{
                    alert('Updated & Re-analyzed successfully!');
                    window.location.href = '/result/' + financialId;
                }} else {{
                    alert('Error: ' + (result.detail || 'Update failed'));
                    btn.disabled = false;
                    btn.innerHTML = '💾 Update & Re-analyze';
                }}
            }} catch (error) {{
                alert('Error: ' + error.message);
                btn.disabled = false;
                btn.innerHTML = '💾 Update & Re-analyze';
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
            quarter = f" Q{fin.get('quarter')}" if fin.get('quarter') else ""
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

            dcf_html = ""
            if analysis.get("dcf_valuation"):
                dcf = analysis["dcf_valuation"]
                dcf_html = f"""
                <div style="margin-top:15px;padding:12px;background:rgba(6,182,212,0.1);border-radius:8px;border-left:4px solid #06b6d4;">
                    <strong>📊 DCF Value:</strong> {dcf.get('intrinsic_value_per_share', 'N/A')} টাকা 
                    <span style="background:{dcf.get('signal_color','#64748b')};color:white;padding:2px 10px;border-radius:12px;font-size:12px;margin-left:8px;">{dcf.get('signal','N/A')}</span>
                    {f"<span style='color:#10b981;margin-left:8px;'>↑ {dcf.get('upside_percent',0)}% upside</span>" if dcf.get('upside_percent') and dcf.get('upside_percent') > 0 else ""}
                </div>"""

            analyses_html += f"""
            <div style="background:#1e293b;padding:20px;border-radius:15px;margin-bottom:20px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">
                    <h4>{rtype} - {year}{quarter}</h4>
                    <a href="/edit-data/{fin_id}" class="btn btn-warning btn-sm">✏️ Edit</a>
                </div>
                <div style="text-align:center;margin:25px 0;">
                    <h2 style="color:{color};font-size:3rem;">{score}/100</h2>
                    <h4 style="color:{color};">{color_name}</h4>
                </div>
                <table style="width:100%;border-collapse:collapse;">
                    <thead><tr style="background:#334155;"><th style="padding:12px;text-align:left;">Metric</th><th style="padding:12px;">Value</th><th style="padding:12px;">Score</th><th style="padding:12px;">Status</th></tr></thead>
                    <tbody>{metrics_rows}</tbody>
                </table>
                {dcf_html}
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
    quarter = f" Q{analysis.get('quarter')}" if analysis.get('quarter') else ""
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

    dcf_card = ""
    if analysis.get("dcf_valuation"):
        dcf = analysis["dcf_valuation"]
        fcf_rows = "".join([f"<tr><td>Year {i+1}</td><td>{val} M</td></tr>" for i, val in enumerate(dcf.get('fcf_projections', []))])

        dcf_card = f"""
        <div style="margin-top:30px;background:#1e293b;padding:25px;border-radius:15px;border:2px solid #06b6d4;">
            <h4 style="text-align:center;color:#06b6d4;margin-bottom:20px;">📊 DCF Intrinsic Valuation</h4>
            
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:15px;text-align:center;margin-bottom:25px;">
                <div style="background:#334155;padding:15px;border-radius:10px;">
                    <div style="color:#94a3b8;font-size:13px;">Current Price</div>
                    <div style="font-size:1.3rem;font-weight:bold;">{dcf.get('current_price',0)} টাকা</div>
                </div>
                <div style="background:#334155;padding:15px;border-radius:10px;">
                    <div style="color:#94a3b8;font-size:13px;">Intrinsic Value</div>
                    <div style="font-size:1.3rem;font-weight:bold;color:#10b981;">{dcf.get('intrinsic_value_per_share',0)} টাকা</div>
                </div>
                <div style="background:#334155;padding:15px;border-radius:10px;">
                    <div style="color:#94a3b8;font-size:13px;">MoS Value</div>
                    <div style="font-size:1.3rem;font-weight:bold;color:#f59e0b;">{dcf.get('mos_adjusted_value',0)} টাকা</div>
                </div>
                <div style="background:#334155;padding:15px;border-radius:10px;">
                    <div style="color:#94a3b8;font-size:13px;">Upside</div>
                    <div style="font-size:1.3rem;font-weight:bold;color:{dcf.get('signal_color','#64748b')};">{dcf.get('upside_percent','N/A')}%</div>
                </div>
            </div>
            
            <div style="text-align:center;margin:20px 0;">
                <span style="background:{dcf.get('signal_color','#64748b')};color:white;padding:10px 30px;border-radius:30px;font-weight:bold;font-size:1.2rem;">
                    {dcf.get('signal','N/A')} SIGNAL
                </span>
            </div>
            
            <details style="margin-top:20px;">
                <summary style="cursor:pointer;color:#94a3b8;font-weight:500;">🔍 DCF Calculation Details</summary>
                <div style="margin-top:15px;background:#334155;padding:15px;border-radius:8px;">
                    <table style="width:100%;font-size:14px;">
                        <tr><td style="padding:6px 0;">WACC</td><td style="padding:6px 0;text-align:right;">{dcf.get('inputs',{}).get('wacc_percent','N/A')}%</td></tr>
                        <tr><td style="padding:6px 0;">Terminal Growth</td><td style="padding:6px 0;text-align:right;">{dcf.get('inputs',{}).get('terminal_growth_percent','N/A')}%</td></tr>
                        <tr><td style="padding:6px 0;">Projection Period</td><td style="padding:6px 0;text-align:right;">{dcf.get('inputs',{}).get('projection_years','N/A')} Years</td></tr>
                        <tr><td style="padding:6px 0;">Margin of Safety</td><td style="padding:6px 0;text-align:right;">{dcf.get('inputs',{}).get('margin_of_safety_percent','N/A')}%</td></tr>
                        <tr><td style="padding:6px 0;">PV of FCF</td><td style="padding:6px 0;text-align:right;">{dcf.get('pv_fcf_sum','N/A')} M</td></tr>
                        <tr><td style="padding:6px 0;">PV of Terminal</td><td style="padding:6px 0;text-align:right;">{dcf.get('pv_terminal','N/A')} M</td></tr>
                        <tr><td style="padding:6px 0;">Enterprise Value</td><td style="padding:6px 0;text-align:right;">{dcf.get('enterprise_value','N/A')} M</td></tr>
                        <tr><td style="padding:6px 0;">Net Debt</td><td style="padding:6px 0;text-align:right;">{dcf.get('net_debt','N/A')} M</td></tr>
                    </table>
                </div>
            </details>
            
            <details style="margin-top:15px;">
                <summary style="cursor:pointer;color:#94a3b8;font-weight:500;">📈 FCF Projections</summary>
                <div style="margin-top:10px;background:#334155;padding:10px;border-radius:8px;">
                    <table style="width:100%;font-size:13px;">
                        <thead><tr style="border-bottom:1px solid #475569;"><th style="padding:8px;text-align:left;">Year</th><th style="padding:8px;text-align:right;">Projected FCF</th></tr></thead>
                        <tbody>{fcf_rows}</tbody>
                    </table>
                </div>
            </details>
            
            <p style="margin-top:15px;font-size:12px;color:#94a3b8;text-align:center;">
                💡 {dcf.get('calculation_note','')}
            </p>
        </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Result - {name}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body style="background:#0f172a;color:white;padding:30px;font-family:Arial;">
    <div style="max-width:900px;margin:0 auto;background:#1e293b;padding:30px;border-radius:15px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
            <h3 style="text-align:center;flex:1;">{name} ({ticker})</h3>
            <a href="/edit-data/{financial_id}" class="btn btn-warning btn-sm">✏️ Edit Data</a>
        </div>
        <p style="text-align:center;color:#94a3b8;">{rtype} - {year}{quarter}</p>
        <div style="text-align:center;margin:25px 0;">
            <div style="width:150px;height:150px;border-radius:50%;background:{color};display:flex;align-items:center;justify-content:center;margin:0 auto;font-size:2.5rem;font-weight:bold;">{score}</div>
            <h4 style="color:{color};margin-top:12px;">{color_name}</h4>
        </div>
        <table style="width:100%;border-collapse:collapse;">
            <thead><tr style="background:#334155;"><th style="padding:12px;text-align:left;">Metric</th><th style="padding:12px;">Value</th><th style="padding:12px;">Score</th><th style="padding:12px;">Status</th></tr></thead>
            <tbody>{metrics_rows}</tbody>
        </table>
        {dcf_card}
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

@app.put("/api/companies/{company_id}")
async def update_company(company_id: str, company: CompanyCreate):
    """Update a company"""
    try:
        obj_id = ObjectId(company_id)
    except:
        raise HTTPException(400, "Invalid company ID")

    existing = await db.companies.find_one({"_id": obj_id})
    if not existing:
        raise HTTPException(404, "Company not found")

    duplicate = await db.companies.find_one({
        "ticker": company.ticker.upper(),
        "_id": {"$ne": obj_id}
    })
    if duplicate:
        raise HTTPException(400, "Another company with this ticker already exists")

    await db.companies.update_one(
        {"_id": obj_id},
        {"$set": {
            "name": company.name,
            "ticker": company.ticker.upper(),
            "sector": company.sector,
            "sub_sector": company.sub_sector,
            "updated_at": datetime.utcnow()
        }}
    )

    return {"message": "Company updated successfully"}

@app.delete("/api/companies/{company_id}")
async def delete_company(company_id: str):
    """Soft delete a company"""
    try:
        obj_id = ObjectId(company_id)
    except:
        raise HTTPException(400, "Invalid company ID")

    existing = await db.companies.find_one({"_id": obj_id})
    if not existing:
        raise HTTPException(404, "Company not found")

    await db.companies.update_one(
        {"_id": obj_id},
        {"$set": {"is_active": False, "deleted_at": datetime.utcnow()}}
    )

    return {"message": "Company deleted successfully"}

@app.post("/api/financial-data")
async def create_financial_data(data: FinancialDataCreate):
    """Input financial data and run analysis + DCF"""
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

    dcf_result = None
    if doc.get("free_cash_flow", 0) > 0 or doc.get("revenue", 0) > 0:
        dcf_params = getattr(data, 'dcf_params', None) or {}
        dcf_result = DCFValuation.run_dcf(doc, dcf_params, company)

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
        "dcf_valuation": dcf_result,
        "created_at": datetime.utcnow(),
    }
    await db.analysis_results.insert_one(analysis_doc)

    return {
        "financial_id": financial_id,
        "analysis": health_analysis,
        "dcf": dcf_result,
    }

@app.put("/api/financial-data/{financial_id}")
async def update_financial_data(financial_id: str, data: FinancialDataUpdate):
    """Update financial data and re-run analysis"""
    try:
        obj_id = ObjectId(financial_id)
    except:
        raise HTTPException(400, "Invalid financial data ID")

    existing = await db.financial_data.find_one({"_id": obj_id})
    if not existing:
        raise HTTPException(404, "Financial data not found")

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.utcnow()

    await db.financial_data.update_one(
        {"_id": obj_id},
        {"$set": update_data}
    )

    updated_doc = await db.financial_data.find_one({"_id": obj_id})

    company = await db.companies.find_one({"_id": existing["company_id"]})
    
    ratios = engine.calculate_ratios(updated_doc)
    health_analysis = engine.calculate_health_score(ratios, company.get("sector", "General"))

    dcf_result = None
    if updated_doc.get("free_cash_flow", 0) > 0 or updated_doc.get("revenue", 0) > 0:
        dcf_params = data.dcf_params if hasattr(data, 'dcf_params') and data.dcf_params else {}
        dcf_result = DCFValuation.run_dcf(updated_doc, dcf_params, company)

    analysis_update = {
        "overall_score": health_analysis["overall_score"],
        "overall_color": health_analysis["overall_color"],
        "overall_color_name": health_analysis["overall_color_name"],
        "metrics": health_analysis["metrics"],
        "ratios": health_analysis["ratios"],
        "dcf_valuation": dcf_result,
        "updated_at": datetime.utcnow(),
    }

    await db.analysis_results.update_one(
        {"financial_data_id": financial_id},
        {"$set": analysis_update},
        upsert=True
    )

    return {
        "message": "Financial data updated and re-analyzed successfully",
        "analysis": health_analysis,
        "dcf": dcf_result,
    }

@app.delete("/api/financial-data/{financial_id}")
async def delete_financial_data(financial_id: str):
    """Delete financial data and its analysis"""
    try:
        obj_id = ObjectId(financial_id)
    except:
        raise HTTPException(400, "Invalid financial data ID")

    existing = await db.financial_data.find_one({"_id": obj_id})
    if not existing:
        raise HTTPException(404, "Financial data not found")

    await db.financial_data.delete_one({"_id": obj_id})
    await db.analysis_results.delete_many({"financial_data_id": financial_id})

    return {"message": "Financial data and analysis deleted successfully"}

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
                "dcf_signal": analysis.get("dcf_valuation", {}).get("signal"),
                "dcf_upside": analysis.get("dcf_valuation", {}).get("upside_percent"),
            })

    return sorted(comparison, key=lambda x: x["overall_score"], reverse=True)

# ---------------------- Run Config ----------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)