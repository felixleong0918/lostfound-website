"""處理剛爬進來的招領物：產生語意向量並反向比對現有遺失通報（必要時寄出通知）。

用法（通常接在爬蟲之後）：
    python scripts/scrapers/supa_crawl_lib.py   # 把資料 upsert 進 lost_items
    python scripts/match_lost_items.py          # 對新資料算向量 + 媒合

需要環境變數：DATABASE_URL（Supabase Postgres），以及（可選）JINA_API_KEY 啟用語意比對。
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import app  # noqa: E402  匯入時會載入 .env 並確保資料表存在


def main() -> int:
    result = app.process_new_lost_items()
    if not result.get("ok"):
        print(f"處理失敗：{result.get('error')}")
        return 1
    print(f"處理完成：新處理 {result['processed']} 筆招領物，新增 {result['new_matches']} 筆媒合。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
