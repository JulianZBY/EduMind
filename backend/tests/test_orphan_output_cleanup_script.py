"""票 03 一次性清理脚本的测试（.scratch/knowledge-restructure/issues/03-orphan-output-cleanup.md）。

脚本不是产品代码、不改行为：这里只测它的保留口径与门禁——
「保留 = 文件名出现在 artifact_versions.filename，或被 session_messages.artifacts 引用；
其余全删；对账不过即拒绝」。用临时库 + 临时目录复刻现场，全程离线确定。
"""


import importlib.util
import json
import sqlite3
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # 先注册进 sys.modules：3.14 的 dataclasses 解析注解时要按 __module__ 回查模块对象
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def orphan_script():
    return _load_script("cleanup_orphan_outputs")


DDL = """
CREATE TABLE artifact_versions (id TEXT PRIMARY KEY, filename TEXT, artifact_type TEXT);
CREATE TABLE session_messages (id TEXT PRIMARY KEY, artifacts TEXT);
"""

KEEP_FILES = [
    "courseware_ppt_a7c136b0.pptx",
    "lesson_plan_4a204a68.docx",
    "outline_ab857b69.docx",
    "courseware_ppt_13dc9c97.pptx",
    "lesson_plan_ccc97a07.docx",
    "outline_2dc6d284.docx",
    "courseware_ppt_9bd11262.pptx",
    "lesson_plan_886ecc49.docx",
    "outline_3549d4ba.docx",
]
MESSAGE_ONLY_REF = "interactive_demo9f2c.html"  # 只被消息 artifacts 引用、不在版本表里
# 盘上存在但谁都不引用（不在版本表、也没被消息提）→ 按口径全是孤儿
ORPHAN_FILES = [
    "courseware_ppt_9bd11262.pptx",
    "lesson_plan_886ecc49.docx",
    "outline_3549d4ba.docx",
    "courseware_ppt_0031b01b.pptx",
    "lesson_plan_deadbeef.docx",
]


def _make_db(path: Path, *, version_filenames: list[str] | None = None, bad_message: bool = False):
    conn = sqlite3.connect(path)
    conn.executescript(DDL)
    for name in version_filenames if version_filenames is not None else KEEP_FILES[:6]:
        conn.execute(
            "INSERT INTO artifact_versions VALUES (?, ?, ?)",
            (f"v-{name}", name, "课件"),
        )
    # 生成回复的 artifacts：既有裸文件名，也有 Windows 路径形态的引用
    artifacts = {
        "ppt": {"filename": KEEP_FILES[0], "path": f"data\\output\\{KEEP_FILES[0]}"},
        "word": {"filename": KEEP_FILES[1]},
        "outline": {"path": f"data\\output\\{KEEP_FILES[2]}"},
        "interactive": {"filename": MESSAGE_ONLY_REF},
    }
    conn.execute(
        "INSERT INTO session_messages VALUES (?, ?)",
        ("m1", json.dumps(artifacts, ensure_ascii=False)),
    )
    # 一条坏 JSON：门禁必须拒绝而不是静默忽略（独立场景开关，干净场景不含）
    if bad_message:
        conn.execute("INSERT INTO session_messages VALUES (?, ?)", ("m2", "{not-json"))
    conn.commit()
    return conn


