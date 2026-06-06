# HTTP 路由與資料結構

目前產品是 **Flask 伺服器端渲染**（不是 JSON API）。登入採 Supabase Email OTP，
找到的招領物來自 Supabase Postgres 的 `lost_items`，使用者提報存在 `lost_reports`，
媒合結果存在 `matches`。

> 歷史備註：舊版本曾規劃 `POST /api/register`、`/api/login` 等密碼式 JSON API，
> 現已改為下列 OTP + 伺服器渲染流程，舊契約不再適用。

## 路由

| 方法 | 路徑 | 登入 | 說明 |
|------|------|------|------|
| GET, POST | `/login` | 否 | 輸入台大 email；POST 會寄出 OTP 驗證碼 |
| GET, POST | `/verify` | 否 | 輸入 OTP；驗證成功則建立 / 登入使用者 |
| POST | `/logout` | 是 | 清除 session |
| GET | `/` | 否 | 儀表板（來源統計、近期媒合） |
| GET | `/sources` | 否 | 招領物名單；query：`q`、`source`、`category` |
| GET, POST | `/report` | 是 | 提報遺失物；POST 後立即媒合並導向 `/matches` |
| GET, POST | `/report/<id>/edit` | 是 | 編輯通報（清掉舊媒合並重新比對） |
| POST | `/report/<id>/resolve` | 是 | 標記為「已找到」（停止後續媒合） |
| POST | `/report/<id>/reopen` | 是 | 重新開啟通報 |
| POST | `/report/<id>/delete` | 是 | 刪除通報（連同其媒合） |
| GET | `/matches` | 是 | 我的媒合結果 |
| GET | `/notifications` | 是 | 我的通知 |
| POST | `/notifications/read-all` | 是 | 全部標示為已讀 |

提報表單欄位（`POST /report`、`/report/<id>/edit`）：`title`、`category`（取自正規類別清單）、
`location`、`lost_date_start`（`YYYY-MM-DD`，必填）、`lost_date_end`（`YYYY-MM-DD`，可留空＝單日）、
`description`。`category` 與篩選共用 `category_rules.json` 定義的正規類別。
只有 `status='open'` 的通報會參與媒合。

未登入者在 `/sources`、`/` 只會看到非 facebook 來源的招領物。

## 資料表（Supabase Postgres）

### `lost_items`（招領物，由爬蟲維護）
`id`(int) · `source_system` · `original_id` · `found_date`(字串如 `2026/06/05`) ·
`location` · `description` · `category` · `storage_place` · `created_at` ·
`embedding`(語意向量 JSON 字串)
唯一鍵：`(source_system, original_id)`。

### `lost_reports`（使用者提報）
`id` · `user_id`→`users.id` · `title` · `category`(正規類別) · `location` ·
`lost_date_start`(YYYY-MM-DD) · `lost_date_end`(YYYY-MM-DD) ·
`status`(`open`/`resolved`) · `description` · `embedding` · `created_at`

### `matches`
`id` · `report_id`→`lost_reports.id` · `lost_item_id`→`lost_items.id` ·
`score`(0–99) · `reasons_json`(原因字串陣列) · `created_at`
唯一鍵：`(report_id, lost_item_id)`。

### `notifications`
`id` · `user_id`→`users.id` · `subject` · `message` · `is_read`(0/1) ·
`delivery` · `created_at`

### `users`
`id` · `supabase_id` · `name` · `email`(唯一) · `created_at`

## UI / 媒合用的「external」形狀

`bridge.lost_item_to_external()` 會把一筆 `lost_items` 補成下列形狀給畫面與媒合使用
（`lost_items` 沒有的欄位在此合成）：

```json
{
  "id": 1,
  "title": "黑色折疊傘一把",
  "category": "雨傘",
  "location": "總圖2F其他區域",
  "found_at": "2026-06-05T00:00:00",
  "description": "黑色折疊傘一把（存放：總圖一樓服務台）",
  "source_name": "總圖書館",
  "source_type": "library",
  "source_url": ""
}
```

`match`（畫面上呈現的一筆媒合）：

```json
{
  "id": 1,
  "report_title": "遺失黑色雨傘",
  "external_title": "黑色折疊傘一把",
  "external_location": "總圖2F其他區域",
  "external_source_name": "總圖書館",
  "external_source_type": "library",
  "external_source_url": "",
  "score": 81,
  "reasons_json": "[\"類型一致\", \"地點相近\", \"語意相近（81%）\"]",
  "created_at": "2026-06-06T18:00:00"
}
```
