# NTU Lost ETL Hub

這個 repo 現在定位成 **正式產品的前端與介面層專案**，用來展示並承接台大校園失物 ETL 聚合平台的核心使用流程。

也就是說，這份 codebase 的責任是：

- 展示 ETL 聚合型失物平台的前端流程
- 呈現登入 / 註冊頁
- 呈現遺失物招領名單與來源欄位
- 提供使用者提報遺失物的互動
- 呈現媒合結果與 email 通知體驗
- 定義前後端整合所需的 API contract
- 以 `Flask` 實作核心的 `auth/register/report-lost`

不在這個 repo 裡做的事：

- 完整的資料擷取排程
- 各來源的正式 crawler / connector
- 生產等級的部署與監控配置

## 系統分工

目前專案採前後端整合：

- 前端負責登入 / 註冊頁、來源名單、遺失物提報、媒合結果與通知體驗
- `Flask` 後端負責 `auth/register`、資料寫入、媒合與 email 通知
- API 結構定義於 [API_CONTRACT.md](/Users/felix/.openclaw/workspace/lostfound-website/API_CONTRACT.md)

這代表它不是單純的視覺稿，而是已經帶有可運作 Python backend 的產品雛形；完整 ETL 擷取與生產部署仍可繼續擴充。

## 產品方向

### 1. 不提供拾得物上傳

這個平台現在不是一般雙向 lost-and-found board，而是更純的 ETL 聚合前端：

- 外部來源先匯入招領資料
- 使用者只需提報「自己遺失了什麼」
- 系統列出可能配對

### 2. 招領名單必須標示來源

目前產品整合的來源有：

- `FB交流版`
- `圖書館遺失版`
- `駐警隊`

其中：

- `FB交流版` 只放原始貼文連結
- 其他來源直接顯示來源名稱

### 3. 登入註冊要提醒 NTU email

UI 上會明確提醒：

- 請使用 `@ntu.edu.tw` 信箱註冊
- 請使用 `@ntu.edu.tw` 信箱登入

前端會先提醒並驗證這件事，後端也應再做一次正式驗證。

## 專案結構

```text
lostfound-website/
├── app.py
├── index.html
├── requirements.txt
├── script.js
├── styles.css
├── API_CONTRACT.md
└── README.md
```

## 本地執行

這個版本需要本機有 Python 3，並安裝依賴：

```bash
pip3 install --user -r requirements.txt
```

最推薦直接用：

```bash
cd /Users/felix/.openclaw/workspace/lostfound-website
task up
```

然後開：

```text
http://127.0.0.1:8000
```

其他常用指令：

```bash
task down
task open
```

如果你不想用 `task`，也可以直接：

```bash
pip3 install --user -r requirements.txt
python3 app.py
```

## Python 功能

目前這個 repo 已經用 `Flask` 實作：

- `auth`
- `register`
- `發布遺失物`
- session-based login state
- SQLite 資料存放
- 規則式媒合
- 站內通知

如果沒有設定 SMTP，信件內容會先寫到 `mail.log`。

## GitHub Pages 注意事項

GitHub Pages 只能部署靜態檔案，例如：

- `index.html`
- `styles.css`
- `script.js`
- 圖片與其他前端素材

它不會執行 `app.py`，也不會啟動 `Flask` server、SQLite database、session 或任何 Python API。

所以如果直接把這個 repo push 到 GitHub Pages，頁面雖然可以打開，但登入、註冊、送出遺失物等功能會出現 `Request failed`。原因是前端目前會呼叫：

```text
POST /api/login
POST /api/register
POST /api/lost-reports
```

本機開發時，這些 request 會送到正在執行的 Flask server：

```text
http://127.0.0.1:8000/api/login
```

但在 GitHub Pages 上，瀏覽器會改成打 GitHub Pages 的網址，例如：

```text
https://<username>.github.io/api/login
```

或 project site 底下的 Pages 網址。GitHub Pages 並沒有這些 API route，因此 request 會失敗。

如果要讓 GitHub Pages 可以展示完整流程，有兩種做法：

1. 改成純前端 demo mode：使用 `localStorage` 儲存假登入狀態與展示資料，不呼叫 Flask API。
2. 保留真實後端：把 Flask API 另外部署到 Render / Railway / Fly.io，再把 `script.js` 的 API base URL 改成正式後端網址。

目前完整功能請用本機方式執行：

```bash
cd /Users/felix/.openclaw/workspace/lostfound-website
task up
```

然後開：

```text
http://127.0.0.1:8000
```

## 部署到 Vercel

如果你們之後把前端部署到 Vercel，要注意：

- 目前這份 repo 的 `Flask` backend 不會自動變成可用 API
- Vercel 這邊比較適合放前端頁面
- Python backend 比較適合另外部署到 Render / Railway / Fly.io

目前只要把這個 repo push 到 GitHub，然後在 Vercel：

1. `Add New Project`
2. 選這個 GitHub repo
3. Framework Preset 選 `Other`
4. Build Command 留空
5. Output Directory 留空
6. 直接 deploy

我已經補了：

- [vercel.json](/Users/felix/.openclaw/workspace/lostfound-website/vercel.json)
- [.vercelignore](/Users/felix/.openclaw/workspace/lostfound-website/.vercelignore)

這樣前端靜態頁可以先上線，之後再把 `script.js` 裡的 API base URL 指向真正部署出去的 Python backend。

## 團隊協作建議

如果這個 repo 要和別人協作，合理的切法應該是：

1. 這個 repo 保持前端畫面與 Flask backend 的整合開發版本
2. 正式部署時，前端與 Python API 可以拆成不同服務
3. 之後再把 ETL 擷取、SMTP、資料來源同步做成真正的 production pipeline

這樣責任最清楚，也能維持產品演進時的模組邊界。
