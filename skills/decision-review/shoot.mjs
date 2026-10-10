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
//   --clip x,y,w,h        crop to this rectangle (page pixels; image pixels for an image)
//
// Images (a Figma export, a screenshot you already have): pass the file instead of a URL.
//   node shoot.mjs slide.png crop.png --clip 740,150,560,580
//   node shoot.mjs slide.png no-chart.png --clip 740,150,560,580 --cover 760,440,275,275,#F7F7F7
//   --cover x,y,w,h,#hex  paint over a rectangle, to show an element removed (repeatable).
//                         Coordinates are in the source image's pixels, not the crop's.
//                         Leave the color out to use the color just left of the rectangle.
//                         Works on flat backgrounds; a gradient will show a band.
//   node shoot.mjs slide.png --pick 760,430      prints the color at that pixel
//   --logged-in           use the saved sign-in session (see --login)
//
// Pages behind a login:
//   node shoot.mjs --login https://app.example.com
//     Opens a normal Chrome window with a profile that belongs only to this tool.
//     Sign in yourself, then quit that window (Cmd+Q on Mac). The session stays saved.
//   node shoot.mjs <url> <out.png> --logged-in      shoots as the signed-in user
//   node shoot.mjs --logout                         deletes the saved session
//   --profile <dir>       where the session lives (default ~/.decision-review/chrome-profile)
//
// Your own Chrome profile, passwords and cookies are never touched.
// Works with http(s):// and file:// URLs. Set CHROME_PATH if Chrome isn't found.

import { spawn, execSync } from 'node:child_process';
import { existsSync, writeFileSync, mkdtempSync, rmSync, mkdirSync, lstatSync, readlinkSync } from 'node:fs';
import { tmpdir, homedir } from 'node:os';
import { join, dirname, resolve } from 'node:path';

const args = process.argv.slice(2);
const FLAGS = ['--full', '--logged-in', '--logout'];
const pos = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && args[i - 1].startsWith('--') && !FLAGS.includes(args[i - 1])));
const opt = (name, def) => { const i = args.indexOf(`--${name}`); return i >= 0 ? args[i + 1] : def; };
const [url, out] = pos;
const PROFILE_DIR = resolve(opt('profile', join(homedir(), '.decision-review', 'chrome-profile')));
const loginUrl = opt('login', null);

