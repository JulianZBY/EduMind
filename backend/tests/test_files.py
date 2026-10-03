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


def test_download_uses_generation_output_directory(isolated_output_dir):
    from pathlib import Path

    from app.generate.creative import save_html

    html = "<html><body>一次函数</body></html>"
    filename = Path(save_html(html)).name
    response = client.get(f"/api/v1/files/{filename}?inline=true")
    assert response.status_code == 200
    assert response.content == html.encode("utf-8")
    assert response.headers["content-type"].startswith("text/html")
    assert "attachment" not in response.headers.get("content-disposition", "")
