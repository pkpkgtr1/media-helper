"""可选的日→中翻译。没装翻译库就返回原文，绝不让抓取因此失败。

保留这一层是因为站点面板偶尔已经给出中文，只有缺失时才值得付出一次
离线翻译的代价；翻译库（argostranslate + 语言包）属于可选依赖。
"""
from __future__ import annotations

_CACHE = {}
_MAX_CACHE = 2000


def available():
    try:
        import argostranslate.translate  # noqa: F401
    except Exception:
        return False
    return True


def _translate(text):
    import argostranslate.translate as argos

    installed = argos.get_installed_languages()
    source = next((lang for lang in installed if lang.code == "ja"), None)
    target = next((lang for lang in installed if lang.code == "zh"), None)
    if not source or not target:
        return ""
    return source.get_translation(target).translate(text)


def translate_text_ja2zh(text):
    """把日文翻成中文；任何异常都退回原文。"""
    source = (text or "").strip()
    if not source:
        return ""
    if source in _CACHE:
        return _CACHE[source]
    try:
        result = _translate(source)
    except Exception:
        return source
    if not result:
        return source
    if len(_CACHE) >= _MAX_CACHE:
        _CACHE.clear()
    _CACHE[source] = result
    return result
