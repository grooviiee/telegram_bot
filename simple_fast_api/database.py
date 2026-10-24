"""
SQLite 기반 사용자 즐겨찾기 저장소.
테이블: favorites (user_id, username, company, analysis_type)
"""

import aiosqlite
import json
from config import DB_PATH, TIMING_MAX_WATCHES


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
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS timing_watches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                company TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                target_price REAL CHECK(target_price > 0),
                revision INTEGER NOT NULL DEFAULT 1,
                last_alert_day TEXT,
                last_checked_at TEXT,
                last_quote_at TEXT,
                last_price REAL,
                last_status TEXT NOT NULL DEFAULT 'waiting',
                UNIQUE(chat_id, stock_code)
            );
            CREATE TABLE IF NOT EXISTS trending_subscriptions (
                chat_id INTEGER PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS trending_editions (
                chat_id INTEGER, day TEXT, payload TEXT NOT NULL,
                PRIMARY KEY(chat_id, day)
            );
            CREATE TABLE IF NOT EXISTS trending_deliveries (
                chat_id INTEGER, day TEXT, PRIMARY KEY(chat_id, day)
            );
            CREATE TABLE IF NOT EXISTS trending_seen (
                chat_id INTEGER, name TEXT, day TEXT NOT NULL,
                PRIMARY KEY(chat_id, name)
            );
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


async def set_trending_subscription(chat_id: int, enabled: bool) -> None:
    """개인 채팅의 GitHub 소개 정기 발송을 신청하거나 해제합니다."""
    async with aiosqlite.connect(DB_PATH) as db:
        if enabled:
            await db.execute("INSERT OR IGNORE INTO trending_subscriptions VALUES (?)", (chat_id,))
        else:
            await db.execute("DELETE FROM trending_subscriptions WHERE chat_id=?", (chat_id,))
        await db.commit()


async def get_trending_subscribers() -> list[int]:
    """GitHub 소개를 신청한 채팅 ID를 반환합니다."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT chat_id FROM trending_subscriptions ORDER BY chat_id")
        return [row[0] for row in await cursor.fetchall()]


async def get_trending_edition(chat_id: int, day: str) -> dict | None:
    """해당 채팅의 당일 소개 캐시를 반환합니다."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT payload FROM trending_editions WHERE chat_id=? AND day=?", (chat_id, day))
        row = await cursor.fetchone()
        return json.loads(row[0]) if row else None


async def save_trending_edition(chat_id: int, day: str, payload: dict) -> None:
    """당일 소개 캐시를 저장합니다."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO trending_editions VALUES (?,?,?)",
                         (chat_id, day, json.dumps(payload, ensure_ascii=False)))
        await db.commit()


async def get_trending_seen(chat_id: int, cutoff: str) -> set[str]:
    """최근 지정 기간에 성공적으로 발송한 저장소를 반환합니다."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT name FROM trending_seen WHERE chat_id=? AND day>=?", (chat_id, cutoff))
        return {row[0] for row in await cursor.fetchall()}


async def trending_was_delivered(chat_id: int, day: str) -> bool:
    """해당 날짜의 소개 발송 성공 여부를 확인합니다."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM trending_deliveries WHERE chat_id=? AND day=?", (chat_id, day))
        return await cursor.fetchone() is not None


async def mark_trending_delivered(chat_id: int, day: str, names: list[str]) -> None:
    """발송 성공 후 일간 발송과 저장소 중복 제외 기록을 함께 저장합니다."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO trending_deliveries VALUES (?,?)", (chat_id, day))
        await db.executemany("INSERT OR REPLACE INTO trending_seen VALUES (?,?,?)",
                             [(chat_id, name, day) for name in names])
        await db.commit()


async def save_timing_watch(chat_id: int, company: str, stock_code: str,
                            target_price: float | None) -> None:
    """관심종목 조건을 저장하고 동일 종목의 당일 발송 기록을 유지합니다."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('BEGIN IMMEDIATE')
        cursor = await db.execute('SELECT stock_code FROM timing_watches WHERE chat_id=?', (chat_id,))
        codes = {row[0] for row in await cursor.fetchall()}
        if stock_code not in codes and len(codes) >= TIMING_MAX_WATCHES:
            raise ValueError(f'관심종목은 최대 {TIMING_MAX_WATCHES}개까지 등록할 수 있습니다.')
        await db.execute("""
            INSERT INTO timing_watches (chat_id, company, stock_code, target_price)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id, stock_code) DO UPDATE SET
                company=excluded.company, target_price=excluded.target_price,
                revision=timing_watches.revision+1, last_checked_at=NULL, last_quote_at=NULL,
                last_price=NULL, last_status='waiting'
            WHERE timing_watches.target_price IS NOT excluded.target_price
                OR timing_watches.company != excluded.company
        """, (chat_id, company, stock_code, target_price))
        await db.commit()


async def get_timing_watches(chat_id: int | None = None) -> list[dict]:
    """개인 채팅 또는 전체의 가격 알림 설정과 마지막 확인 결과를 반환합니다."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = 'SELECT * FROM timing_watches'
        args = () if chat_id is None else (chat_id,)
        if chat_id is not None:
            query += ' WHERE chat_id=?'
        cursor = await db.execute(query + ' ORDER BY id', args)
        return [dict(row) for row in await cursor.fetchall()]


async def remove_timing_watch(chat_id: int, company_or_code: str) -> bool:
    """외부 API 조회 없이 해당 채팅 소유의 관심종목 알림만 해제합니다."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'DELETE FROM timing_watches WHERE chat_id=? AND (company=? OR stock_code=?)',
            (chat_id, company_or_code, company_or_code))
        await db.commit()
        return cursor.rowcount > 0


async def record_timing_check(watch: dict, checked_at: str, price: float | None,
                              status: str, quote_at: str | None = None) -> bool:
    """등록 버전이 같은 경우에만 해당 조건의 가격 확인 결과를 저장합니다."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            UPDATE timing_watches SET last_checked_at=?, last_price=?, last_status=?, last_quote_at=?
            WHERE id=? AND revision=?
        """, (checked_at, price, status, quote_at, watch['id'], watch['revision']))
        await db.commit()
        return cursor.rowcount > 0


async def mark_timing_delivered(watch: dict, day: str) -> None:
    """전송 중 조건이 바뀌어도 같은 구독의 당일 성공 기록을 유지합니다."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE timing_watches SET last_alert_day=?,
                last_status=CASE WHEN revision=? THEN 'sent' ELSE last_status END
            WHERE id=?
        """, (day, watch['revision'], watch['id']))
        await db.commit()
