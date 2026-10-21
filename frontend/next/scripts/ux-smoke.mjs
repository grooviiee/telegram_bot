import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

// 실행 중인 웹에 연결합니다. 외부 공시·AI 호출은 고정 응답으로 대체합니다.
const base = process.env.UX_BASE_URL ?? 'http://127.0.0.1:3000';
const api = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const browser = await chromium.launch({ headless: true });
const errors = [];
const counts = new Map();
let reportFails = true;
let quarterFails = true;
let malformedValuation = false;
let delayFinancials = false;
let releaseFinancials;
let longAnswer = false;
const financials = [{ year: 2025, fs_div: 'CFS', revenue: 300e12, operating_income: 30e12,
  operating_margin: 10, roe: 12, net_income: 20e12, eps: 3000, debt_ratio: 35,
  current_ratio: 200, fcf: 10e12 }];

async function prepare(context, favorites) {
  await context.addInitScript((stored) => localStorage.setItem('dart_favorites', stored), favorites);
  await context.route(`${api}/**`, async (route) => {
    const url = new URL(route.request().url());
    const [endpoint, encoded] = url.pathname.slice(1).split('/');
    const company_name = decodeURIComponent(encoded ?? '');
    counts.set(endpoint, (counts.get(endpoint) ?? 0) + 1);
    if (endpoint === 'financials' && delayFinancials) {
      delayFinancials = false;
      await new Promise((resolve) => { releaseFinancials = resolve; });
    }
    if (endpoint === 'valuation' && malformedValuation) {
      malformedValuation = false;
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{broken' });
      return;
    }
    let status = 200;
    let body;
    if (endpoint === 'report' && reportFails) {
      reportFails = false;
      status = 503;
      body = { detail: '리포트를 불러오지 못했습니다.' };
    } else if (endpoint === 'financials-quarterly' && quarterFails) {
      quarterFails = false;
      status = 503;
      body = { detail: '분기 데이터를 불러오지 못했습니다.' };
    } else if (company_name === '없는회사') {
      status = 404;
      body = { detail: '해당 기업을 찾을 수 없습니다.' };
    } else {
      const fixtures = {
        financials: { financials },
        'financials-quarterly': { financials: financials.map((row) => ({ ...row, quarter: 'Q1', label: '2025 Q1' })) },
        'dividend-data': { dividend_data: [{ year: 2025, dividend: 1500 }] },
        'dividend-data-quarterly': { dividend_data: [{ year: 2025, dividend: 375, label: '2025 Q1' }] },
        valuation: { stock_code: '005930', price: 60000, shares: 100, market_cap: 300e12,
          per: 10, pbr: 1, psr: 1, ev_ebit: 10, latest_year: 2025, history: [] },
        report: { report: '## 기업 분석\n공시 근거를 확인하세요.' },
        chat: { answer: longAnswer ? '긴 공시 설명입니다.\n'.repeat(100) : '영업이익률은 10%입니다.' },
      };
      assert.ok(endpoint in fixtures, `Unexpected API request: ${endpoint}`);
      body = { company_name, ...fixtures[endpoint] };
    }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  });
  const page = await context.newPage();
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(base);
  return page;
}

async function visible(locator) { await locator.waitFor({ state: 'visible' }); }
async function menu(page, name) { await page.getByRole('navigation', { name: '분석 메뉴' }).getByRole('button', { name, exact: true }).click(); }
async function noOverflow(page) {
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Page has horizontal overflow');
}

try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await prepare(context, JSON.stringify([{ company: '삼성전자', page: 'analysis' }, { bad: true }]));
  const input = () => page.getByRole('searchbox', { name: '기업명' });
  assert.equal(await page.locator('html').getAttribute('lang'), 'ko');
  assert.equal(await page.getByRole('button', { name: '조회', exact: true }).isDisabled(), true);
  await page.getByRole('button', { name: '즐겨찾기 1' }).click();
  await page.getByRole('button', { name: '종합 분석', exact: true }).last().click();
  await visible(page.getByText('연결 재무제표', { exact: false }));
  assert.equal(await input().inputValue(), '삼성전자');
  assert.equal(await page.getByRole('button', { name: '삼성전자 즐겨찾기 해제' }).getAttribute('aria-pressed'), 'true');
  await menu(page, '밸류에이션');
  await visible(page.getByText('2025년 재무 기준'));
  assert.equal(await input().inputValue(), '삼성전자');
  await page.getByRole('button', { name: '삼성전자 즐겨찾기 추가' }).click();
  await menu(page, 'AI 리포트');
  assert.equal(await input().inputValue(), '삼성전자');
  assert.equal(counts.get('report') ?? 0, 0, 'AI report must require an explicit request');
  await page.getByRole('button', { name: '리포트 생성', exact: true }).click();
  await visible(page.getByRole('alert').filter({ hasText: '오류:' }));
  await page.getByRole('button', { name: '다시 시도' }).click();
  await visible(page.getByRole('heading', { name: '기업 분석', exact: true }));
  assert.equal(counts.get('report'), 2);
  await menu(page, '수익성 & 성장성');
  await visible(page.getByRole('button', { name: '삼성전자 즐겨찾기 추가' }));
  await page.getByRole('button', { name: '분기별', exact: true }).click();
  await visible(page.getByRole('alert').filter({ hasText: '오류:' }));
  await page.getByRole('button', { name: '다시 시도' }).click();
  await visible(page.getByRole('status').filter({ hasText: '데이터 조회 완료' }));
  assert.equal(await page.getByRole('button', { name: '분기별', exact: true }).getAttribute('aria-pressed'), 'true');
  assert.equal(counts.get('financials-quarterly'), 2);
  await input().fill('없는회사');
  await input().press('Enter');
  await visible(page.getByRole('alert').filter({ hasText: '오류:' }));
  assert.equal(await page.getByRole('button', { name: /없는회사 즐겨찾기/ }).count(), 0);
  await input().fill('SK하이닉스');
  await input().press('Enter');
  await visible(page.getByRole('button', { name: 'SK하이닉스 즐겨찾기 추가' }));
  // 화면을 떠난 뒤 도착한 이전 기업 응답이 현재 선택을 바꾸지 않아야 합니다.
  delayFinancials = true;
  const delayedRequest = page.waitForRequest((request) => request.url().includes('/financials/') && decodeURI(request.url()).endsWith('삼성전자'));
  await input().fill('삼성전자');
  await input().press('Enter');
  await delayedRequest;
  await menu(page, '밸류에이션');
  releaseFinancials();
  await visible(page.getByText('2025년 재무 기준'));
  assert.equal(await input().inputValue(), 'SK하이닉스');
  malformedValuation = true;
  await page.getByRole('button', { name: '조회', exact: true }).click();
  await visible(page.getByRole('alert').filter({ hasText: '서버 응답을 읽지 못했습니다.' }));
  await page.getByRole('button', { name: '다시 시도' }).click();
  await visible(page.getByText('2025년 재무 기준'));
  await menu(page, 'AI 상담');
  await visible(page.getByText('SK하이닉스의 DART 공시 데이터를 불러왔습니다.', { exact: false }));
  await page.getByRole('button', { name: '최근 매출과 영업이익 추세를 알려줘' }).click();
  await visible(page.getByText('영업이익률은 10%입니다.', { exact: true }));
  longAnswer = true;
  await page.getByRole('textbox', { name: '상담 질문' }).fill('자세히 설명해줘');
  await page.getByRole('button', { name: '전송', exact: true }).click();
  await visible(page.getByText('긴 공시 설명입니다.', { exact: false }));
  const composer = await page.getByRole('textbox', { name: '상담 질문' }).boundingBox();
  assert.ok(composer && composer.y >= 0 && composer.y + composer.height <= 900, 'Long chat pushes the question input outside the viewport');
  await mkdir('ux-artifacts', { recursive: true });
  await page.screenshot({ path: 'ux-artifacts/desktop.png', fullPage: true });
  await context.close();

  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const phone = await prepare(mobile, '{broken-json');
  await noOverflow(phone);
  await phone.getByRole('button', { name: '즐겨찾기', exact: true }).click();
  await visible(phone.getByText('아직 즐겨찾기가 없습니다.'));
  await phone.getByRole('button', { name: '기업 분석 시작하기' }).click();
  for (const name of ['사업 분석', '배당 분석', '수익성 & 성장성', '재무 건전성', '밸류에이션', '버핏 리포트', 'AI 리포트', 'AI 상담', '주가 이벤트', '종합 분석']) {
    await menu(phone, name);
    await visible(phone.getByRole('searchbox', { name: '기업명' }));
    await noOverflow(phone);
  }
  await phone.getByRole('button', { name: '삼성전자', exact: true }).click();
  await visible(phone.getByText('연결 재무제표', { exact: false }));
  await noOverflow(phone);
  await phone.screenshot({ path: 'ux-artifacts/mobile.png', fullPage: true });
  await mobile.close();
  const direct = await browser.newContext();
  const routed = await prepare(direct, '[]');
  await routed.goto(`${base}/valuation`);
  await visible(routed.getByRole('heading', { name: '밸류에이션', exact: true }));
  await direct.close();
  assert.deepEqual(errors, [], 'Browser runtime errors');
  console.log('PASS: company handoff, legacy favorites, explicit AI generation, retry, quarterly errors, 404 recovery, stale requests, malformed JSON, long chat, direct routes, all mobile menus and overflow');
} finally {
  await browser.close();
}
