# Daily Research Report Server - Railway 部署

## 部署步驟

### 1. 推送代碼到 GitHub
```bash
cd /home/homea/.openclaw/workspace/report-railway
git init
git add .
git commit -m "Report Server for Railway"
gh repo create report-server --public --push
```

### 2. 連接到 Railway
1. 去 [railway.app](https://railway.app) 用 GitHub 登入
2. 點 "New Project" → "Deploy from GitHub repo"
3. 選擇 `report-server` repo
4. Railway 會自動檢測係 Python 項目

### 3. 設置環境變量（如需要）
在 Railway Dashboard → 項目 → 設定：
- `PORT` = 8000 (Railway 會自動設置)

### 4. 部署完成！
Railway 會自動安裝依賴並啟動服務。

---

## 技術栈
- **後端**: FastAPI + Python 3.11
- **數據庫**: SQLite（直接持久化）
- **部署**: Railway

## 本地運行
```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8765
```
