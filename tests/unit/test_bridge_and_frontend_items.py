from __future__ import annotations

from datetime import datetime

import pytest

import bridge
import matching
from frontend_items import FRONTEND_ITEMS


@pytest.mark.unit
def test_lost_item_to_external_maps_scraper_row():
    external = bridge.lost_item_to_external(
        {
            "source_system": "school_libraries",
            "original_id": "A123",
            "found_date": "2026/06/07",
            "location": "總圖2F",
            "description": "黑色折疊傘",
            "category": "其他",
            "storage_place": "一樓服務台",
        }
    )

    assert external["source_ref"] == "school_libraries:A123"
    assert external["source_name"] == "總圖書館"
    assert external["source_type"] == "library"
    assert external["category"] == "雨傘"
    assert external["found_at"] == "2026-06-07T00:00:00"
    assert "存放：一樓服務台" in external["description"]


@pytest.mark.unit
def test_frontend_items_follow_external_contract():
    required = {
        "source_ref",
        "title",
        "category",
        "location",
        "found_at",
        "description",
        "source_name",
        "source_type",
        "source_url",
    }

    assert len(FRONTEND_ITEMS) == 8
    assert sum(item["source_name"] == "駐警隊" for item in FRONTEND_ITEMS) == 4
    assert sum(item["source_name"] == "FB交流版" for item in FRONTEND_ITEMS) == 4

    for item in FRONTEND_ITEMS:
        assert required <= item.keys()
        assert item["category"] in matching.CANONICAL_CATEGORIES
        datetime.fromisoformat(item["found_at"])
        if item["source_type"] == "facebook":
            assert item["source_url"].startswith("https://")
