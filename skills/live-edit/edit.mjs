#!/usr/bin/env node
// Open a page in Chrome with a Figma-style editor on top. The user edits by hand and clicks
// "Send to Claude"; every change is written to edits.json, with before/after screenshots.
// No dependencies: drives the Chrome you already have over the DevTools protocol.
//
//   node edit.mjs <file.html | url> [options]
//
//   --out edits.json      where to write the edits (default ./edits.json, screenshots next to it)
//   --lang he|en          editor language (default en)
//   --width 390           fix the viewport width, e.g. to edit the mobile layout (default: the window)
//   --height 844          fix the viewport height (with --width)
//   --timeout 120         minutes to wait for "Send to Claude" before giving up (default 120)
//   --logged-in           use the saved sign-in session from decision-review (shoot.mjs --login)
//   --profile <dir>       use this Chrome profile directory instead
//
// The command returns when the user clicks "Send to Claude" or closes the window.
// Edits are also saved as they happen, so closing the window loses nothing.
// Your own Chrome profile, passwords and cookies are never touched. Set CHROME_PATH if Chrome isn't found.

import { spawn, execSync } from 'node:child_process';
import { existsSync, writeFileSync, readFileSync, mkdtempSync, rmSync, mkdirSync } from 'node:fs';
import { tmpdir, homedir } from 'node:os';
import { join, dirname, resolve, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const args = process.argv.slice(2);
const FLAGS = ['--logged-in', '--headless'];
const pos = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && args[i - 1].startsWith('--') && !FLAGS.includes(args[i - 1])));
const opt = (name, def) => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : def; };
const [input] = pos;
if (!input) {
  console.error('Usage: node edit.mjs <file.html | url> [--out edits.json] [--lang he|en] [--width 390 --height 844] [--logged-in]');
  process.exit(1);
}
if (typeof WebSocket === 'undefined') {
  console.error('edit.mjs needs Node 22 or newer (it uses the built-in WebSocket). You have ' + process.version + '.');
  process.exit(1);
}

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(opt('out', 'edits.json'));
const stem = OUT.replace(/\.json$/i, '');
const SHOT_BEFORE = `${stem}-before.png`, SHOT_AFTER = `${stem}-after.png`;
mkdirSync(dirname(OUT), { recursive: true });
const LANG = opt('lang', 'en') === 'he' ? 'he' : 'en';
const TIMEOUT = Number(opt('timeout', 120)) * 60 * 1000;
const W = opt('width', null), H = opt('height', null);
const headless = args.includes('--headless'); // for tests only: nobody can click in a headless window
const PROFILE_DIR = resolve(opt('profile', join(homedir(), '.decision-review', 'chrome-profile')));
const useProfile = args.includes('--logged-in') || args.includes('--profile');

let target = input;
if (!/^[a-z][a-z0-9+.-]*:/i.test(target)) {
  if (!existsSync(target)) { console.error(`No such file: ${target}`); process.exit(1); }
  target = 'file://' + resolve(target);
}
if (useProfile && !existsSync(PROFILE_DIR)) {
  console.error('No saved sign-in yet. Run: node ../decision-review/shoot.mjs --login <the app\'s URL>, sign in, quit that window, then try again.');
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
if (!chromePath) { console.error('Chrome not found. Install Chrome, or set CHROME_PATH to a Chrome or Chromium binary.'); process.exit(1); }

const profile = useProfile ? PROFILE_DIR : mkdtempSync(join(tmpdir(), 'live-edit-'));
rmSync(join(profile, 'DevToolsActivePort'), { force: true });
const chrome = spawn(chromePath, [
  ...(headless ? ['--headless=new'] : []),
  ...(process.getuid?.() === 0 ? ['--no-sandbox'] : []), // Chrome refuses to start as root otherwise (containers, CI)
  '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check',
  '--allow-file-access-from-files', '--window-size=1600,1000', 'about:blank',
], { stdio: 'ignore' });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let finished = false;
const pages = new Map(); // url -> latest report from that page
let sentOnce = false;

function writeEdits(status) {
  const list = [...pages.values()].filter((p) => p.elements.length || p.note);
  const out = {
    tool: 'live-edit', version: 1, status, source: input, savedAt: new Date().toISOString(),
    screenshots: { before: existsSync(SHOT_BEFORE) ? basename(SHOT_BEFORE) : null, after: existsSync(SHOT_AFTER) ? basename(SHOT_AFTER) : null },
    pages: list.length ? list : [...pages.values()].slice(-1),
  };
  mkdirSync(dirname(OUT), { recursive: true });
  writeFileSync(OUT, JSON.stringify(out, null, 2) + '\n');
  return list.reduce((n, p) => n + p.elements.reduce((m, e) => m + e.changes.length, 0), 0);
}

async function finish(code, msg) {
  if (finished) return;
  finished = true;
  if (msg) console[code ? 'error' : 'log'](msg);
  try { chrome.kill(); } catch {}
  if (!useProfile) { await sleep(300); try { rmSync(profile, { recursive: true, force: true }); } catch {} }
  process.exit(code);
}
let opened = false;
chrome.once('exit', () => {
  if (finished) return;
  if (!opened) return finish(1, 'Chrome closed before the editor opened. Is another Chrome using this profile?');
  const n = writeEdits(sentOnce ? 'sent' : 'closed');
  finish(0, sentOnce ? `Sent: ${n} changes → ${OUT}` : `Window closed without "Send to Claude". Saved ${n} changes anyway → ${OUT}`);
});

// Chrome writes the port it picked into the profile folder.
let port = null;
for (let i = 0; i < 100 && !port; i++) {
  try { port = readFileSync(join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0].trim(); } catch { await sleep(150); }
}
if (!port) await finish(1, 'Could not start Chrome.');
let targets;
for (let i = 0; i < 60 && !targets?.some((t) => t.type === 'page'); i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(200); }
}
const page = targets?.find((t) => t.type === 'page');
if (!page) await finish(1, 'Could not open a Chrome window.');

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r, j) => { ws.addEventListener('open', r); ws.addEventListener('error', j); });
let id = 0; const pending = new Map(); const listeners = [];
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  else if (m.method) listeners.forEach((fn) => fn(m));
});
ws.addEventListener('close', () => { if (!finished) chrome.emit('exit'); });
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async (expression) => (await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })).result?.result?.value;

