// REPL driver for the frontend/next web app, using Playwright chromium directly
// (chromium-cli is not available in this environment; this is the fallback
// described in the run-skill-generator's playwright.md).
//
// Assumes the Next.js dev server is already running at DEV_URL (default
// http://localhost:3000). Run under plain node — no xvfb needed, Chromium
// runs headless.
import { chromium } from 'playwright';
import * as readline from 'node:readline';
import * as fs from 'node:fs';
import * as path from 'node:path';

const DEV_URL = process.env.DEV_URL || 'http://localhost:3000';
const SHOT_DIR = process.env.SCREENSHOT_DIR || '/tmp/shots';
fs.mkdirSync(SHOT_DIR, { recursive: true });

let browser = null;
let page = null;

const COMMANDS = {
  async launch() {
    if (browser) return console.log('already launched');
    browser = await chromium.launch({ args: ['--no-sandbox'] });
    const context = await browser.newContext();
    page = await context.newPage();
    page.on('console', msg => { if (msg.type() === 'error') COMMANDS.consoleErrors.push(msg.text()); });
    page.on('pageerror', err => COMMANDS.consoleErrors.push(String(err)));
    console.log('launched.');
  },

  async nav(url) {
    if (!page) return console.log('ERROR: launch first');
    const target = url?.startsWith('http') ? url : `${DEV_URL}${url || '/'}`;
    await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 30_000 });
    console.log('nav →', target);
  },

  async ss(name) {
    if (!page) return console.log('ERROR: launch first');
    const f = path.join(SHOT_DIR, (name || `ss-${Date.now()}`) + '.png');
    await page.screenshot({ path: f });
    console.log('screenshot:', f);
  },

  async click(sel) {
    if (!page) return console.log('ERROR: launch first');
    try { await page.click(sel, { timeout: 10_000 }); console.log('click', sel, '→ OK'); }
    catch (e) { console.log('click', sel, '→ ERROR:', e.message); }
  },

  async 'click-text'(text) {
    if (!page) return console.log('ERROR: launch first');
    try { await page.getByText(text, { exact: false }).first().click({ timeout: 10_000 }); console.log('click-text', JSON.stringify(text), '→ OK'); }
    catch (e) { console.log('click-text', JSON.stringify(text), '→ ERROR:', e.message); }
  },

  async fill(args) {
    if (!page) return console.log('ERROR: launch first');
    const sp = args.indexOf(' ');
    const sel = args.slice(0, sp);
    const value = args.slice(sp + 1);
    try { await page.fill(sel, value, { timeout: 10_000 }); console.log('fill', sel, '→ OK'); }
    catch (e) { console.log('fill', sel, '→ ERROR:', e.message); }
  },

  async press(key) { if (page) await page.keyboard.press(key); },

  async wait(sel) {
    if (!page) return console.log('ERROR: launch first');
    try { await page.waitForSelector(sel, { timeout: 10_000 }); console.log('found:', sel); }
    catch { console.log('TIMEOUT:', sel); }
  },

  async 'wait-for-text'(text) {
    if (!page) return console.log('ERROR: launch first');
    try { await page.getByText(text, { exact: false }).first().waitFor({ timeout: 10_000 }); console.log('found text:', text); }
    catch { console.log('TIMEOUT waiting for text:', text); }
  },

  async text(sel) {
    if (!page) return console.log('ERROR: launch first');
    console.log(await page.evaluate(
      s => (s ? document.querySelector(s) : document.body)?.innerText ?? '(null)',
      sel || null));
  },

  async eval(expr) {
    if (!page) return console.log('ERROR: launch first');
    try { console.log(JSON.stringify(await page.evaluate(expr))); }
    catch (e) { console.log('ERROR:', e.message); }
  },

  consoleErrors: [],
  async 'console'(mode) {
    if (mode === '--errors') {
      console.log(COMMANDS.consoleErrors.length ? COMMANDS.consoleErrors.join('\n') : '(no console errors captured)');
    }
  },

  async quit() { if (browser) await browser.close().catch(() => {}); browser = null; page = null; },
  help() { console.log('commands:', Object.keys(COMMANDS).filter(k => typeof COMMANDS[k] === 'function').join(', ')); },
};

const stdin = fs.createReadStream(null, { fd: fs.openSync('/dev/stdin', 'r') });
const rl = readline.createInterface({ input: stdin, output: process.stdout, prompt: 'driver> ' });

// Piped input (heredoc) delivers every line before async handlers finish —
// readline does not wait for a 'line' listener's promise before emitting the
// next one. Queue commands so each fully completes before the next starts.
let queue = Promise.resolve();

rl.on('line', line => {
  queue = queue.then(async () => {
    const [cmd, ...rest] = line.trim().split(/\s+/);
    if (!cmd) return;
    const fn = COMMANDS[cmd];
    if (typeof fn !== 'function') { console.log('unknown:', cmd, '— try: help'); return; }
    try { await fn(rest.join(' ')); } catch (e) { console.log('ERROR:', e.message); }
    if (cmd === 'quit') { rl.close(); process.exit(0); }
    rl.prompt();
  });
});
// Wait for any still-queued commands to finish before tearing down — 'close'
// fires as soon as piped/redirected stdin hits EOF, which is often before
// the queued async commands (e.g. a slow 'launch') have actually run.
rl.on('close', async () => { await queue; await COMMANDS.quit(); process.exit(0); });

console.log('frontend/next driver — "help" for commands, "launch" to start');
rl.prompt();
