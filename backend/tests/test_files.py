"""课件下载接口测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_download_missing():
    r = client.get("/api/v1/files/notfound.pptx")
    assert r.status_code == 404


def test_download_illegal_name():
    r = client.get("/api/v1/files/a..b.pptx")
    assert r.status_code == 400
