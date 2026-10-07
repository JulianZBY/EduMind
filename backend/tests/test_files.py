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


def _write_output(name: str, content: bytes) -> None:
    from app.generate import output_dir

    target = output_dir()
    target.mkdir(parents=True, exist_ok=True)
    (target / name).write_bytes(content)


def test_interactive_html_is_served_isolated_from_the_app_origin():
    """互动内容是模型生成的带脚本页面：必须带 sandbox 且不含 allow-same-origin。

    否则它与应用同源，脚本可以调用本应用的全部接口（接口没有认证）。
    下载与内联打开两种取法都要带。
    """
    _write_output("creative_isolation.html", b"<!doctype html><script>1</script>")

    for inline in ("false", "true"):
        r = client.get("/api/v1/files/creative_isolation.html", params={"inline": inline})
        assert r.status_code == 200
        csp = r.headers["content-security-policy"]
        assert csp.startswith("sandbox")
        assert "allow-scripts" in csp  # 小游戏要能跑
        assert "allow-same-origin" not in csp  # 但不能拿到应用的源
        assert r.headers["x-content-type-options"] == "nosniff"


def test_non_html_artifacts_are_served_without_sandbox():
    _write_output("courseware_plain.pptx", b"PK\x03\x04")

    r = client.get("/api/v1/files/courseware_plain.pptx")

    assert r.status_code == 200
    assert "content-security-policy" not in r.headers
