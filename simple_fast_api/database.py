"""
SQLite 기반 사용자 즐겨찾기 저장소.
테이블: favorites (user_id, username, company, analysis_type)
"""

import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_data.db")


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                username      TEXT,
                company       TEXT NOT NULL,
                analysis_type TEXT NOT NULL,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, company, analysis_type)
            )
        """)
        await db.commit()
    print(f"[DB] 초기화 완료: {DB_PATH}")


async def add_favorite(user_id: int, username: str, company: str, analysis_type: str) -> bool:
    """즐겨찾기 추가. 이미 존재하면 False 반환."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO favorites (user_id, username, company, analysis_type) VALUES (?, ?, ?, ?)",
            (user_id, username, company, analysis_type),
        )
        await db.commit()
        return cursor.rowcount > 0


async def remove_favorite(user_id: int, company: str, analysis_type: str) -> bool:
    """즐겨찾기 삭제. 존재하지 않으면 False 반환."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM favorites WHERE user_id=? AND company=? AND analysis_type=?",
            (user_id, company, analysis_type),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_user_favorites(user_id: int) -> list[dict]:
    """특정 사용자의 즐겨찾기 목록 반환."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT company, analysis_type FROM favorites WHERE user_id=? ORDER BY created_at",
            (user_id,),
        )
        rows = await cursor.fetchall()
    return [{"company": r[0], "analysis_type": r[1]} for r in rows]


async def get_all_favorites_grouped() -> dict[int, list[tuple[str, str]]]:
    """알림 발송용: {user_id: [(company, analysis_type), ...]} 형태로 반환."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id, company, analysis_type FROM favorites ORDER BY user_id, created_at"
        )
        rows = await cursor.fetchall()
    grouped: dict[int, list] = {}
    for user_id, company, analysis_type in rows:
        grouped.setdefault(int(user_id), []).append((company, analysis_type))
    return grouped
