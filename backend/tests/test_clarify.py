"""需求澄清测试。"""

from app.core.clarify import build_question, missing_fields
from app.core.intent import TeachingIntent


def test_missing_fields_standard():
    intent = TeachingIntent(topic="TCP", duration_minutes=45)
    missing = missing_fields(intent, "标准")
    assert "style" in missing
    assert "objectives" in missing
    assert "duration_minutes" not in missing


def test_missing_fields_quick_complete():
    intent = TeachingIntent(topic="TCP", duration_minutes=45, style="学术")
    assert missing_fields(intent, "快速") == []


def test_build_question():
    assert "多长时间" in build_question(["duration_minutes"])
    assert build_question([]) == ""
