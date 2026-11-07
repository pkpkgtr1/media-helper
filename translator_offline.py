# -*- coding: utf-8 -*-
"""
翻译模块 (ja -> zh) —— 在线优先 + 离线回退
- 优先使用 googletrans-py (免费在线接口)
- 失败时回退 Argos Translate (离线 ja->en->zh)
- 带缓存，避免重复翻译
- 加了重试机制，避免一次失败直接放弃
"""

import os, sys, time
import requests
from functools import lru_cache

# ---------- Googletrans ----------
_USE_GT = False
_gt = None
try:
    from googletrans import Translator
    # 用 translate.google.com 比 translate.googleapis.com 更稳
    _gt = Translator(service_urls=["translate.google.com"])
    _USE_GT = True
except Exception as e:
    if os.environ.get("TRANSLATOR_DEBUG") == "1":
        print("⚠️ googletrans 导入失败:", e)

# ---------- Argos ----------
try:
    import argostranslate.package as argos_pkg
    import argostranslate.translate as argos_trans
    _ARGOS_OK = True
except Exception as e:
    if os.environ.get("TRANSLATOR_DEBUG") == "1":
        print("⚠️ Argos Translate 导入失败:", e)
    argos_pkg = None
    argos_trans = None
    _ARGOS_OK = False

# ---------- 工具 ----------
def _install_all_models():
    """仅在需要时安装 models/ 下的 argosmodel"""
    if not (argos_pkg and argos_trans):
        return
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
           else os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.join(base, "models")
    if not os.path.isdir(models_dir):
        return
    for fn in os.listdir(models_dir):
        if fn.lower().endswith(".argosmodel"):
            try:
                argos_pkg.install_from_path(os.path.join(models_dir, fn))
            except Exception:
                pass

def _argos_translate(text: str) -> str:
    """链式 Argos 翻译：ja->en->zh"""
    if not text or not _ARGOS_OK:
        return text
    _install_all_models()
    try:
        mid = argos_trans.translate(text, from_code="ja", to_code="en")
        out  = argos_trans.translate(mid, from_code="en", to_code="zh")
        return out if out else text
    except Exception:
        return text

def _google_webapi_translate(text: str) -> str:
    """无依赖兜底：直接调用 Google Translate Web API（非官方）"""
    if not text or not text.strip():
        return text
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": "ja",
                "tl": "zh-CN",
                "dt": "t",
                "q": text,
            },
            timeout=(4, 10),
        )
        if r.status_code != 200:
            return text
        data = r.json()
        # data[0] -> [[translated, original, ...], ...]
        parts = []
        for seg in (data[0] or []):
            if seg and isinstance(seg, list) and seg[0]:
                parts.append(seg[0])
        out = "".join(parts).strip()
        return out or text
    except Exception:
        return text

# ---------- 主函数 ----------
@lru_cache(maxsize=512)
def translate_text_ja2zh(text: str) -> str:
    if not text or not text.strip():
        return text
    # 优先 googletrans
    if _USE_GT and _gt:
        for attempt in range(2):  # 最多尝试两次
            try:
                res = _gt.translate(text, src="ja", dest="zh-cn")
                if res and res.text:
                    return res.text
            except Exception as e:
                if attempt == 0:
                    time.sleep(1)  # 第一次失败后等 1 秒再试
                else:
                    print("⚠️ googletrans 多次失败，改用 Argos:", e)
    # Fallback 1: Google Web API（避免 googletrans 抽风时直接失效）
    out = _google_webapi_translate(text)
    if out and out != text:
        return out

    # Fallback 2: Argos 离线
    return _argos_translate(text)