def _make_output(path: Path, names: list[str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for name in names:
        (path / name).write_bytes(b"artifact-bytes")


@dataclass
class Scene:
    main_db: Path
    output: Path
    main: sqlite3.Connection
    gate: object


@pytest.fixture()
def scene(tmp_path, orphan_script):
    main_db = tmp_path / "edumind.db"
    output = tmp_path / "output"
    _make_db(main_db)
    _make_output(output, [*KEEP_FILES, MESSAGE_ONLY_REF, *ORPHAN_FILES])
    gate = orphan_script.Gate(expected_delete=len(ORPHAN_FILES))
    yield Scene(main_db, output, sqlite3.connect(main_db), gate)


# ---- 计划：保留口径与对账 ----


def test_plan_keeps_versions_and_message_refs_deletes_rest(orphan_script, scene):
    plan = orphan_script.build_plan(scene.main, scene.output)
    assert sorted(p.name for p in plan.keep) == sorted([*KEEP_FILES[:6], MESSAGE_ONLY_REF])
    assert sorted(p.name for p in plan.delete) == sorted(ORPHAN_FILES)
    assert plan.keep_missing == []


def test_gate_blocks_when_version_file_missing_on_disk(orphan_script, scene):
    (scene.output / KEEP_FILES[0]).unlink()
    plan = orphan_script.build_plan(scene.main, scene.output)
    problems = orphan_script.find_gate_problems(plan, scene.gate)
    assert any(KEEP_FILES[0] in p for p in problems)


def test_gate_blocks_on_malformed_artifacts_json(orphan_script, tmp_path):
    main_db = tmp_path / "edumind.db"
    output = tmp_path / "output"
    _make_db(main_db, bad_message=True)
    _make_output(output, [*KEEP_FILES[:6], MESSAGE_ONLY_REF, *ORPHAN_FILES])
    main = sqlite3.connect(main_db)
    plan = orphan_script.build_plan(main, output)
    gate = orphan_script.Gate(expected_delete=len(ORPHAN_FILES))
    problems = orphan_script.find_gate_problems(plan, gate)
    assert any("m2" in p for p in problems)
    main.close()


def test_gate_blocks_on_delete_count_mismatch(orphan_script, scene):
    plan = orphan_script.build_plan(scene.main, scene.output)
    bad_gate = orphan_script.Gate(expected_delete=len(ORPHAN_FILES) + 1)
    problems = orphan_script.find_gate_problems(plan, bad_gate)
    assert any("对不上" in p for p in problems)


def test_gate_blocks_when_keep_below_minimum(orphan_script, scene):
    plan = orphan_script.build_plan(scene.main, scene.output)
    bad_gate = orphan_script.Gate(min_keep=99, expected_delete=len(ORPHAN_FILES))
    problems = orphan_script.find_gate_problems(plan, bad_gate)
    assert any("99" in p for p in problems)


# ---- dry-run：只出清单，不落任何写 ----


def test_dry_run_changes_nothing(orphan_script, scene, capsys):
    code = orphan_script.dry_run(scene.main, scene.output, scene.gate)
    assert code == 0
    assert sorted(p.name for p in scene.output.iterdir()) == sorted(
        {*KEEP_FILES, MESSAGE_ONLY_REF, *ORPHAN_FILES}
    )
    out = capsys.readouterr().out
    assert ORPHAN_FILES[0] in out and KEEP_FILES[0] in out


# ---- 真删：孤儿全清、保留原样、tar 备份可查 ----


def test_execute_deletes_orphans_keeps_referenced_and_tars_backup(orphan_script, scene, tmp_path):
    tar_path = tmp_path / "orphans.tar"
    orphan_script.execute_cleanup(scene.main, scene.output, tar_path, scene.gate)

    assert sorted(p.name for p in scene.output.iterdir()) == sorted(
        [*KEEP_FILES[:6], MESSAGE_ONLY_REF]
    )
    assert tar_path.exists()
    with tarfile.open(tar_path) as tar:
        assert sorted(m.name for m in tar.getmembers()) == sorted(ORPHAN_FILES)


def test_execute_is_idempotent_noop_on_second_run(orphan_script, scene, tmp_path, capsys):
    orphan_script.execute_cleanup(scene.main, scene.output, tmp_path / "a.tar", scene.gate)
    assert (
        orphan_script.execute_cleanup(scene.main, scene.output, tmp_path / "b.tar", scene.gate)
        is None
    )
    assert "无孤儿可删" in capsys.readouterr().out


def test_execute_refuses_when_gate_fails(orphan_script, scene, tmp_path):
    (scene.output / KEEP_FILES[3]).unlink()  # 版本表引用的文件不在盘上
    tar_path = tmp_path / "never.tar"
    with pytest.raises(orphan_script.CleanupRefused):
        orphan_script.execute_cleanup(scene.main, scene.output, tar_path, scene.gate)
    # 拒绝即零副作用：不建 tar、不删任何文件
    assert not tar_path.exists()
    assert sorted(p.name for p in scene.output.iterdir()) == sorted(
        {*KEEP_FILES, MESSAGE_ONLY_REF, *ORPHAN_FILES} - {KEEP_FILES[3]}
    )
