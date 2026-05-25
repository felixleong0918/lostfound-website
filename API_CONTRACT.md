# API Contract

這份文件是給未來後端 / 全端協作者看的。  
目前產品採前後端分工，前端依照這份文件與 Flask API 或其他正式後端介接。

## Auth

### `POST /api/register`

Request:

```json
{
  "name": "使用者姓名",
  "email": "bxxxxxxxx@ntu.edu.tw",
  "password": "12345678"
}
```

Response:

```json
{
  "user": {
    "id": 1,
    "name": "使用者姓名",
    "email": "bxxxxxxxx@ntu.edu.tw"
  }
}
```

Rules:

- 必須檢查 `@ntu.edu.tw`
- 密碼長度至少 8 碼

### `POST /api/login`

Request:

```json
{
  "email": "bxxxxxxxx@ntu.edu.tw",
  "password": "12345678"
}
```

Response:

```json
{
  "user": {
    "id": 1,
    "name": "使用者姓名",
    "email": "bxxxxxxxx@ntu.edu.tw"
  }
}
```

### `POST /api/logout`

Response:

```json
{
  "ok": true
}
```

### `GET /api/session`

Response:

```json
{
  "user": {
    "id": 1,
    "name": "使用者姓名",
    "email": "bxxxxxxxx@ntu.edu.tw"
  }
}
```

## Bootstrap

### `GET /api/bootstrap`

Response:

```json
{
  "external_items": [],
  "reports": [],
  "matches": [],
  "notifications": []
}
```

## Lost Report

### `POST /api/report-lost`

Request:

```json
{
  "title": "黑色 AirPods Pro",
  "category": "電子產品",
  "location": "總圖 2F",
  "lost_at": "2026-05-25T14:20",
  "description": "黑色保護殼，外殼有白色貼紙"
}
```

Response:

```json
{
  "reports": [],
  "matches": [],
  "notifications": []
}
```

Behavior:

- 只接受遺失者提報
- 後端寫入使用者自己的遺失通報
- 後端立即執行媒合
- 若有新媒合，建立站內通知並寄 email

## Notifications

### `POST /api/notifications/read-all`

Response:

```json
{
  "notifications": []
}
```

## Data Shape

### `external_item`

```json
{
  "id": 1,
  "title": "AirPods Pro 耳機",
  "category": "電子產品",
  "location": "總圖 1F 服務台附近",
  "found_at": "2026-05-25T14:25",
  "description": "黑色充電盒，外殼上有白色貼紙，已送往服務台。",
  "source_name": "圖書館遺失版",
  "source_type": "library",
  "source_url": ""
}
```

### `match`

```json
{
  "id": "100-1",
  "report_title": "黑色 AirPods Pro",
  "external_title": "AirPods Pro 耳機",
  "external_location": "總圖 1F 服務台附近",
  "external_source_name": "圖書館遺失版",
  "external_source_type": "library",
  "external_source_url": "",
  "score": 81,
  "reasons_json": "[\"類型一致\", \"地點相近\"]",
  "created_at": "2026-05-25T16:00:00.000Z"
}
```
