"""語意媒合：以 Jina embeddings v3 產生向量，計算遺失通報與招領物的相似度。

設計重點
--------
* **語意 + 結構化混合評分**：embedding 向量的 cosine 相似度負責「意思相近」
  （例如「錢」≈「現金」、「皮夾」≈「錢包」），再加上類型 / 地點 / 時間等結構化訊號。
* **向量儲存**：embedding 以 JSON 陣列存在 Postgres 的 text 欄位
  （``lost_items.embedding`` / ``lost_reports.embedding``），在 Python 端算 cosine；
  資料量還小，暴力法完全夠用。資料量變大要改用 pgvector 索引時見 ``supabase/pgvector.sql``。
  （embedding 的讀寫與媒合流程在 ``app.py``，本模組只提供純函式。）
* **優雅降級**：若未設定 ``JINA_API_KEY`` 或呼叫失敗，會退回原本的關鍵字重疊比對，
  服務仍可運作（方便本機開發與測試）。
"""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# --- Jina embeddings v3 設定 ---
# 金鑰於呼叫時才讀取（lazy），避免相依於 load_dotenv() 與 import 的先後順序。
JINA_URL = "https://api.jina.ai/v1/embeddings"
JINA_MODEL = "jina-embeddings-v3"
# text-matching：對稱式語意相似，適合「通報 vs 招領物」的比對情境。
JINA_TASK = "text-matching"
EMBED_DIM = 1024
JINA_TIMEOUT = 60  # 批次請求較大，給寬一點的逾時秒數

# --- 評分權重（可依實際資料微調）---
CATEGORY_POINTS = 25      # 類型完全一致
LOCATION_POINTS = 15      # 地點前綴相近
TIME_CLOSE_POINTS = 15    # 時間 <= 6 小時
TIME_OK_POINTS = 8        # 時間 <= 24 小時
SEMANTIC_MAX = 45         # 語意相似最高加分
SEMANTIC_FLOOR = 0.35     # cosine 低於此值不計語意分（過濾雜訊）
KEYWORD_MAX = 25          # 無向量時的關鍵字 fallback 上限
MATCH_THRESHOLD = 45      # 達到此分數才視為一筆媒合
SCORE_CAP = 99

# --- 台大校內地點簡稱 → 正式名稱 ---
# 校內慣用簡稱（如「活大」）一般 embedding 模型不認得，且地點是用結構化比對而非語意，
# 因此用這張對照表把簡稱正規化後再比。
#
# 對照表存在 location_aliases.json，方便非工程背景的貢獻者直接增修（不必動程式）。
# 這份 JSON 的格式刻意做成「簡稱: 正式名稱」的扁平結構，之後搬到 Supabase 時可直接
# 對應一張 location_aliases 資料表，改由後台維護、免重新部署。
# 下方的 _FALLBACK_ALIASES 是 JSON 缺失或格式錯誤時的內建預設，確保服務仍可運作。
_FALLBACK_ALIASES: dict[str, str] = {
    "活大": "第一學生活動中心",
    "總圖": "總圖書館",
    "小福": "小福樓",
}
_ALIASES_PATH = Path(__file__).resolve().parent / "location_aliases.json"


def _load_location_aliases() -> dict[str, str]:
    try:
        with _ALIASES_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and all(
            isinstance(k, str) and isinstance(v, str) for k, v in data.items()
        ):
            return data
    except FileNotFoundError:
        pass
    except (ValueError, OSError):
        pass
    return dict(_FALLBACK_ALIASES)


LOCATION_ALIASES: dict[str, str] = _load_location_aliases()
# 先換較長的簡稱，避免「第一活動中心」被「活」之類的短鍵搶先替換。
_ALIAS_ORDER = sorted(LOCATION_ALIASES, key=len, reverse=True)
_CANONICAL_PLACES = set(LOCATION_ALIASES.values())


# ---------------------------------------------------------------------------
# Embedding 客戶端
# ---------------------------------------------------------------------------
def _api_key() -> str | None:
    return os.environ.get("JINA_API_KEY")


def embeddings_enabled() -> bool:
    return bool(_api_key())


