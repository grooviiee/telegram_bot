"""FastAPI 애플리케이션 엔트리포인트."""
import os
import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from config import DART_API_KEY, GEMINI_API_KEY, TELEGRAM_BOT_TOKEN
import database
import bot as telegram_bot
from routes.data import router as data_router
from routes.ai import router as ai_router
from routes.legacy import router as legacy_router
from routes.system import router as system_router

# --- 환경 변수 검증 ---
if not DART_API_KEY:
    raise ValueError("DART_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")

# --- Telegram 봇 & 스케줄러 ---
bot_app = telegram_bot.create_bot_application() if TELEGRAM_BOT_TOKEN else None
scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


# --- Lifespan ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await database.init_db()
    app.state.bot_app = bot_app  # system 라우트에서 참조

    if bot_app:
        await bot_app.initialize()
        try:
            await bot_app.bot.delete_webhook(drop_pending_updates=True)
        except Exception:
            pass
        await bot_app.start()
        await bot_app.updater.start_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )
        print("[Bot] Polling 모드로 시작됨")

        scheduler.add_job(
            telegram_bot.send_daily_notification,
            CronTrigger(hour=9, minute=0),
            args=[bot_app.bot],
            id="daily_notification",
            replace_existing=True,
        )
        scheduler.add_job(
            telegram_bot.send_filing_alerts,
            "interval",
            minutes=30,
            args=[bot_app.bot],
            id="filing_alerts",
            replace_existing=True,
        )
        scheduler.start()
        print("[Scheduler] 일일 알림 (09:00 KST) + 공시 감지 (30분) 등록 완료")
    else:
        print("[Bot] TELEGRAM_BOT_TOKEN 미설정 — 봇 기능 비활성화")

    yield

    # Shutdown
    if scheduler.running:
        scheduler.shutdown(wait=False)
    if bot_app:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
        print("[Bot] 봇 종료")
    await telegram_bot.close_session()


# --- FastAPI 앱 ---

app = FastAPI(
    title="DART Report Analyzer with Gemini",
    description="DART 보고서 다운로드, 배당금 분석, AI 투자 리포트 생성",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 라우터 등록 ---
app.include_router(data_router)
app.include_router(ai_router)
app.include_router(legacy_router)
app.include_router(system_router)

# --- Matplotlib 한글 폰트 ---
font_path = None
if os.name == 'posix':
    font_paths = fm.findSystemFonts(fontpaths=None, fontext='ttf')
    nanum_paths = [p for p in font_paths if 'NanumGothic' in p]
    if nanum_paths:
        font_path = nanum_paths[0]
elif os.name == 'nt':
    font_path = 'c:/Windows/Fonts/malgun.ttf'

if font_path and os.path.exists(font_path):
    font_name = fm.FontProperties(fname=font_path).get_name()
    plt.rc('font', family=font_name)
    plt.rc('axes', unicode_minus=False)
    print(f"Matplotlib 한글 폰트가 '{font_name}'으로 설정되었습니다.")
else:
    print("경고: 한글 폰트를 찾을 수 없습니다.")


# --- 서버 실행 ---
if __name__ == "__main__":
    print("서버를 시작합니다. http://127.0.0.1:8000/docs 에서 API 문서를 확인하세요.")
    uvicorn.run(app, host="127.0.0.1", port=8000)
