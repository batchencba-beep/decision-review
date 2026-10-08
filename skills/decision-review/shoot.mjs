#!/usr/bin/env node
// Screenshot one element of a page, as it is or with a proposed CSS change applied.
// No dependencies: drives the Chrome you already have over the DevTools protocol.
//
//   node shoot.mjs <url> <out.png> [options]
//
//   --selector ".nav"     crop to this element (default: the viewport)
//   --css "..."           CSS injected before the shot, to render the proposed version
//   --width 1440          viewport width  (default 1440; use 390 for mobile)
//   --height 900          viewport height (default 900)
//   --scale 2             pixel density   (default 2, sharp on retina)
//   --pad 16              space around the element, in CSS pixels (default 16)
//   --wait 2500           ms to let the page and its animations settle (default 2500)
//   --full                the whole page, top to bottom (ignored with --selector)
//
// Works with http(s):// and file:// URLs. Set CHROME_PATH if Chrome isn't found.

import { spawn, execSync } from 'node:child_process';
import { existsSync, writeFileSync, mkdtempSync, rmSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, resolve } from 'node:path';

const args = process.argv.slice(2);
const FLAGS = ['--full'];
const pos = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && args[i - 1].startsWith('--') && !FLAGS.includes(args[i - 1])));
const opt = (name, def) => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : def; };
const [url, out] = pos;
if (!url || !out) {
  console.error('Usage: node shoot.mjs <url> <out.png> [--selector ".x"] [--css "..."] [--full] [--width 1440] [--height 900] [--scale 2] [--pad 16] [--wait 2500]');
  process.exit(1);
}
if (typeof WebSocket === 'undefined') {
  console.error('shoot.mjs needs Node 22 or newer (it uses the built-in WebSocket). You have ' + process.version + '.');
  process.exit(1);
}

function findChrome() {
  const candidates = [
    process.env.CHROME_PATH,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  ].filter(Boolean);
  for (const c of candidates) if (existsSync(c)) return c;
  for (const bin of ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']) {
    try { return execSync(`command -v ${bin}`, { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim(); } catch {}
  }
  return null;
}

const chromePath = findChrome();
if (!chromePath) {
  console.error('Chrome not found. Install Chrome, or set CHROME_PATH to a Chrome or Chromium binary.');
  process.exit(1);
}

const W = Number(opt('width', 1440)), H = Number(opt('height', 900));
const SCALE = Number(opt('scale', 2)), PAD = Number(opt('pad', 16)), WAIT = Number(opt('wait', 2500));
const selector = opt('selector', null), css = opt('css', null), full = args.includes('--full');

const profile = mkdtempSync(join(tmpdir(), 'shoot-'));
const port = 9300 + Math.floor(Math.random() * 600);
const chrome = spawn(chromePath, [
  '--headless=new', '--disable-gpu', '--hide-scrollbars', '--allow-file-access-from-files',
  `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, 'about:blank',
], { stdio: 'ignore' });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function done(code, msg) {
  if (msg) console[code ? 'error' : 'log'](msg);
  try { chrome.kill(); } catch {}
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
  process.exit(code);
}

let targets;
for (let i = 0; i < 60 && !targets; i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(200); }
}
const page = targets?.find((t) => t.type === 'page');
if (!page) done(1, 'Could not start headless Chrome.');

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r, j) => { ws.addEventListener('open', r); ws.addEventListener('error', j); });
let id = 0; const pending = new Map();
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
});
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async (expression) => (await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })).result?.result?.value;

await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: SCALE, mobile: W < 600 });
await send('Page.enable');
const nav = await send('Page.navigate', { url });
if (nav.result?.errorText) done(1, `Could not open ${url}: ${nav.result.errorText}`);
await sleep(WAIT);

if (css) {
  await evaluate(`(() => { const s = document.createElement('style'); s.textContent = ${JSON.stringify(css)}; document.head.appendChild(s); })()`);
  await sleep(600);
}

let clip;
if (selector) {
  const box = await evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) return null;
    el.scrollIntoView({ block: 'center' });
    const r = el.getBoundingClientRect();
    return { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height };
  })()`);
  if (!box) done(1, `No element matches ${selector} on ${url}.`);
  await sleep(700);
  clip = { x: Math.max(0, box.x - PAD), y: Math.max(0, box.y - PAD), width: box.w + PAD * 2, height: box.h + PAD * 2, scale: 1 };
}

if (!clip && full) {
  // Grow the viewport to the page's height, so fixed bars sit at the real top and bottom
  // instead of being stamped over the middle of the page.
  const size = await evaluate(`({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight })`);
  await send('Emulation.setDeviceMetricsOverride', { width: W, height: Math.max(H, size.h), deviceScaleFactor: SCALE, mobile: W < 600 });
  await evaluate('window.scrollTo(0, 0)');
  await sleep(800);
  const fullH = await evaluate('document.documentElement.scrollHeight');
  clip = { x: 0, y: 0, width: W, height: Math.max(H, fullH), scale: 1 };
}

const shot = await send('Page.captureScreenshot', { format: 'png', ...(clip ? { clip, captureBeyondViewport: true } : {}) });
if (!shot.result?.data) done(1, 'Screenshot failed.');
mkdirSync(dirname(resolve(out)), { recursive: true });
writeFileSync(out, Buffer.from(shot.result.data, 'base64'));
ws.close();
done(0, out);
