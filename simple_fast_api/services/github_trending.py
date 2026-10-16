"""GitHub 일간 Trending 선정, README 기반 소개 및 채팅별 발송 상태 관리."""
import asyncio
import base64
import html
import json
import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from weakref import WeakValueDictionary

import aiohttp
from bs4 import BeautifulSoup
from fastapi import HTTPException

import config
import database
from cache import github_trending_cache, github_summary_cache
from utils import call_gemini

logger = logging.getLogger(__name__)
_locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()


def chat_lock(chat_id: int) -> asyncio.Lock:
    """조회와 발송을 채팅별로 직렬화하는 잠금을 반환합니다."""
    return _locks.setdefault(chat_id, asyncio.Lock())


def now_kst() -> datetime:
    """한국 시간의 현재 시각을 반환합니다."""
    return datetime.now(ZoneInfo(config.TRENDING_TIMEZONE))


def parse_trending(document: str) -> list[dict]:
    """Trending 후보를 당일 스타 증가량 순으로 파싱하고 중복을 제거합니다."""
    projects = {}
    for row in BeautifulSoup(document, 'html.parser').select('article.Box-row'):
        anchor = row.select_one('h2 a')
        name = anchor.get('href', '').strip('/') if anchor else ''
        if not re.fullmatch(r'[\w.-]{1,39}/[\w.-]{1,100}', name, flags=re.ASCII):
            continue
        growth = next((span.get_text(' ', strip=True) for span in row.select('span')
                       if re.search(r'[\d,]+\s+stars? today', span.get_text(' ', strip=True))), '')
        if not growth:
            continue
        stars = row.select_one(f'a[href="/{name}/stargazers"]')
        description = row.select_one('p')
        language = row.select_one('[itemprop="programmingLanguage"]')
        def count(text: str) -> int:
            match = re.search(r'[\d,]+', text)
            return int(match.group().replace(',', '')) if match else 0
        projects[name] = {
            'name': name, 'url': f'{config.GITHUB_WEB_URL}/{name}',
            'stars_today': count(growth), 'stars': count(stars.text) if stars else None,
            'description': description.get_text(' ', strip=True) if description else '',
            'language': language.text.strip() if language else '미표시',
        }
    if not projects:
        raise HTTPException(502, 'GitHub Trending을 읽지 못했습니다. 페이지 구조 또는 접속 상태를 확인하세요.')
    return sorted(projects.values(), key=lambda project: project['stars_today'], reverse=True)


async def fetch_trending() -> list[dict]:
    """실제 GitHub 일간 Trending 페이지에서 후보를 수집합니다."""
    try:
        async with aiohttp.ClientSession(trust_env=True, headers={'User-Agent': config.TRENDING_USER_AGENT},
                                        timeout=aiohttp.ClientTimeout(total=config.TRENDING_HTTP_TIMEOUT)) as session:
            async with session.get(config.GITHUB_TRENDING_URL) as response:
                response.raise_for_status()
                document = await response.text()
        return await asyncio.to_thread(parse_trending, document)
    except (aiohttp.ClientError, asyncio.TimeoutError):
        raise HTTPException(502, 'GitHub Trending 수집에 실패했습니다.') from None


async def fetch_readme(name: str) -> str:
    """저장소의 README를 인증 정보가 포함되지 않은 텍스트로 가져옵니다."""
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': config.TRENDING_USER_AGENT}
    if config.GITHUB_TOKEN:
        headers['Authorization'] = f'Bearer {config.GITHUB_TOKEN}'
    async with aiohttp.ClientSession(trust_env=True, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=config.TRENDING_HTTP_TIMEOUT)) as session:
        async with session.get(f'{config.GITHUB_API_URL}/repos/{name}/readme') as response:
            response.raise_for_status()
            data = await response.json()
    if data.get('encoding') != 'base64':
        raise ValueError('지원하지 않는 README 인코딩')
    return base64.b64decode(data['content']).decode('utf-8', errors='replace')[:config.TRENDING_README_MAX_CHARS]


