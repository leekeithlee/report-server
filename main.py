"""
Daily Research Report Server
Stores and displays research reports for 3 companies
Supports PostgreSQL (Neon) and SQLite fallback
"""
import os
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI(title="Daily Research Report Server")

# ============================
# PostgreSQL (Neon) Functions
# ============================
def get_pg_connection():
    """Get PostgreSQL connection for Neon"""
    import psycopg
    return psycopg.connect(DATABASE_URL)

@contextmanager
def get_pg_cursor():
    """Context manager for PostgreSQL cursor"""
    conn = get_pg_connection()
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def init_pg_db():
    """Initialize PostgreSQL tables"""
    with get_pg_cursor() as cur:
        # Create companies table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS companies (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                website TEXT,
                description TEXT
            )
        ''')
        
        # Create reports table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id SERIAL PRIMARY KEY,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                report_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                tags TEXT
            )
        ''')
        
        # Create indexes
        cur.execute('CREATE INDEX IF NOT EXISTS idx_reports_company ON reports(company)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(report_date)')
        
        # Insert default companies
        companies = [
            ("Homeasy", "www.homeasy.hk", "家居服務有限公司"),
            ("Under-Shield", "www.under-shield.com", "機電/工程/防護服務"),
            ("Sustntech", "www.sustntech.com", "可持續發展/環保科技")
        ]
        for name, website, description in companies:
            cur.execute('''
                INSERT INTO companies (name, website, description) 
                VALUES (%s, %s, %s)
                ON CONFLICT (name) DO NOTHING
            ''', (name, website, description))

# ============================
# SQLite Functions (Fallback)
# ============================
DB_PATH = Path(__file__).parent / "reports.db"