async function fullShot(file) {
  await evaluate('window.__liveEdit && window.__liveEdit.chrome(false)');
  await sleep(150);
  try {
    const m = (await send('Page.getLayoutMetrics')).result;
    const size = m.cssContentSize || m.contentSize;
    const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true,
      clip: { x: 0, y: 0, width: Math.ceil(size.width), height: Math.min(Math.ceil(size.height), 12000), scale: 1 } });
    if (shot.result?.data) writeFileSync(file, Buffer.from(shot.result.data, 'base64'));
  } finally {
    await evaluate('window.__liveEdit && window.__liveEdit.chrome(true)');
  }
}

const editor = readFileSync(join(HERE, 'editor.js'), 'utf8');
await send('Page.enable');
await send('Runtime.enable');
await send('Page.setBypassCSP', { enabled: true });
await send('Runtime.addBinding', { name: '__liveEditSave' });
await send('Page.addScriptToEvaluateOnNewDocument', { source: `window.__LIVE_EDIT_CFG = ${JSON.stringify({ lang: LANG, waitForReady: true })};\n${editor}` });
if (W) await send('Emulation.setDeviceMetricsOverride', { width: Number(W), height: Number(H || 900), deviceScaleFactor: 0, mobile: Number(W) < 600 });

let firstLoad = true;
listeners.push(async (m) => {
  if (m.method === 'Runtime.bindingCalled' && m.params.name === '__liveEditSave') {
    let msg; try { msg = JSON.parse(m.params.payload); } catch { return; }
    pages.set(msg.data.url, msg.data);
    if (!msg.done) { writeEdits('editing'); return; }
    sentOnce = true;
    try { await fullShot(SHOT_AFTER); } catch (err) { console.error(`warning: no after screenshot (${err.message})`); }
    const n = writeEdits('sent');
    await evaluate('window.__liveEdit && window.__liveEdit.sentToast()');
    await sleep(1200);
    await finish(0, `Sent: ${n} changes → ${OUT}\nScreenshots: ${SHOT_BEFORE}, ${SHOT_AFTER}`);
  }
  if (m.method === 'Page.loadEventFired') {
    await sleep(700);
    try { if (firstLoad) { firstLoad = false; await fullShot(SHOT_BEFORE); } }
    catch (err) { console.error(`warning: no before screenshot (${err.message})`); }
    await evaluate('window.__liveEdit && window.__liveEdit.ready()');
  }
});

const nav = await send('Page.navigate', { url: target });
if (nav.result?.errorText) await finish(1, `Could not open ${input}: ${nav.result.errorText}`);
opened = true;
console.log(`Editor open on ${target}. Waiting for "Send to Claude"…`);
setTimeout(() => { const n = writeEdits('timeout'); finish(0, `Stopped waiting after ${TIMEOUT / 60000} minutes. Saved ${n} changes → ${OUT}`); }, TIMEOUT);
