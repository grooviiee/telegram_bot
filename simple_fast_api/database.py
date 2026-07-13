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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS filing_watch (
                corp_code    TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                last_rcept_no TEXT,
                last_rcept_dt TEXT,
                updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS search_stats (
                company          TEXT PRIMARY KEY,
                search_count     INTEGER NOT NULL DEFAULT 0,
                last_searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
    print(f"[DB] 초기화 완료: {DB_PATH}")


async def record_search(company: str) -> None:
    """종목 검색 횟수를 1 증가시킵니다 (인기 종목 캐시 워밍업에 사용)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO search_stats (company, search_count, last_searched_at)
            VALUES (?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(company) DO UPDATE SET
                search_count     = search_count + 1,
                last_searched_at = CURRENT_TIMESTAMP
            """,
            (company,),
        )
        await db.commit()


async def get_top_searched_companies(limit: int = 20) -> list[str]:
    """검색 횟수 상위 N개 종목명을 반환합니다."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT company FROM search_stats ORDER BY search_count DESC, last_searched_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [r[0] for r in rows]


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


async def get_all_watched_companies() -> list[dict]:
    """즐겨찾기에 등록된 고유 종목 목록 반환 (공시 감지용)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT company FROM favorites ORDER BY company"
        )
        rows = await cursor.fetchall()
    return [{"company": r[0]} for r in rows]


async def get_users_watching_company(company_name: str) -> list[int]:
    """특정 종목을 즐겨찾기한 모든 user_id 반환."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT user_id FROM favorites WHERE company=?",
            (company_name,),
        )
        rows = await cursor.fetchall()
    return [r[0] for r in rows]


async def get_filing_watch(corp_code: str) -> dict | None:
    """종목의 마지막 공시 정보 반환."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT corp_code, company_name, last_rcept_no, last_rcept_dt FROM filing_watch WHERE corp_code=?",
            (corp_code,),
        )
        row = await cursor.fetchone()
    if not row:
        return None
    return {"corp_code": row[0], "company_name": row[1], "last_rcept_no": row[2], "last_rcept_dt": row[3]}


async def update_filing_watch(corp_code: str, company_name: str, last_rcept_no: str, last_rcept_dt: str) -> None:
    """종목의 마지막 공시 정보 갱신 (없으면 삽입)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO filing_watch (corp_code, company_name, last_rcept_no, last_rcept_dt, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(corp_code) DO UPDATE SET
                last_rcept_no = excluded.last_rcept_no,
                last_rcept_dt = excluded.last_rcept_dt,
                updated_at    = CURRENT_TIMESTAMP
            """,
            (corp_code, company_name, last_rcept_no, last_rcept_dt),
        )
        await db.commit()


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
