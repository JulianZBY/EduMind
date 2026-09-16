"""LLM JSON 输出容错解析。"""

import json
import re


def parse_json(text: str) -> dict:
    """剥离 markdown 代码块与多余文字，解析 JSON 对象。"""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # LLM 偶发输出格式错误，返回空 dict 让调用方降级，避免整个请求 500
        return {}
