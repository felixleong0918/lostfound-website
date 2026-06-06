"""Vercel 進入點：把根目錄的 Flask app 當成 WSGI handler 匯出。

Vercel 的 @vercel/python runtime 會抓這個檔案裡名為 ``app`` 的變數當 WSGI 應用。
vercel.json 會把所有路徑 rewrite 到這支，因此整個 Flask app（含 /static）都由它服務。
"""

import os
import sys

# 讓本檔可以 import 專案根目錄的 app.py / matching.py / bridge.py。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402  re-export 給 Vercel 當 WSGI handler

__all__ = ["app"]
