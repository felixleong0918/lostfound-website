from __future__ import annotations

from datetime import date

import pytest

import matching


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("白色 AirPods Pro 耳機", "電子產品"),
        ("台大學生證", "證件/卡片"),
        ("黑色折疊傘", "雨傘"),
        ("Nike 後背包", "包包"),
        ("無法分類的物品", "其他"),
    ],
)
def test_canonical_category(raw, expected):
    assert matching.canonical_category(raw) == expected


@pytest.mark.unit
def test_canonical_location_expands_ntu_aliases():
    assert matching.canonical_location("二活三樓") == "第二學生活動中心三樓"
    assert matching.canonical_location("活大一樓") == "第一學生活動中心一樓"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("found_at", "expected_points", "expected_reason"),
    [
        ("2026-06-07T12:00:00", 15, "時間吻合"),
        ("2026-06-09T12:00:00", 8, "時間接近"),
        ("2026-06-12T12:00:00", 4, "時間大致符合"),
        ("2026-06-13T12:00:00", 0, None),
    ],
)
def test_time_score_uses_report_date_range(found_at, expected_points, expected_reason):
    report = {
        "lost_date_start": date(2026, 6, 6).isoformat(),
        "lost_date_end": date(2026, 6, 7).isoformat(),
    }

    points, reason = matching._time_score(report, {"found_at": found_at})

    assert points == expected_points
    assert reason == expected_reason


@pytest.mark.unit
def test_blended_score_crosses_threshold_for_close_report():
    report = {
        "title": "AirPods Pro 不見了",
        "category": "電子產品",
        "location": "二活三樓",
        "lost_date_start": "2026-06-07",
        "lost_date_end": "2026-06-07",
        "description": "白色耳機盒，灰色保護套",
    }
    item = {
        "title": "白色 AirPods Pro 耳機",
        "category": "電子產品",
        "location": "第二學生活動中心三樓",
        "found_at": "2026-06-07T12:35:00",
        "description": "白色 AirPods Pro 充電盒，外殼有灰色保護套。",
    }

    score, reasons = matching.blended_score(report, item, cos=None)

    assert score >= matching.MATCH_THRESHOLD
    assert "類型一致" in reasons
    assert "地點相近" in reasons
    assert "時間吻合" in reasons


@pytest.mark.unit
def test_blended_score_rejects_unrelated_report():
    report = {
        "title": "紅色圍巾",
        "category": "衣物/配件",
        "location": "管理學院",
        "lost_date_start": "2026-05-01",
        "lost_date_end": "2026-05-01",
        "description": "羊毛材質",
    }
    item = {
        "title": "白色 AirPods Pro 耳機",
        "category": "電子產品",
        "location": "第二學生活動中心三樓",
        "found_at": "2026-06-07T12:35:00",
        "description": "灰色保護套",
    }

    score, reasons = matching.blended_score(report, item, cos=None)

    assert score < matching.MATCH_THRESHOLD
    assert reasons == []