def init_sqlite_db():
    """Initialize SQLite tables"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            report_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            tags TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            website TEXT,
            description TEXT
        )
    ''')
    companies = [
        ("Homeasy", "www.homeasy.hk", "家居服務有限公司"),
        ("Under-Shield", "www.under-shield.com", "機電/工程/防護服務"),
        ("Sustntech", "www.sustntech.com", "可持續發展/環保科技")
    ]
    c.executemany('INSERT OR IGNORE INTO companies (name, website, description) VALUES (?, ?, ?)', companies)
    conn.commit()
    conn.close()

# ============================
# Initialize Database
# ============================
if DATABASE_URL:
    # PostgreSQL mode (Neon)
    init_pg_db()
else:
    # SQLite fallback
    init_sqlite_db()

# ============================
# Pydantic Models
# ============================
class ReportSubmit(BaseModel):
    company: str
    title: str
    content: str
    report_date: str
    tags: Optional[str] = ""

class ReportResponse(BaseModel):
    id: int
    company: str
    title: str
    content: str
    report_date: str
    created_at: str
    tags: Optional[str]

# ============================
# API Endpoints
# ============================
@app.post("/api/reports")
async def submit_report(report: ReportSubmit):
    """Submit a new report"""
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if DATABASE_URL:
        with get_pg_cursor() as cur:
            cur.execute('''
                INSERT INTO reports (company, title, content, report_date, created_at, tags)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (report.company, report.title, report.content, report.report_date, created_at, report.tags or ""))
            report_id = cur.fetchone()[0]
        return {"status": "ok", "id": report_id, "created_at": created_at}
    else:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO reports (company, title, content, report_date, created_at, tags)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (report.company, report.title, report.content, report.report_date, created_at, report.tags or ""))
        conn.commit()
        report_id = c.lastrowid
        conn.close()
        return {"status": "ok", "id": report_id, "created_at": created_at}

@app.get("/api/reports")
async def get_reports(company: Optional[str] = None, limit: int = 100):
    """Get all reports with optional filter"""
    if DATABASE_URL:
        with get_pg_cursor() as cur:
            if company:
                cur.execute(
                    "SELECT * FROM reports WHERE company = %s ORDER BY created_at DESC LIMIT %s",
                    (company, limit)
                )
            else:
                cur.execute("SELECT * FROM reports ORDER BY created_at DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
            return [
                {"id": r[0], "company": r[1], "title": r[2], "content": r[3], 
                 "report_date": r[4], "created_at": r[5], "tags": r[6]}
                for r in rows
            ]
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        if company:
            c.execute("SELECT * FROM reports WHERE company = ? ORDER BY created_at DESC LIMIT ?", (company, limit))
        else:
            c.execute("SELECT * FROM reports ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]

@app.get("/api/reports/{report_id}")
async def get_report(report_id: int):
    """Get single report"""
    if DATABASE_URL:
        with get_pg_cursor() as cur:
            cur.execute("SELECT * FROM reports WHERE id = %s", (report_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Report not found")
            return {"id": row[0], "company": row[1], "title": row[2], "content": row[3],
                    "report_date": row[4], "created_at": row[5], "tags": row[6]}
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Report not found")
        return dict(row)

@app.get("/api/companies")
async def get_companies():
    """Get all companies"""
    if DATABASE_URL:
        with get_pg_cursor() as cur:
            cur.execute("SELECT * FROM companies")
            rows = cur.fetchall()
            return [{"id": r[0], "name": r[1], "website": r[2], "description": r[3]} for r in rows]
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM companies")
        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]

@app.delete("/api/reports/{report_id}")
async def delete_report(report_id: int):
    """Delete a report"""
    if DATABASE_URL:
        with get_pg_cursor() as cur:
            cur.execute("DELETE FROM reports WHERE id = %s", (report_id,))
            affected = cur.rowcount
        if affected == 0:
            raise HTTPException(status_code=404, detail="Report not found")
        return {"status": "deleted"}
    else:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        conn.commit()
        affected = c.rowcount
        conn.close()
        if affected == 0:
            raise HTTPException(status_code=404, detail="Report not found")
        return {"status": "deleted"}

# ============================
# HTML Dashboard
# ============================
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Main dashboard page"""
    reports_html = """
    <!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>每日研究報告 Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }
        .header { background: linear-gradient(135deg, #1a1a2e, #16213e); color: white; padding: 20px 40px; }
        .header h1 { font-size: 24px; margin-bottom: 5px; }
        .header p { color: #a0a0a0; font-size: 14px; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px 40px; }
        .filters { display: flex; gap: 15px; margin-bottom: 25px; align-items: center; flex-wrap: wrap; }
        .filter-btn { padding: 8px 20px; border: none; border-radius: 20px; cursor: pointer; font-size: 14px; background: white; color: #333; box-shadow: 0 2px 5px rgba(0,0,0,0.1); transition: all 0.3s; }
        .filter-btn:hover, .filter-btn.active { background: #1a1a2e; color: white; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }
        .stat-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.08); }
        .stat-card h3 { font-size: 14px; color: #888; margin-bottom: 8px; }
        .stat-card .number { font-size: 32px; font-weight: bold; color: #1a1a2e; }
        .reports-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; }
        .report-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.08); transition: transform 0.2s; cursor: pointer; }
        .report-card:hover { transform: translateY(-3px); box-shadow: 0 5px 20px rgba(0,0,0,0.15); }
        .report-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px; }
        .company-badge { padding: 4px 12px; border-radius: 15px; font-size: 12px; font-weight: 600; color: white; }
        .company-Homeasy { background: #4CAF50; }
        .company-Under-Shield { background: #2196F3; }
        .company-Sustntech { background: #FF9800; }
        .report-date { font-size: 12px; color: #888; }
        .report-title { font-size: 16px; font-weight: 600; margin-bottom: 8px; line-height: 1.4; }
        .report-preview { font-size: 13px; color: #666; line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
        .report-meta { margin-top: 12px; padding-top: 12px; border-top: 1px solid #eee; display: flex; justify-content: space-between; font-size: 12px; color: #888; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); z-index: 1000; justify-content: center; align-items: center; }
        .modal.show { display: flex; }
        .modal-content { background: white; border-radius: 16px; max-width: 800px; width: 90%; max-height: 85vh; overflow-y: auto; }
        .modal-header { padding: 20px 25px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
        .modal-header h2 { font-size: 18px; }
        .modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: #888; }
        .modal-body { padding: 25px; }
        .report-full-content { font-size: 14px; line-height: 1.8; white-space: pre-wrap; }
        .no-reports { text-align: center; padding: 60px 20px; color: #888; }
        .no-reports h3 { margin-bottom: 10px; font-size: 18px; }
        .search-box { flex: 1; min-width: 200px; }
        .search-box input { width: 100%; padding: 10px 15px; border: 1px solid #ddd; border-radius: 25px; font-size: 14px; }
        @media (max-width: 768px) {
            .container { padding: 20px; }
            .reports-grid { grid-template-columns: 1fr; }
            .header { padding: 15px 20px; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 每日研究報告 Dashboard</h1>
        <p>三間公司研究報告 • 自動收集 • 每週更新</p>
    </div>
    <div class="container">
        <div class="filters">
            <button class="filter-btn active" onclick="filterReports('all')">全部公司</button>
            <button class="filter-btn" onclick="filterReports('Homeasy')">Homeasy</button>
            <button class="filter-btn" onclick="filterReports('Under-Shield')">Under-Shield</button>
            <button class="filter-btn" onclick="filterReports('Sustntech')">Sustntech</button>
        </div>
        <div class="stats">
            <div class="stat-card"><h3>總報告數</h3><div class="number" id="total-count">--</div></div>
            <div class="stat-card"><h3>Homeasy</h3><div class="number" id="homeasy-count">--</div></div>
            <div class="stat-card"><h3>Under-Shield</h3><div class="number" id="undershield-count">--</div></div>
            <div class="stat-card"><h3>Sustntech</h3><div class="number" id="sustntech-count">--</div></div>
        </div>
        <div class="reports-grid" id="reports-grid">
            <div class="no-reports"><h3>載入中...</h3><p>正在連接伺服器...</p></div>
        </div>
    </div>
    <div class="modal" id="report-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 id="modal-title">報告詳情</h2>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="report-full-content" id="modal-content"></div>
            </div>
        </div>
    </div>
    <script>
        let allReports = [];
        let currentFilter = 'all';

        async function loadReports() {
            try {
                const res = await fetch('/api/reports?limit=200');
                allReports = await res.json();
                updateStats();
                renderReports();
            } catch (e) {
                document.getElementById('reports-grid').innerHTML = '<div class="no-reports"><h3>連接失敗</h3><p>無法連接到伺服器，請確認伺服器正在運行。</p></div>';
            }
        }

        function updateStats() {
            document.getElementById('total-count').textContent = allReports.length;
            document.getElementById('homeasy-count').textContent = allReports.filter(r => r.company === 'Homeasy').length;
            document.getElementById('undershield-count').textContent = allReports.filter(r => r.company === 'Under-Shield').length;
            document.getElementById('sustntech-count').textContent = allReports.filter(r => r.company === 'Sustntech').length;
        }

        function filterReports(company) {
            currentFilter = company;
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            event.target.classList.add('active');
            renderReports();
        }

        function renderReports() {
            const filtered = currentFilter === 'all' ? allReports : allReports.filter(r => r.company === currentFilter);
            const grid = document.getElementById('reports-grid');
            
            if (filtered.length === 0) {
                grid.innerHTML = '<div class="no-reports"><h3>暫無報告</h3><p>尚未收到任何研究報告。</p></div>';
                return;
            }

            grid.innerHTML = filtered.map(r => {
                const badgeClass = r.company === 'Homeasy' ? 'company-Homeasy' : r.company === 'Under-Shield' ? 'company-Under-Shield' : 'company-Sustntech';
                const preview = r.content.length > 200 ? r.content.substring(0, 200) + '...' : r.content;
                return `
                    <div class="report-card" onclick="openReport(${r.id})">
                        <div class="report-header">
                            <span class="company-badge ${badgeClass}">${r.company}</span>
                            <span class="report-date">${r.report_date}</span>
                        </div>
                        <div class="report-title">${r.title}</div>
                        <div class="report-preview">${preview}</div>
                        <div class="report-meta">
                            <span>${r.created_at}</span>
                            <span>點擊查看詳情 →</span>
                        </div>
                    </div>
                `;
            }).join('');
        }

        async function openReport(id) {
            const res = await fetch(`/api/reports/${id}`);
            const r = await res.json();
            document.getElementById('modal-title').textContent = r.title;
            document.getElementById('modal-content').textContent = r.content;
            document.getElementById('report-modal').classList.add('show');
        }

        function closeModal() {
            document.getElementById('report-modal').classList.remove('show');
        }

        document.getElementById('report-modal').addEventListener('click', function(e) {
            if (e.target === this) closeModal();
        });

        loadReports();
        setInterval(loadReports, 30000); // Refresh every 30s
    </script>
</body>
</html>
    """
    return reports_html

@app.get("/status")
async def status():
    """Health check endpoint"""
    db_type = "PostgreSQL (Neon)" if DATABASE_URL else "SQLite"
    return {"status": "ok", "server": "report-server", "version": "2.0.0", "database": db_type}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8765))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
