#!/usr/bin/env python3
"""一次性清理脚本：data/output 历史孤儿文件清理（票 03，.scratch/knowledge-restructure/issues/03-orphan-output-cleanup.md）。

教师已批准（2026-10-08）。默认 **dry-run**：只打印保留清单与删除清单，不落任何写；
真删必须显式加 `--execute`。

保留口径（票面原文）：
- **保留**：文件名出现在 `artifact_versions.filename`，或被 `session_messages.artifacts`
  （JSON 文本列）引用——引用判定 = 遍历该 JSON 的全部字符串值，按 `\\`/`/` 分隔取末段，
  命中 output 目录现存文件名即算引用（覆盖裸文件名与 `data\\output\\x.pptx` 路径两种形态）；
- **删除**：其余全部。

门禁（对账不过 → 拒绝，零副作用）：
- `artifact_versions` 每一行的 filename 必须真实存在于 output 目录且落在保留侧；
- 保留数 ≥ 6（票面预期）；删除数 == 3366（票面预期 ~3366 的现场核实值，2026-10-08 实测
  3375 个文件 − 9 个保留）；
- `session_messages.artifacts` 出现解析不了的 JSON → 拒绝（不静默忽略）。

真删前把删除清单打包为 tar（默认 `/tmp/edumind-output-orphans-<时间戳>.tar`，在 data/ 之外），
打包后校验成员数与删除清单一致才开删。运行（backend 目录下）：
`uv run python scripts/cleanup_orphan_outputs.py`          # dry-run
`uv run python scripts/cleanup_orphan_outputs.py --execute`  # 真删
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
MAIN_DB = BASE_DIR / "edumind.db"
OUTPUT_DIR = BASE_DIR / "data" / "output"

# 票面（2026-10-08）预期：保留 ≥ 6（与 artifact_versions 对账），删除 ~3366
# （现场核实：output 3375 个文件，artifact_versions 9 行，3375 - 9 = 3366）。
MIN_KEEP = 6
EXPECTED_DELETE = 3366


@dataclass
class Gate:
    """门禁期望值：生产用模块常量作默认；测试场景可注入自己的对账基准。"""

    min_keep: int = MIN_KEEP
    expected_delete: int = EXPECTED_DELETE


class CleanupRefused(RuntimeError):
    """门禁不过，拒绝执行（零副作用）。"""


@dataclass
class Plan:
    keep: list[Path] = field(default_factory=list)
    delete: list[Path] = field(default_factory=list)
    keep_missing: list[str] = field(default_factory=list)  # 版本/消息引用了但盘上没有
    unexpected: list[Path] = field(default_factory=list)  # 目录里的非普通文件条目
    bad_messages: list[str] = field(default_factory=list)  # artifacts JSON 解析失败的消息 id
    version_filenames: list[str] = field(default_factory=list)
    message_referenced: list[str] = field(default_factory=list)


def _basename(any_path: str) -> str:
    """兼容 Windows 反斜杠路径与裸文件名：统一按 \\/ 分隔取末段。"""
    return any_path.replace("\\", "/").rsplit("/", 1)[-1]


def _collect_strings(node, out: list[str]) -> None:
    if isinstance(node, dict):
        for value in node.values():
            _collect_strings(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_strings(value, out)
    elif isinstance(node, str):
        out.append(node)


def build_plan(main: sqlite3.Connection, output_dir: Path) -> Plan:
    """只读地算出「保留 / 删除」两份清单。"""
    plan = Plan()
    plan.version_filenames = [
        row[0] for row in main.execute("SELECT filename FROM artifact_versions ORDER BY filename")
    ]
    on_disk: dict[str, Path] = {}
    if output_dir.is_dir():
        for entry in sorted(output_dir.iterdir()):
            if entry.is_file():
                on_disk[entry.name] = entry
            else:
                plan.unexpected.append(entry)

    referenced: set[str] = set(plan.version_filenames)
    for msg_id, raw in main.execute(
        "SELECT id, artifacts FROM session_messages WHERE artifacts IS NOT NULL"
    ):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            plan.bad_messages.append(str(msg_id))
            continue
        strings: list[str] = []
        _collect_strings(parsed, strings)
        for value in strings:
            name = _basename(value)
            if name in on_disk:
                referenced.add(name)
    plan.message_referenced = sorted(referenced.difference(plan.version_filenames))

    for name in sorted(referenced):
        if name in on_disk:
            plan.keep.append(on_disk[name])
        else:
            plan.keep_missing.append(name)
    plan.delete = [path for name, path in on_disk.items() if name not in referenced]
    return plan


def find_gate_problems(plan: Plan, gate: Gate) -> list[str]:
    problems: list[str] = []
    for name in plan.version_filenames:
        if name not in {p.name for p in plan.keep}:
            problems.append(f"artifact_versions 引用的 {name} 不在保留侧（盘上缺失？）,拒绝执行")
    for name in plan.keep_missing:
        problems.append(f"保留口径引用的 {name} 在 output 目录不存在（可能早已缺失）,请人工核对")
    for entry in plan.unexpected:
        problems.append(f"output 目录出现非文件条目 {entry.name},不在票面口径内")
    for msg_id in plan.bad_messages:
        problems.append(f"session_messages {msg_id} 的 artifacts JSON 解析失败,拒绝静默忽略")
    if len(plan.keep) < gate.min_keep:
        problems.append(f"保留数 {len(plan.keep)} < 票面预期 ≥ {gate.min_keep},对不上")
    if plan.delete and len(plan.delete) != gate.expected_delete:
        # 删除集为空（清理后的复跑）时不做数量对账：无事可删即无事可对，由 no-op 分支接管
        problems.append(
            f"删除数 {len(plan.delete)} != 票面预期 {gate.expected_delete}"
            f"（output 总数 {len(plan.keep) + len(plan.delete) + len(plan.unexpected)}）,对不上"
        )
    return problems


def print_plan(plan: Plan) -> None:
    print("== 保留清单（dry-run）==")
    for path in plan.keep:
        print(f"  {path.name}")
    print(
        f"（artifact_versions 引用 {len(plan.version_filenames)} 个;"
        f"消息 artifacts 额外引用 {len(plan.message_referenced)} 个:"
        f"{', '.join(plan.message_referenced) or '无'}）"
    )
    print(f"== 删除清单（dry-run，共 {len(plan.delete)} 个）==")
    for path in plan.delete:
        print(f"  {path.name}")
    if plan.keep_missing or plan.unexpected or plan.bad_messages:
        print("== 需人工核对的条目 ==")
        for name in plan.keep_missing:
            print(f"  保留引用缺失: {name}")
        for entry in plan.unexpected:
            print(f"  非文件条目: {entry.name}")
        for msg_id in plan.bad_messages:
            print(f"  artifacts JSON 解析失败: session_messages {msg_id}")


def dry_run(main: sqlite3.Connection, output_dir: Path, gate: Gate | None = None) -> int:
    plan = build_plan(main, output_dir)
    print_plan(plan)
    problems = find_gate_problems(plan, gate or Gate())
    if problems:
        print("\n== 门禁不过（停在报告，不删）==")
        for p in problems:
            print(f"  ✗ {p}")
        return 2
    print("\n门禁通过：保留/删除与票面口径逐项相符。加 --execute 真删。")
    return 0


def make_tar(delete: list[Path], tar_path: Path) -> None:
    """把删除清单原样打包到 data/ 之外；打包后校验成员数与清单一致。"""
    tar_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "w") as tar:
        for path in delete:
            tar.add(path, arcname=path.name)
    with tarfile.open(tar_path) as tar:
        members = tar.getnames()
    if len(members) != len(delete):
        raise RuntimeError(f"tar 成员数 {len(members)} != 删除清单 {len(delete)}，中止")
    print(f"备份完成：{tar_path}（{len(members)} 个文件）")


def execute_cleanup(
    main: sqlite3.Connection, output_dir: Path, tar_path: Path, gate: Gate | None = None
) -> None:
    plan = build_plan(main, output_dir)
    problems = find_gate_problems(plan, gate or Gate())
    if problems:
        detail = "\n".join(f"  ✗ {p}" for p in problems)
        raise CleanupRefused(f"门禁不过，拒绝执行（零副作用）：\n{detail}")
    if not plan.delete:
        print("无孤儿可删：output 目录全部文件都在保留侧，无事可做。")
        return

    make_tar(plan.delete, tar_path)
    for path in plan.delete:
        path.unlink()

    # 删后自证：保留侧分毫不动、删除侧全部离场
    remaining = {p.name for p in output_dir.iterdir()}
    if remaining != {p.name for p in plan.keep}:
        raise RuntimeError(
            f"删除后自证失败：剩余 {len(remaining)} 个 != 保留 {len(plan.keep)} 个。"
            f"请从备份恢复：{tar_path}"
        )
    print(f"删除完成，删后自证通过：剩 {len(remaining)} 个保留文件，孤儿全清。")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="票 03：data/output 孤儿文件清理（默认 dry-run）")
    parser.add_argument("--execute", action="store_true", help="真删（默认只 dry-run）")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="显式声明 dry-run（默认即 dry-run，此旗标不改变行为，便于脚本化留痕）",
    )
    parser.add_argument(
        "--tar-path",
        type=Path,
        default=None,
        help="删除清单备份 tar 的落点（默认 /tmp/edumind-output-orphans-<时间戳>.tar）",
    )
    args = parser.parse_args(argv)

    print(f"主库：{MAIN_DB}")
    print(f"生成物目录：{OUTPUT_DIR}")
    main_conn = sqlite3.connect(f"file:{MAIN_DB}?mode=ro", uri=True)
    try:
        if not args.execute:
            return dry_run(main_conn, OUTPUT_DIR)
        tar_target = args.tar_path or Path(
            "/tmp", f"edumind-output-orphans-{time.strftime('%Y%m%d-%H%M%S')}.tar"
        )
        execute_cleanup(main_conn, OUTPUT_DIR, tar_target)
        return 0
    finally:
        main_conn.close()


if __name__ == "__main__":
    sys.exit(main())
