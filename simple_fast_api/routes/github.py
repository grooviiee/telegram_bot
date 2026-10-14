"""GitHub Trending 소개의 전송 없는 미리보기 API."""
from fastapi import APIRouter
from services.github_trending import get_digest

router = APIRouter(tags=['GitHub'])


@router.get('/github/trending')
async def preview_trending() -> dict:
    """Telegram 전송 없이 공용 일간 소개와 캐시 여부를 반환합니다."""
    return await get_digest()