async def summarize_project(project: dict) -> dict:
    """Gemini로 한국어 소개를 생성하고 실패 시 원문 설명을 명시합니다."""
    warnings = []
    readme = ''
    try:
        readme = await fetch_readme(project['name'])
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
        warnings.append('README를 가져오지 못해 저장소 설명만 사용했습니다.')
    if config.AI_PROVIDER == 'ollama' or config.GEMINI_API_KEY:
        try:
            summary = await call_gemini(json.dumps({'repository': project['name'],
                'description': project['description'], 'readme': readme}, ensure_ascii=False),
                system_instruction=config.TRENDING_SYSTEM_INSTRUCTION)
            if summary.strip() and summary != '(AI 응답 생성 실패)':
                return {**project, 'summary': _clip_utf16(summary, config.TRENDING_SUMMARY_MAX_CHARS),
                        'ai_used': True, 'warnings': warnings}
        except Exception as exc:
            logger.warning('GitHub 소개 생성 실패 (%s)', type(exc).__name__)
    warnings.append('한국어 요약을 사용할 수 없어 원문 설명을 표시합니다.')
    return {**project, 'summary': '원문 소개: ' + (project['description'][:config.TRENDING_DESCRIPTION_MAX_CHARS]
            or '설명 없음. 저장소 README를 확인하세요.'), 'ai_used': False, 'warnings': warnings}


async def get_digest(chat_id: int = 0, now: datetime | None = None) -> dict:
    """채팅별 중복 제외를 적용한 일간 소개를 캐시와 함께 반환합니다."""
    async with chat_lock(chat_id):
        return await build_digest(chat_id, now)


async def build_digest(chat_id: int, now: datetime | None = None) -> dict:
    """호출자가 채팅 잠금을 보유한 상태에서 일간 소개를 구성합니다."""
    now = (now or now_kst()).astimezone(ZoneInfo(config.TRENDING_TIMEZONE))
    day = now.date().isoformat()
    cached = await database.get_trending_edition(chat_id, day)
    if cached is not None:
        return {**cached, 'cached': True}
    cutoff = (now.date() - timedelta(days=config.TRENDING_EXCLUDE_DAYS)).isoformat()
    seen = await database.get_trending_seen(chat_id, cutoff)
    async def load_candidates() -> dict:
        return {'projects': await fetch_trending(), 'collected_at': now.isoformat()}
    snapshot, _ = await github_trending_cache.get_or_create(day, load_candidates)
    candidates = snapshot['projects']
    selected = [project for project in candidates if project['name'] not in seen][:config.TRENDING_COUNT]
    async def shared_summary(project: dict) -> dict:
        async def generate() -> dict:
            return await summarize_project(project)
        key = f"{day}:{project['name']}:{config.AI_PROVIDER}:{config.OLLAMA_MODEL if config.AI_PROVIDER == 'ollama' else config.GEMINI_MODEL}:{bool(config.GEMINI_API_KEY)}"
        card, _ = await github_summary_cache.get_or_create(key, generate)
        return card
    projects = await asyncio.gather(*(shared_summary(project) for project in selected))
    result = {'day': day, 'collected_at': snapshot['collected_at'], 'projects': projects,
              'source': config.GITHUB_TRENDING_URL, 'cached': False}
    if projects:
        await database.save_trending_edition(chat_id, day, result)
    return result


def _clip_utf16(text: str, limit: int) -> str:
    return text.encode('utf-16-le')[:limit * 2].decode('utf-16-le', errors='ignore')


def format_digest(digest: dict) -> str:
    """외부 설명과 AI 출력을 이스케이프한 단일 Telegram HTML 메시지를 만듭니다."""
    stamp = datetime.fromisoformat(digest['collected_at']).strftime('%Y-%m-%d %H:%M KST')
    lines = [f'🔥 <b>GitHub 오늘의 핫 프로젝트</b>\n수집: {stamp}\n'
             f'일간 Trending 후보 · 오늘 스타 증가 순 · 최근 {config.TRENDING_EXCLUDE_DAYS}일 소개 제외']
    for index, project in enumerate(digest['projects'], 1):
        total = f"{project['stars']:,}" if project['stars'] is not None else '미표시'
        lines.append(f"{index}. <b>{html.escape(project['name'])}</b>\n"
                     f"⭐ 오늘 +{project['stars_today']:,} · 누적 {total} · {html.escape(_clip_utf16(project['language'], 40))}\n\n"
                     f"{html.escape(_clip_utf16(project['summary'], config.TRENDING_SUMMARY_MAX_CHARS))}\n" +
                     '\n'.join(html.escape(w) for w in project['warnings']) +
                     f"\n<a href=\"{html.escape(project['url'], quote=True)}\">저장소 보기</a>")
    if not digest['projects']:
        lines.append('최근 7일에 소개하지 않은 새로운 후보가 없습니다.')
    return '\n\n'.join(lines)