def embed_texts(texts: list[str]) -> list[list[float]]:
    """呼叫 Jina API，回傳與輸入順序一致的向量清單。"""
    api_key = _api_key()
    if not api_key:
        raise RuntimeError("JINA_API_KEY 未設定")
    payload = json.dumps(
        {
            "model": JINA_MODEL,
            "task": JINA_TASK,
            "dimensions": EMBED_DIM,
            "embedding_type": "float",
            "input": texts,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        JINA_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            # 帶上 User-Agent，避免被 Cloudflare 擋下預設的 Python-urllib 簽章（error 1010）。
            "User-Agent": "ntu-lostfound/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=JINA_TIMEOUT) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    rows = sorted(body["data"], key=lambda d: d["index"])
    return [row["embedding"] for row in rows]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def item_text(row) -> str:
    """招領物 / 通報共用的語意文字：以物品本身的標題與描述為主。"""
    return f"{row['title']}。{row['description']}"


# ---------------------------------------------------------------------------
# 向量運算
# ---------------------------------------------------------------------------
def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _semantic_points(cos: float) -> int:
    if cos <= SEMANTIC_FLOOR:
        return 0
    scaled = (cos - SEMANTIC_FLOOR) / (1.0 - SEMANTIC_FLOOR)
    return round(SEMANTIC_MAX * scaled)


# ---------------------------------------------------------------------------
# 結構化 / 關鍵字評分
# ---------------------------------------------------------------------------
def normalize_words(text: str) -> set[str]:
    clean = text.lower()
    for token in ["：", "，", ",", ".", "(", ")", "[", "]", "{", "}", "<", ">", "。"]:
        clean = clean.replace(token, " ")
    return {piece for piece in clean.split() if piece}


def canonical_location(text: str) -> str:
    """把校內慣用簡稱（活大、總圖…）展開成正式名稱，方便地點比對。"""
    result = text
    for alias in _ALIAS_ORDER:
        canon = LOCATION_ALIASES[alias]
        # 已是正式名稱就略過，避免重複展開（如「普通教學館」→「普通教學館教學館」）。
        if canon in result:
            continue
        if alias in result:
            result = result.replace(alias, canon)
    return result.lower()


def _location_match(report_location: str, external_location: str) -> bool:
    r = canonical_location(report_location)
    e = canonical_location(external_location)
    # 兩邊（正規化後）提到同一個已知地點 → 視為相近。
    for place in _CANONICAL_PLACES:
        p = place.lower()
        if p in r and p in e:
            return True
    # 退而求其次：正規化後的前綴重疊（沿用原本的粗略啟發式）。
    return bool(r[:2]) and (r[:2] in e or e[:2] in r)


def _structured_score(report, external) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if report["category"] == external["category"]:
        score += CATEGORY_POINTS
        reasons.append("類型一致")
    if _location_match(report["location"], external["location"]):
        score += LOCATION_POINTS
        reasons.append("地點相近")
    report_time = datetime.fromisoformat(report["lost_at"])
    external_time = datetime.fromisoformat(external["found_at"])
    diff_hours = abs((external_time - report_time).total_seconds()) / 3600
    if diff_hours <= 6:
        score += TIME_CLOSE_POINTS
        reasons.append("時間高度接近")
    elif diff_hours <= 24:
        score += TIME_OK_POINTS
        reasons.append("時間落在合理範圍")
    return score, reasons


def _keyword_score(report, external) -> tuple[int, list[str]]:
    shared = normalize_words(report["title"] + " " + report["description"]).intersection(
        normalize_words(external["title"] + " " + external["description"])
    )
    if not shared:
        return 0, []
    points = min(KEYWORD_MAX, len(shared) * 6)
    return points, ["關鍵字重疊：" + "、".join(sorted(shared)[:4])]


def blended_score(report, external, cos: float | None) -> tuple[int, list[str]]:
    """結合結構化訊號與語意（或關鍵字 fallback）的最終分數。"""
    score, reasons = _structured_score(report, external)
    if cos is not None:
        points = _semantic_points(cos)
        if points:
            score += points
            reasons.append(f"語意相近（{round(cos * 100)}%）")
    else:
        points, kw_reasons = _keyword_score(report, external)
        score += points
        reasons.extend(kw_reasons)
    return min(score, SCORE_CAP), reasons


