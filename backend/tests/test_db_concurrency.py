"""SQLite 并发配置回归（M2）：WAL + busy_timeout 钉住后台解析与请求线程并发写库。

Rigel 的验证评估（G3）指出：`engine.py` 只设了 `check_same_thread=False`，既没开 WAL
也没给 busy_timeout，后台解析（`pipeline.py` 自建连接）与请求线程并发写同一库存在
`database is locked` 未知风险。本文件把 PRAGMA 与并发写行为钉成回归。
"""

import threading

from app.db import SessionLocal, init_db
from app.db.engine import engine
from app.db.models import Document

init_db()  # 幂等：确保表与默认用户存在（与 test_documents.py 同口径）


def test_sqlite_pragmas_are_set():
    """每条连接都开 WAL 并给 5s busy_timeout（数值是行为契约，不随默认漂移）。"""
    with engine.connect() as conn:
        journal = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
        busy = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
    assert str(journal).lower() == "wal"
    assert int(busy) == 5000


def test_concurrent_writers_do_not_lock():
    """多线程各持连接并发写同一表：不应出现 database is locked。"""
    errors: list[BaseException] = []

    def _write(worker: int) -> None:
        db = SessionLocal()
        try:
            for n in range(5):
                db.add(
                    Document(
                        id=f"concurrent-{worker}-{n}",
                        user_id="default",
                        filename=f"f{worker}-{n}.txt",
                        file_path=f"/tmp/f{worker}-{n}.txt",
                        file_type="txt",
                        status="处理中",
                        is_reference=False,
                    )
                )
                db.commit()
        except BaseException as exc:  # noqa: BLE001 - 收敛任何写库异常用于断言
            errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=_write, args=(i,)) for i in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    db = SessionLocal()
    try:
        rows = db.query(Document).filter(Document.id.like("concurrent-%")).all()
        count = len(rows)
        # 清理：不留「处理中」行给启动清扫类用例造成顺序相关
        for row in rows:
            db.delete(row)
        db.commit()
    finally:
        db.close()
    assert count == 25