if (args.includes('--logout')) {
  rmSync(PROFILE_DIR, { recursive: true, force: true });
  console.log(`Signed out: deleted ${PROFILE_DIR}`);
  process.exit(0);
}
if (!loginUrl && (!url || (!out && !args.includes('--pick')))) {
  console.error('Usage: node shoot.mjs <url> <out.png> [--selector ".x"] [--css "..."] [--full] [--clip x,y,w,h] [--cover x,y,w,h,#hex] [--width 1440] [--height 900] [--scale 2] [--pad 16] [--wait 2500]');
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

function profileInUse() {
  // Chrome marks a profile in use with a SingletonLock link pointing at "host-PID".
  // A crash can leave it behind, so check that the process is really alive.
  const lock = join(PROFILE_DIR, 'SingletonLock');
  try { lstatSync(lock); } catch { return false; }
  try {
    const pid = Number(readlinkSync(lock).split('-').pop());
    if (pid) { process.kill(pid, 0); return true; }
  } catch {}
  for (const f of ['SingletonLock', 'SingletonCookie', 'SingletonSocket']) {
    try { rmSync(join(PROFILE_DIR, f), { force: true }); } catch {}
  }
  return false;
}

if (loginUrl) {
  // A normal, visible Chrome window: no automation, no debugging port. The user signs in by hand.
  mkdirSync(PROFILE_DIR, { recursive: true });
  if (profileInUse()) {
    console.error('The sign-in window is already open. Finish there and quit it (Cmd+Q on Mac).');
    process.exit(1);
  }
  console.log(`Opening ${loginUrl} in a separate Chrome window.`);
  console.log('Sign in there, then quit that window (Cmd+Q on Mac, or close it on Windows/Linux).');
  const win = spawn(chromePath, [`--user-data-dir=${PROFILE_DIR}`, '--no-first-run', '--no-default-browser-check', '--new-window', loginUrl], { stdio: 'ignore' });
  const timer = setTimeout(() => { console.error('Still open after 15 minutes, stopping. Run --login again when ready.'); win.kill(); process.exit(1); }, 15 * 60 * 1000);
  win.on('exit', () => { clearTimeout(timer); console.log(`Saved. Add --logged-in to shoot pages as the signed-in user. Session stored in ${PROFILE_DIR}`); process.exit(0); });
  await new Promise(() => {});
}

const W = Number(opt('width', 1440)), H = Number(opt('height', 900));
const SCALE = Number(opt('scale', 2)), PAD = Number(opt('pad', 16)), WAIT = Number(opt('wait', 2500));
const selector = opt('selector', null), css = opt('css', null), full = args.includes('--full');
const nums = (v) => String(v).split(',').map((n) => Number(n.trim()));
function rect(name, v) {
  const n = nums(v).slice(0, 4);
  if (n.length < 4 || n.some((x) => !Number.isFinite(x)) || n[0] < 0 || n[1] < 0 || n[2] <= 0 || n[3] <= 0) {
    console.error(`--${name} needs four numbers: x,y,width,height (x and y from the top left, not negative). Got "${v}".`);
    process.exit(1);
  }
  return n;
}
const pickArg = opt('pick', null);
const clipArg = opt('clip', null);
const covers = args.map((a, i) => (a === '--cover' ? args[i + 1] : null)).filter(Boolean);

// A plain file path works too. An image file is shown at its real pixel size.
let target = url;
if (target && !/^[a-z][a-z0-9+.-]*:/i.test(target) && existsSync(target)) target = 'file://' + resolve(target);
const imageMode = !!target && target.startsWith('file://') && /\.(png|jpe?g|webp|gif)$/i.test(target);
let imagePage = null;
if (imageMode) {
  const boxes = covers.map((c) => { const [x, y, w, h] = rect('cover', c); const color = (c.split(',')[4] || '').trim();
    return `<div class="cover" data-x="${x}" data-y="${y}" style="position:absolute;left:${x}px;top:${y}px;width:${w}px;height:${h}px;background:${color || 'transparent'}" ${color ? '' : 'data-auto="1"'}></div>`; }).join('');
  imagePage = join(tmpdir(), `shoot-image-${process.pid}.html`);
  writeFileSync(imagePage, `<!doctype html><body style="margin:0;position:relative;background:#fff"><img id="i" src="${target}" style="display:block">${boxes}</body>`);
}
const loggedIn = args.includes('--logged-in') || args.includes('--profile');
if (loggedIn && !existsSync(PROFILE_DIR)) {
  console.error(`No saved sign-in yet. Run: node shoot.mjs --login <the app's URL>, sign in, quit that window, then try again.`);
  process.exit(1);
}
if (loggedIn && profileInUse()) {
  console.error('The sign-in Chrome window is still open. Quit it (Cmd+Q on Mac) and run this again.');
  process.exit(1);
}

const profile = loggedIn ? PROFILE_DIR : mkdtempSync(join(tmpdir(), 'shoot-'));
const port = 9300 + Math.floor(Math.random() * 600);
const chrome = spawn(chromePath, [
  '--headless=new', '--disable-gpu', '--hide-scrollbars', '--allow-file-access-from-files',
  `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, 'about:blank',
], { stdio: 'ignore' });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let connected = false;
const exited = new Promise((r) => chrome.once('exit', r));
async function done(code, msg) {
  if (msg) console[code ? 'error' : 'log'](msg);
  if (loggedIn && connected) {
    // Quit Chrome properly so a refreshed session is written to disk, not lost.
    try { await Promise.race([send('Browser.close'), sleep(3000)]); } catch {}
    await Promise.race([exited, sleep(5000)]);
  }
  try { chrome.kill(); } catch {}
  if (!loggedIn) { try { rmSync(profile, { recursive: true, force: true }); } catch {} }
  process.exit(code);
}

let targets;
for (let i = 0; i < 60 && !targets; i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(200); }
}
const page = targets?.find((t) => t.type === 'page');
if (!page) await done(1, 'Could not start headless Chrome.');

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r, j) => { ws.addEventListener('open', r); ws.addEventListener('error', j); });
connected = true;
let id = 0; const pending = new Map();
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
});
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async (expression) => (await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })).result?.result?.value;

await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: SCALE, mobile: W < 600 });
await send('Page.enable');
const nav = await send('Page.navigate', { url: imageMode ? 'file://' + imagePage : target });
if (nav.result?.errorText) await done(1, `Could not open ${url}: ${nav.result.errorText}`);
await sleep(imageMode ? 600 : WAIT);

let imageClip = null;
if (imageMode) {
  const size = await evaluate(`(async () => { const i = document.getElementById('i'); if (!i.complete) await new Promise((r) => { i.onload = r; i.onerror = r; }); return { w: i.naturalWidth, h: i.naturalHeight }; })()`);
  try { rmSync(imagePage, { force: true }); } catch {}
  if (!size || !size.w) await done(1, `Could not read the image ${url}.`);
  await send('Emulation.setDeviceMetricsOverride', { width: size.w, height: size.h, deviceScaleFactor: 1, mobile: false });
  await sleep(200);
  // Read colors straight from the image: for --pick, and for covers with no color given.
  const color = (x, y) => evaluate(`(() => { const i = document.getElementById('i'); const c = document.createElement('canvas'); c.width = i.naturalWidth; c.height = i.naturalHeight; const g = c.getContext('2d'); g.drawImage(i, 0, 0); const d = g.getImageData(${Math.round(x)}, ${Math.round(y)}, 1, 1).data; return '#' + [d[0], d[1], d[2]].map((v) => v.toString(16).padStart(2, '0')).join(''); })()`);
  if (pickArg) {
    const [px, py] = nums(pickArg);
    if (!(px >= 0 && py >= 0 && px < size.w && py < size.h)) await done(1, `--pick ${pickArg} is outside the image (${size.w}x${size.h}).`);
    await done(0, await color(px, py));
  }
  const autos = await evaluate(`[...document.querySelectorAll('.cover[data-auto]')].map((e) => [Number(e.dataset.x), Number(e.dataset.y)])`);
  for (let k = 0; k < autos.length; k++) {
    const [cx, cy] = autos[k];
    const hex = await color(Math.max(0, cx - 3), cy + 2);
    await evaluate(`document.querySelectorAll('.cover[data-auto]')[${k}].style.background = ${JSON.stringify(hex)}`);
  }
  const [x, y, w, h] = clipArg ? rect('clip', clipArg) : [0, 0, size.w, size.h];
  if (x >= size.w || y >= size.h) await done(1, `--clip ${clipArg} starts outside the image, which is ${size.w}x${size.h} pixels.`);
  const cw = Math.min(w, size.w - x), ch = Math.min(h, size.h - y);
  if (cw < w || ch < h) console.error(`warning: --clip ${clipArg} runs past the image (${size.w}x${size.h}); cropped to ${cw}x${ch}.`);
  imageClip = { x, y, width: cw, height: ch, scale: 1 };
}

const landed = await evaluate('location.href');
try {
  if (imageMode) throw 0;
  const a = new URL(target), b = new URL(landed);
  const gate = /(^|[\/._-])(log-?in|sign-?in|auth|sso|session|oauth)([\/._-]|$)/i;
  if (a.href !== b.href && gate.test(b.hostname + b.pathname) && !gate.test(a.hostname + a.pathname)) {
    console.error(`warning: ${url} redirected to ${landed}, which looks like a sign-in page.` +
      (loggedIn ? ' The saved session may have expired: run --login again.' : ' Run: node shoot.mjs --login ' + a.origin + ' once, then add --logged-in.'));
  }
} catch {}

if (css) {
  await evaluate(`(() => { const s = document.createElement('style'); s.textContent = ${JSON.stringify(css)}; document.head.appendChild(s); })()`);
  await sleep(600);
}

let clip = imageClip;
if (!clip && clipArg) {
  const [x, y, w, h] = rect('clip', clipArg);
  clip = { x, y, width: w, height: h, scale: 1 };
}
if (!imageMode && selector) {
  const box = await evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) return null;
    el.scrollIntoView({ block: 'center' });
    const r = el.getBoundingClientRect();
    return { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height };
  })()`);
  if (!box) await done(1, `No element matches ${selector} on ${url}.`);
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
  // The viewport now is the whole page, so a plain viewport capture is enough.
  // (Clipping "beyond the viewport" shifts right-to-left pages sideways.)
  const fullH = await evaluate('document.documentElement.scrollHeight');
  if (fullH > Math.max(H, size.h)) {
    await send('Emulation.setDeviceMetricsOverride', { width: W, height: fullH, deviceScaleFactor: SCALE, mobile: W < 600 });
    await sleep(400);
  }
}

const shot = await send('Page.captureScreenshot', { format: 'png', ...(clip ? { clip, captureBeyondViewport: !imageMode } : {}) });
if (!shot.result?.data) await done(1, 'Screenshot failed.');
mkdirSync(dirname(resolve(out)), { recursive: true });
writeFileSync(out, Buffer.from(shot.result.data, 'base64'));
await done(0, out);
