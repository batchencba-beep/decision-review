// Live edit: a Figma-style editor that edit.mjs injects into the page.
// Select, drag, resize and restyle anything on the page, then send every change
// back to Claude as structured data (edits.json). No dependencies.
(() => {
  if (window.top !== window || window.__liveEdit) return;
  const CFG = Object.assign({ lang: 'en', waitForReady: false }, window.__LIVE_EDIT_CFG || {});
  const HE = CFG.lang === 'he';

  const STR = {
    en: {
      edit: 'Edit', interact: 'Interact', undo: 'Undo', redo: 'Redo', changes: (n) => (n === 1 ? '1 change' : `${n} changes`),
      send: 'Send to Claude', sent: 'Sent. Go back to Claude.', saved: 'Saved', layers: 'Layers', design: 'Design',
      pageNote: 'Note for the whole screen', pageNotePh: 'Anything Claude should know about this screen as a whole',
      empty: 'Click anything on the page to select it.\n\nDrag to move or reorder · ⌘/Ctrl-drag to move freely\nDouble-click text to edit it\nEsc parent · Enter child · ⌘Z undo · ⌘D duplicate · Delete',
      position: 'Position', layout: 'Layout', auto: 'Auto layout', addAuto: '+ Add auto layout', removeAuto: 'Remove',
      padding: 'Padding', margin: 'Margin', appearance: 'Appearance', fill: 'Fill', stroke: 'Stroke', effects: 'Effects',
      text: 'Text', image: 'Image', intent: 'Intent & interaction',
      intentPh: 'What should this do? e.g. "lifts 4px on hover", "opens the pricing drawer", "same change on all cards"',
      parent: 'Parent', hide: 'Hide', del: 'Delete', dup: 'Duplicate', hideUI: 'Hide panels (⌘\\)', fold: 'Fold or unfold this panel',
      editHint: 'Typing. Click outside or press Esc to finish.', reorderHint: 'Release to reorder', moveHint: 'Moving freely',
      none: 'None', leave: 'Your edits are saved, but they will disappear from the screen if you leave this page.',
    },
    he: {
      edit: 'עריכה', interact: 'גלישה', undo: 'ביטול', redo: 'חזרה', changes: (n) => (n === 1 ? 'שינוי אחד' : `${n} שינויים`),
      send: 'שליחה לקלוד', sent: 'נשלח. אפשר לחזור לקלוד.', saved: 'נשמר', layers: 'שכבות', design: 'עיצוב',
      pageNote: 'הערה לכל המסך', pageNotePh: 'כל מה שקלוד צריך לדעת על המסך כולו',
      empty: 'לחיצה על כל אלמנט בעמוד בוחרת אותו.\n\nגרירה מזיזה או משנה סדר · ⌘/Ctrl וגרירה מזיזים חופשי\nלחיצה כפולה על טקסט עורכת אותו\nEsc הורה · Enter ילד · ⌘Z ביטול · ⌘D שכפול · Delete מחיקה',
      position: 'מיקום', layout: 'פריסה', auto: 'אוטו לייאאוט', addAuto: '+ הוספת אוטו לייאאוט', removeAuto: 'הסרה',
      padding: 'ריווח פנימי', margin: 'ריווח חיצוני', appearance: 'מראה', fill: 'מילוי', stroke: 'קו מתאר', effects: 'אפקטים',
      text: 'טקסט', image: 'תמונה', intent: 'כוונה ואינטראקציה',
      intentPh: 'מה זה אמור לעשות? למשל "מתרומם 4px במעבר עכבר", "פותח מגירת מחירים", "אותו שינוי בכל הכרטיסים"',
      parent: 'הורה', hide: 'הסתרה', del: 'מחיקה', dup: 'שכפול', hideUI: 'הסתרת פאנלים (⌘\\)', fold: 'קיפול או פתיחה של הפאנל',
      editHint: 'מצב הקלדה. לחיצה בחוץ או Esc לסיום.', reorderHint: 'שחרור משנה את הסדר', moveHint: 'הזזה חופשית',
      none: 'ללא', leave: 'העריכות נשמרו, אבל הן ייעלמו מהמסך אם עוזבים את העמוד.',
    },
  }[HE ? 'he' : 'en'];

  const SKIP = new Set(['SCRIPT', 'STYLE', 'LINK', 'META', 'NOSCRIPT', 'TEMPLATE', 'BR', 'HEAD', 'TITLE', 'BASE']);
  const TEXTY = new Set(['P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'SPAN', 'A', 'BUTTON', 'LABEL', 'LI', 'STRONG', 'EM', 'B', 'I', 'SMALL', 'BLOCKQUOTE', 'FIGCAPTION', 'TD', 'TH', 'DT', 'DD', 'CODE', 'SUMMARY', 'LEGEND']);
  const IMAGE = new Set(['IMG', 'SVG', 'PICTURE', 'VIDEO', 'CANVAS', 'IFRAME']);

  // ---------- state ----------
  let host, root, ui = {};
  let mode = 'edit', shown = true, active = false, sent = false;
  let selected = null, hovered = null, editing = null, drag = null;
  const ops = [], redo = [];
  const notes = new Map();
  let pageNote = '';
  const selCache = new WeakMap();
  const copyIds = new WeakMap();
  let copyCount = 0, frozen = false, gidSeq = 0, saveTimer = null, toastTimer = null;
  const expanded = new WeakSet();
  const nextGid = () => ++gidSeq;

  // ---------- naming and selectors ----------
  const isOurs = (n) => n === host || (host && host.contains(n));
  const isLayer = (el) => el && el.nodeType === 1 && !SKIP.has(el.tagName) && !isOurs(el);
  const layerKids = (el) => [...el.children].filter(isLayer);
  const ownText = (el) => [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(' ').replace(/\s+/g, ' ').trim();
  const clip = (s, n = 32) => (s.length > n ? s.slice(0, n - 1) + '…' : s);

  function nameOf(el) {
    if (copyIds.has(el)) return `${nameOf(copyIds.get(el).of)} (copy ${copyIds.get(el).n})`;
    const tag = el.tagName.toLowerCase();
    const cls = [...el.classList].find((c) => !c.startsWith('le-'));
    const base = el.id ? `${tag}#${el.id}` : cls ? `${tag}.${cls}` : tag;
    const t = (el.getAttribute('aria-label') || ownText(el) || (el.children.length === 0 ? el.textContent : '') || el.getAttribute('alt') || '').replace(/\s+/g, ' ').trim();
    return t ? `${base} “${clip(t, 26)}”` : base;
  }

  function computeSelector(el) {
    if (copyIds.has(el)) return `[data-live-edit-copy="${copyIds.get(el).n}"]`;
    const uniq = (s) => { try { return document.querySelectorAll(s).length === 1; } catch { return false; } };
    if (el.id && uniq('#' + CSS.escape(el.id))) return '#' + CSS.escape(el.id);
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && cur !== document.documentElement) {
      if (cur !== el && cur.id && uniq('#' + CSS.escape(cur.id))) { parts.unshift('#' + CSS.escape(cur.id)); break; }
      let part = cur.tagName.toLowerCase();
      if (cur === document.body) { parts.unshift('body'); break; }
      const cls = [...cur.classList].filter((c) => /^[a-zA-Z_][\w-]*$/.test(c) && !/^(is-|has-|js-)|^(active|hover|focus|open|selected)$/.test(c)).slice(0, 2);
      if (cls.length) part += '.' + cls.map((c) => CSS.escape(c)).join('.');
      const parent = cur.parentElement;
      if (parent) {
        const same = [...parent.children].filter((s) => s.tagName === cur.tagName && !copyIds.has(s));
        if (same.length > 1) part += `:nth-of-type(${same.indexOf(cur) + 1})`;
      }
      parts.unshift(part);
      if (uniq(parts.join(' > '))) return parts.join(' > ');
      cur = parent;
    }
    return parts.join(' > ');
  }
  const selOf = (el) => { if (!selCache.has(el)) selCache.set(el, computeSelector(el)); return selCache.get(el); };
  // Before the first structural change, remember every element's selector on the untouched page,
  // so selectors in edits.json always point at the original source.
  function freezeSelectors() {
    if (frozen) return;
    frozen = true;
    let n = 0;
    for (const el of document.body.querySelectorAll('*')) { if (isLayer(el)) selOf(el); if (++n > 20000) break; }
  }

  // ---------- operations, undo, redo ----------
  const OPS = {
    style: {
      apply: (o) => (o.after === '' ? o.el.style.removeProperty(o.prop) : o.el.style.setProperty(o.prop, o.after, 'important')),
      revert: (o) => (o.before === '' ? o.el.style.removeProperty(o.prop) : o.el.style.setProperty(o.prop, o.before, o.beforePri)),
    },
    attr: {
      apply: (o) => (o.after == null ? o.el.removeAttribute(o.name) : o.el.setAttribute(o.name, o.after)),
      revert: (o) => (o.before == null ? o.el.removeAttribute(o.name) : o.el.setAttribute(o.name, o.before)),
    },
    text: {
      apply: (o) => setText(o, 'after'),
      revert: (o) => setText(o, 'before'),
    },
    reorder: {
      apply: (o) => o.parent.insertBefore(o.el, o.afterNext),
      revert: (o) => o.parent.insertBefore(o.el, o.beforeNext),
    },
    duplicate: {
      apply: (o) => o.parent.insertBefore(o.el, o.next),
      revert: (o) => o.el.remove(),
    },
  };
  function setText(o, side) {
    if (o.nodes) o.nodes.forEach((n, i) => { n.data = o[side + 'Data'][i]; });
    else o.el.innerHTML = o[side + 'HTML'];
  }

  function push(op) {
    if (!op.gid) op.gid = nextGid();
    selOf(op.el);
    if (op.type === 'duplicate') selOf(op.of);
    OPS[op.type].apply(op);
    ops.push(op);
    redo.length = 0;
    changed();
  }
  function setStyle(el, prop, value, gid, kind = 'style') {
    if (!el) return;
    const last = gid && [...ops].reverse().find((o) => o.gid === gid && o.el === el && o.prop === prop);
    if (last) { last.after = value; OPS.style.apply(last); changed(); return; }
    push({ type: 'style', kind, el, prop, after: value, gid,
      before: el.style.getPropertyValue(prop), beforePri: el.style.getPropertyPriority(prop),
      from: getComputedStyle(el).getPropertyValue(prop) });
  }
  function undo() {
    if (!ops.length) return;
    const gid = ops[ops.length - 1].gid, group = [];
    while (ops.length && ops[ops.length - 1].gid === gid) { const o = ops.pop(); OPS[o.type].revert(o); group.push(o); }
    redo.push(group);
    changed(true);
  }
  function redoOne() {
    const group = redo.pop();
    if (!group) return;
    for (const o of group.reverse()) { OPS[o.type].apply(o); ops.push(o); }
    changed(true);
  }
  function changed(structural) {
    if (structural && selected && !selected.isConnected) select(null);
    refreshUI(structural);
    scheduleSave();
  }

  // ---------- the report Claude reads ----------
  const rgbHex = (v) => {
    const m = String(v).match(/^rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/);
    if (!m) return v;
    const hex = '#' + [m[1], m[2], m[3]].map((x) => Math.round(+x).toString(16).padStart(2, '0')).join('');
    if (m[4] == null) return hex.toUpperCase();
    const a = m[4].endsWith('%') ? parseFloat(m[4]) / 100 : +m[4];
    return a >= 1 ? hex.toUpperCase() : (hex + Math.round(a * 255).toString(16).padStart(2, '0')).toUpperCase();
  };
  const pretty = (v) => String(v).replace(/rgba?\([^)]*\)/g, rgbHex);

  function report() {
    const byEl = new Map();
    const entry = (el) => {
      if (!byEl.has(el)) byEl.set(el, { selector: selOf(el), name: nameOf(el), changes: [] });
      return byEl.get(el);
    };
    const groups = new Map();
    for (const o of ops) {
      const key = o.type === 'style' ? `style:${o.prop}` : o.type === 'attr' ? `attr:${o.name}` : o.type;
      if (!groups.has(o.el)) groups.set(o.el, new Map());
      const g = groups.get(o.el);
      if (!g.has(key)) g.set(key, []);
      g.get(key).push(o);
    }
    const css = [];
    for (const [el, g] of groups) {
      const e = entry(el);
      const rules = [];
      for (const [key, list] of g) {
        const first = list[0], last = list[list.length - 1];
        if (first.type === 'style') {
          if (last.after === first.before) continue;
          if (first.prop === 'display' && last.after === 'none') {
            e.changes.push({ type: last.kind === 'hide' ? 'hide' : 'delete' });
            continue;
          }
          if (last.kind === 'move') e.changes.push({ type: 'move', property: 'translate', before: pretty(first.from), after: pretty(last.after) });
          else e.changes.push({ type: 'style', property: first.prop, before: pretty(first.from), after: pretty(last.after) });
          rules.push(`  ${first.prop}: ${pretty(last.after)};`);
        } else if (first.type === 'attr') {
          if (last.after === first.before) continue;
          e.changes.push({ type: 'attribute', name: first.name, before: first.before, after: last.after });
        } else if (first.type === 'text') {
          const after = el.innerText.trim();
          if (after === first.beforeText) continue;
          e.changes.push({ type: 'text', before: first.beforeText, after });
        } else if (first.type === 'reorder') {
          const now = layerKids(el.parentElement);
          const idx = now.indexOf(el);
          if (idx === first.fromIndex && el.parentElement === first.fromParent) continue;
          const prev = now[idx - 1], next = now[idx + 1];
          e.changes.push({ type: 'reorder', parent: selOf(el.parentElement), fromIndex: first.fromIndex, toIndex: idx,
            nowAfter: prev ? selOf(prev) : null, nowBefore: next ? selOf(next) : null });
        } else if (first.type === 'duplicate') {
          if (!el.isConnected) continue;
          const now = layerKids(el.parentElement);
          const prev = now[now.indexOf(el) - 1];
          e.changes.push({ type: 'duplicate', of: selOf(first.of), placedAfter: prev ? selOf(prev) : null });
        }
      }
      if (rules.length) css.push(`${selOf(el)} {\n${rules.join('\n')}\n}`);
    }
    for (const [el, text] of notes) if (text.trim()) entry(el).note = text.trim();
    const elements = [...byEl.values()].filter((e) => e.changes.length || e.note);
    const count = elements.reduce((n, e) => n + e.changes.length, 0);
    return {
      url: location.href, title: document.title,
      viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
      note: pageNote.trim() || undefined,
      summary: `${elements.length} element${elements.length === 1 ? '' : 's'}, ${count} change${count === 1 ? '' : 's'}`,
      elements, css: css.join('\n\n'),
    };
  }
  const changeCount = () => report().elements.reduce((n, e) => n + e.changes.length + (e.note ? 1 : 0), 0) + (pageNote.trim() ? 1 : 0);

  function scheduleSave() { clearTimeout(saveTimer); saveTimer = setTimeout(() => save(false), 400); }
  function save(done) {
    const payload = JSON.stringify({ done, data: report() });
    if (typeof window.__liveEditSave === 'function') { window.__liveEditSave(payload); return; }
    if (done) {
      // Opened without edit.mjs: hand the file over as a download instead.
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([JSON.stringify(JSON.parse(payload).data, null, 2)], { type: 'application/json' }));
      a.download = 'edits.json';
      a.click();
    }
  }

  // ---------- selection ----------
  function select(el, fromTree) {
    if (editing && editing !== el) stopEditing();
    selected = el && isLayer(el) ? el : null;
    if (selected) {
      for (let p = selected.parentElement; p && p !== document.documentElement; p = p.parentElement) expanded.add(p);
      if (fromTree) selected.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }
    renderTree();
    renderProps();
    const row = selected && ui.tree.querySelector('.row.sel');
    if (row && !fromTree) row.scrollIntoView({ block: 'nearest' });
  }
  const parentOf = (el) => (el && el.parentElement && el.parentElement !== document.documentElement ? el.parentElement : null);

  // ---------- text editing ----------
  function textNodes(el) {
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), out = [];
    while (w.nextNode()) out.push(w.currentNode);
    return out;
  }
  function startEditing(el) {
    if (!el || !el.innerText.trim()) return;
    stopEditing();
    editing = el;
    const nodes = textNodes(el);
    el.__le = { html: el.innerHTML, text: el.innerText.trim(), nodes, data: nodes.map((n) => n.data), ce: el.getAttribute('contenteditable') };
    el.setAttribute('contenteditable', 'plaintext-only');
    el.focus();
    const r = document.createRange(); r.selectNodeContents(el);
    const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    status(STR.editHint);
  }
  function stopEditing() {
    const el = editing;
    if (!el) return;
    editing = null;
    const b = el.__le; delete el.__le;
    if (b.ce == null) el.removeAttribute('contenteditable'); else el.setAttribute('contenteditable', b.ce);
    getSelection().removeAllRanges();
    status('');
    if (el.innerText.trim() === b.text) return;
    const now = textNodes(el);
    const same = now.length === b.nodes.length && now.every((n, i) => n === b.nodes[i]);
    const op = same
      ? { type: 'text', el, nodes: now, beforeData: b.data, afterData: now.map((n) => n.data), beforeText: b.text }
      : { type: 'text', el, beforeHTML: b.html, afterHTML: el.innerHTML, beforeText: b.text };
    op.gid = nextGid();
    selOf(el);
    ops.push(op); redo.length = 0;
    changed();
  }

  // ---------- structural actions ----------
  function reorder(el, parent, next) {
    if (!el || next === el || (next && next.previousElementSibling === el && parent === el.parentElement)) return;
    freezeSelectors();
    const from = el.parentElement;
    push({ type: 'reorder', el, parent, beforeNext: el.nextSibling, afterNext: next, fromParent: from, fromIndex: layerKids(from).indexOf(el) });
    renderTree();
  }
  function stepOrder(el, dir) {
    if (!el || !parentOf(el)) return;
    const kids = layerKids(el.parentElement), i = kids.indexOf(el);
    if (dir < 0 && i > 0) reorder(el, el.parentElement, kids[i - 1]);
    if (dir > 0 && i < kids.length - 1) reorder(el, el.parentElement, kids[i + 1].nextSibling);
  }
  function duplicate(el) {
    if (!el || !parentOf(el)) return;
    freezeSelectors();
    const clone = el.cloneNode(true);
    copyIds.set(clone, { of: el, n: ++copyCount });
    clone.setAttribute('data-live-edit-copy', String(copyCount));
    push({ type: 'duplicate', el: clone, of: el, parent: el.parentElement, next: el.nextSibling });
    select(clone);
  }
  function remove(el) {
    if (!el || el === document.body) return;
    const p = parentOf(el);
    setStyle(el, 'display', 'none', null, 'delete');
    select(p);
  }
  function toggleHide(el) {
    const op = [...ops].reverse().find((o) => o.el === el && o.prop === 'display');
    if (op && op.after === 'none') setStyle(el, 'display', op.before, null, 'hide');
    else setStyle(el, 'display', 'none', null, 'hide');
    renderTree();
  }

  // ---------- pointer: select, move, reorder, resize ----------
  const fromPath = (e) => { const t = e.composedPath ? e.composedPath()[0] : e.target; return t && t.nodeType === 1 ? t : t && t.parentElement; };
  const inUI = (e) => e.composedPath && e.composedPath().includes(host);
  const flowAxis = (parent) => {
    const cs = getComputedStyle(parent);
    if (cs.display.includes('flex')) return cs.flexDirection.startsWith('column') ? 'y' : 'x';
    if (cs.display.includes('grid')) return 'xy';
    return 'y';
  };
  const canReorder = (el) => {
    const p = parentOf(el);
    if (!p || layerKids(p).length < 2) return false;
    const pos = getComputedStyle(el).position;
    if (pos === 'absolute' || pos === 'fixed') return false;
    const ps = getComputedStyle(p).display;
    return ps.includes('flex') || ps.includes('grid') || getComputedStyle(el).display !== 'inline';
  };
  const parseTranslate = (el) => {
    const v = el.style.getPropertyValue('translate') || getComputedStyle(el).translate;
    if (!v || v === 'none') return [0, 0];
    const [x, y] = v.split(/\s+/).map(parseFloat);
    return [x || 0, y || 0];
  };

  function dropTarget(el, x, y) {
    const p = el.parentElement, axis = flowAxis(p);
    const kids = layerKids(p).filter((k) => k !== el && getComputedStyle(k).display !== 'none');
    let best = null, bestD = Infinity;
    for (const k of kids) {
      const r = k.getBoundingClientRect();
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      const d = axis === 'x' ? Math.abs(x - cx) : axis === 'y' ? Math.abs(y - cy) : Math.hypot(x - cx, y - cy);
      if (d < bestD) { bestD = d; best = { k, r, after: axis === 'y' ? y > cy : (HE && axis !== 'y' && getComputedStyle(p).direction === 'rtl') ? x < cx : x > cx }; }
    }
    if (!best) return null;
    return { parent: p, next: best.after ? best.k.nextSibling : best.k, rect: best.r, after: best.after, axis };
  }

  function onPointerDown(e) {
    if (!active || mode !== 'edit' || inUI(e) || e.button !== 0) return;
    const t = fromPath(e);
    if (editing && editing.contains(t)) return;
    e.preventDefault(); e.stopPropagation();
    if (editing) stopEditing();
    if (!isLayer(t)) return;
    const target = selected && selected !== t && selected.contains(t) ? selected : t;
    const [tx, ty] = parseTranslate(target);
    drag = { el: target, pick: t, x0: e.clientX, y0: e.clientY, tx, ty, mode: null, gid: nextGid(), free: e.metaKey || e.ctrlKey };
    if (target === t && selected !== t) select(t);
  }
  function onPointerMove(e) {
    if (!active) return;
    if (drag && drag.resize) return resizeMove(e);
    if (drag) {
      const dx = e.clientX - drag.x0, dy = e.clientY - drag.y0;
      if (!drag.mode && Math.hypot(dx, dy) > 3) {
        if (drag.el !== selected) select(drag.el);
        drag.mode = !drag.free && canReorder(drag.el) ? 'reorder' : 'move';
        status(drag.mode === 'reorder' ? STR.reorderHint : STR.moveHint);
      }
      if (drag.mode === 'move') {
        let mx = dx, my = dy;
        if (e.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) my = 0; else mx = 0; }
        setStyle(drag.el, 'translate', `${Math.round(drag.tx + mx)}px ${Math.round(drag.ty + my)}px`, drag.gid, 'move');
      } else if (drag.mode === 'reorder') {
        drag.drop = dropTarget(drag.el, e.clientX, e.clientY);
        drawDrop(drag.drop);
      }
      return;
    }
    if (mode !== 'edit' || inUI(e)) { if (hovered && !inUI(e)) hovered = null; return; }
    const t = fromPath(e);
    hovered = isLayer(t) ? t : null;
  }
  function onPointerUp(e) {
    if (!active) return;
    if (drag && drag.resize) { drag = null; status(''); return; }
    if (!drag) return;
    const d = drag; drag = null;
    e.preventDefault(); e.stopPropagation();
    drawDrop(null); status('');
    if (!d.mode) { if (selected !== d.pick) select(d.pick); return; }
    if (d.mode === 'reorder' && d.drop) reorder(d.el, d.drop.parent, d.drop.next);
  }
  function block(e) {
    if (!active || mode !== 'edit' || inUI(e)) return;
    const t = fromPath(e);
    if (editing && editing.contains(t)) return;
    e.preventDefault(); e.stopPropagation();
    if (e.type === 'dblclick' && isLayer(t)) {
      const target = t.innerText && t.innerText.trim() ? t : selected;
      if (target) { if (selected !== target) select(target); startEditing(target); }
    }
  }

  function resizeStart(e, dir) {
    if (!selected) return;
    e.preventDefault(); e.stopPropagation();
    const r = selected.getBoundingClientRect();
    drag = { resize: dir, el: selected, x0: e.clientX, y0: e.clientY, w: r.width, h: r.height, gid: nextGid() };
  }
  function resizeMove(e) {
    const d = drag, dir = d.resize;
    let dw = (e.clientX - d.x0) * (dir.includes('e') ? 1 : dir.includes('w') ? -1 : 0);
    let dh = (e.clientY - d.y0) * (dir.includes('s') ? 1 : dir.includes('n') ? -1 : 0);
    if (e.shiftKey && dw && dh) { const k = Math.max((d.w + dw) / d.w, (d.h + dh) / d.h); dw = d.w * k - d.w; dh = d.h * k - d.h; }
    if (dw) setStyle(d.el, 'width', `${Math.max(1, Math.round(d.w + dw))}px`, d.gid);
    if (dh) setStyle(d.el, 'height', `${Math.max(1, Math.round(d.h + dh))}px`, d.gid);
  }

  // ---------- keyboard ----------
  function onKey(e) {
    if (!active) return;
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key === '\\') { e.preventDefault(); setShown(!shown); return; }
    if (inUI(e)) {
      if (e.key === 'Escape') e.target.blur?.();
      return;
    }
    if (editing) {
      if (e.key === 'Escape') { e.preventDefault(); const el = editing; stopEditing(); select(el); }
      return;
    }
    if (mode !== 'edit') return;
    let handled = true;
    const k = e.key;
    if (mod && k.toLowerCase() === 'z') e.shiftKey ? redoOne() : undo();
    else if (mod && k.toLowerCase() === 'y') redoOne();
    else if (mod && k.toLowerCase() === 'd') duplicate(selected);
    else if (mod && k === ']') stepOrder(selected, 1);
    else if (mod && k === '[') stepOrder(selected, -1);
    else if (!selected) handled = false;
    else if (k === 'Escape') select(parentOf(selected));
    else if (k === 'Enter' && e.shiftKey) select(parentOf(selected));
    else if (k === 'Enter') { const c = layerKids(selected)[0]; if (c) select(c); else startEditing(selected); }
    else if (k === 'Tab') { const sib = e.shiftKey ? selected.previousElementSibling : selected.nextElementSibling; if (isLayer(sib)) select(sib); }
    else if (k === 'Delete' || k === 'Backspace') remove(selected);
    else if (k.startsWith('Arrow')) {
      const step = e.shiftKey ? 10 : 1;
      const [x, y] = parseTranslate(selected);
      const dx = k === 'ArrowLeft' ? -step : k === 'ArrowRight' ? step : 0;
      const dy = k === 'ArrowUp' ? -step : k === 'ArrowDown' ? step : 0;
      nudgeGid = e.repeat && nudgeGid ? nudgeGid : nextGid();
      setStyle(selected, 'translate', `${x + dx}px ${y + dy}px`, nudgeGid, 'move');
    } else handled = false;
    if (handled) { e.preventDefault(); e.stopPropagation(); }
  }
  let nudgeGid = null;

  // ---------- UI ----------
  const CSSUI = `
  :host { all: initial; }
  * { box-sizing: border-box; }
  .ui { --bg:#fff; --line:#e6e6e6; --ink:#1e1e1e; --muted:#8c8c8c; --soft:#f5f5f5; --accent:#0d99ff; --accent-soft:#e5f4ff;
    font: 11px/1.45 Inter, -apple-system, "Segoe UI", system-ui, sans-serif; color: var(--ink); }
  .panel { position: fixed; top: 52px; bottom: 10px; width: 260px; background: var(--bg); border: 1px solid var(--line); border-radius: 10px;
    box-shadow: 0 6px 24px rgba(0,0,0,.08); display: flex; flex-direction: column; overflow: hidden; z-index: 3; }
  .left { left: 10px; } .right { right: 10px; width: 272px; }
  .head { padding: 10px 12px; font-weight: 600; border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: 6px; cursor: pointer; user-select: none; }
  .fold { color: var(--muted); font-size: 9px; transition: transform .15s; }
  .panel.folded { bottom: auto; width: auto; min-width: 120px; } .panel.folded .scroll { display: none; } .panel.folded .head { border-bottom: 0; }
  .panel.folded .fold { transform: rotate(-90deg); } .ui[dir=rtl] .panel.folded .fold { transform: rotate(90deg); }
  .scroll { overflow: auto; flex: 1; }
  .bar { position: fixed; top: 10px; left: 50%; transform: translateX(-50%); display: flex; align-items: center; gap: 4px; padding: 4px;
    background: #1e1e1e; color: #fff; border-radius: 10px; box-shadow: 0 6px 24px rgba(0,0,0,.18); z-index: 4; white-space: nowrap; }
  .bar button { background: transparent; color: #fff; border: 0; border-radius: 6px; padding: 6px 10px; font: inherit; cursor: pointer; }
  .bar button:hover { background: #383838; } .bar button.on { background: var(--accent); }
  .bar button:disabled { opacity: .35; cursor: default; background: transparent; }
  .bar .count { color: #b3b3b3; padding: 0 8px; }
  .bar .send { background: var(--accent); font-weight: 600; } .bar .send:hover { background: #0b85e0; }
  .seg { display: flex; background: #2c2c2c; border-radius: 7px; padding: 2px; }
  .sep { width: 1px; height: 18px; background: #444; margin: 0 4px; }
  .row { display: flex; align-items: center; gap: 4px; height: 26px; padding-inline-end: 6px; cursor: default; white-space: nowrap; }
  .row:hover { background: var(--soft); } .row.sel { background: var(--accent-soft); }
  .row.hidden .nm { opacity: .4; }
  .car { width: 14px; text-align: center; color: var(--muted); cursor: pointer; flex: none; font-size: 9px; }
  .ic { width: 14px; text-align: center; color: var(--muted); flex: none; font-weight: 600; }
  .nm { text-align: start; overflow: hidden; text-overflow: ellipsis; flex: 1; }
  .eye { opacity: 0; cursor: pointer; padding: 0 4px; color: var(--muted); } .row:hover .eye, .row.hidden .eye { opacity: 1; }
  .sec { border-bottom: 1px solid var(--line); padding: 8px 12px 10px; }
  .sec h4 { margin: 0 0 6px; font-size: 11px; font-weight: 600; display: flex; justify-content: space-between; align-items: center; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; } .grid4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
  .f { display: flex; align-items: center; height: 28px; background: var(--soft); border: 1px solid transparent; border-radius: 5px; min-width: 0; }
  .f:hover { border-color: var(--line); } .f:focus-within { border-color: var(--accent); background: #fff; }
  .f label { color: var(--muted); padding: 0 6px; cursor: ew-resize; user-select: none; flex: none; font-size: 10px; min-width: 18px; text-align: center; }
  .f input, .f select { border: 0; background: transparent; font: inherit; color: inherit; width: 100%; min-width: 0; height: 100%; outline: none; padding: 0 6px 0 0; }
  .f select { padding: 0 4px; } .f input[type=color] { width: 22px; height: 18px; padding: 0; margin: 0 4px; flex: none; border-radius: 3px; cursor: pointer; }
  .full { grid-column: 1 / -1; }
  .title { padding: 10px 12px; border-bottom: 1px solid var(--line); }
  .title b { display: block; text-align: start; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .title code { display: block; color: var(--muted); font: 10px ui-monospace, Menlo, monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; direction: ltr; text-align: start; margin-top: 2px; }
  .acts { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
  .acts button { white-space: nowrap; }
  .acts button, .link { border: 1px solid var(--line); background: #fff; border-radius: 5px; padding: 4px 8px; font: inherit; cursor: pointer; color: inherit; }
  .acts button:hover, .link:hover { border-color: var(--ink); }
  .link { border: 0; color: var(--accent); padding: 2px 0; background: none; }
  textarea { width: 100%; min-height: 64px; resize: vertical; border: 1px solid var(--line); border-radius: 6px; padding: 6px 8px; font: inherit; color: inherit; outline: none; }
  textarea:focus { border-color: var(--accent); }
  .empty { padding: 14px 12px; color: var(--muted); white-space: pre-line; }
  .presets { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px; }
  .presets button { border: 1px solid var(--line); background: #fff; border-radius: 4px; padding: 2px 6px; font: inherit; cursor: pointer; }
  .box { position: fixed; pointer-events: none; z-index: 1; }
  .hov { outline: 1px solid var(--accent); } .selb { outline: 2px solid var(--accent); } .par { outline: 1px dashed rgba(13,153,255,.55); }
  .tag { position: fixed; z-index: 2; background: var(--accent); color: #fff; font-size: 10px; padding: 1px 5px; border-radius: 3px; pointer-events: none; white-space: nowrap; direction: ltr; }
  .h { position: fixed; width: 8px; height: 8px; background: #fff; border: 1px solid var(--accent); z-index: 2; pointer-events: auto; }
  .drop { position: fixed; background: var(--accent); z-index: 2; pointer-events: none; border-radius: 2px; }
  .status { position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%); background: #1e1e1e; color: #fff; padding: 6px 12px; border-radius: 8px; z-index: 4; pointer-events: none; }
  .toast { position: fixed; top: 60px; left: 50%; transform: translateX(-50%); background: #14ae5c; color: #fff; padding: 10px 16px; border-radius: 8px; z-index: 5; font-weight: 600; font-size: 13px; }
  .collapsed .panel, .collapsed .box, .collapsed .tag, .collapsed .h { display: none; }
  .off { display: none !important; }
  .ui[dir=rtl] .nm, .ui[dir=rtl] .title b { text-align: right; }
  `;

  const h = (tag, attrs = {}, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else if (k === 'class') el.className = v;
      else if (v != null && v !== false) el.setAttribute(k, v === true ? '' : v);
    }
    for (const k of kids.flat()) if (k != null && k !== false) el.append(k.nodeType ? k : document.createTextNode(k));
    return el;
  };

  function buildUI() {
    host = document.createElement('live-edit-ui');
    host.style.cssText = 'all: initial; position: fixed; inset: 0; pointer-events: none; z-index: 2147483647;';
    root = host.attachShadow({ mode: 'open' });
    root.append(h('style', {}, CSSUI));
    const wrap = h('div', { class: 'ui', dir: HE ? 'rtl' : 'ltr' });
    root.append(wrap);
    const pe = (el) => { el.style.pointerEvents = 'auto'; return el; };

    ui.modeEdit = h('button', { onclick: () => setMode('edit') }, STR.edit);
    ui.modeInt = h('button', { onclick: () => setMode('interact') }, STR.interact);
    ui.undo = h('button', { title: '⌘Z', onclick: undo }, '↶');
    ui.redo = h('button', { title: '⇧⌘Z', onclick: redoOne }, '↷');
    ui.count = h('span', { class: 'count' }, STR.changes(0));
    ui.send = h('button', { class: 'send', onclick: sendAll }, STR.send + ' ✓');
    wrap.append(pe(h('div', { class: 'bar', dir: HE ? 'rtl' : 'ltr' },
      h('div', { class: 'seg' }, ui.modeEdit, ui.modeInt), h('span', { class: 'sep' }), ui.undo, ui.redo,
      h('button', { title: STR.hideUI, onclick: () => setShown(!shown) }, '◫'), ui.count, ui.send)));

    ui.tree = h('div', { class: 'scroll' });
    const fold = (e) => e.currentTarget.parentElement.classList.toggle('folded');
    ui.left = pe(h('div', { class: 'panel left' }, h('div', { class: 'head', title: STR.fold, onclick: fold }, h('span', { class: 'fold' }, '▾'), STR.layers), ui.tree));
    ui.props = h('div', { class: 'scroll' });
    ui.right = pe(h('div', { class: 'panel right' }, h('div', { class: 'head', title: STR.fold, onclick: fold }, h('span', { class: 'fold' }, '▾'), STR.design), ui.props));
    wrap.append(ui.left, ui.right);

    ui.par = h('div', { class: 'box par' }); ui.hov = h('div', { class: 'box hov' }); ui.sel = h('div', { class: 'box selb' });
    ui.tag = h('div', { class: 'tag' }); ui.drop = h('div', { class: 'drop off' });
    ui.handles = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'].map((d) => {
      const el = pe(h('div', { class: 'h', 'data-d': d }));
      el.style.cursor = { n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize', ne: 'nesw-resize', sw: 'nesw-resize', nw: 'nwse-resize', se: 'nwse-resize' }[d];
      el.addEventListener('pointerdown', (e) => resizeStart(e, d));
      return el;
    });
    ui.status = h('div', { class: 'status off' });
    ui.toast = h('div', { class: 'toast off' });
    wrap.append(ui.par, ui.hov, ui.sel, ui.tag, ui.drop, ...ui.handles, ui.status, ui.toast);
    ui.wrap = wrap;
    document.documentElement.append(host);
  }

  function setMode(m) {
    mode = m;
    if (m !== 'edit') { if (editing) stopEditing(); hovered = null; }
    refreshUI();
  }
  function setShown(v) { shown = v; ui.wrap.classList.toggle('collapsed', !v); }
  function status(text) { if (!ui.status) return; ui.status.textContent = text; ui.status.classList.toggle('off', !text); }
  function toast(text, ms = 2500) {
    ui.toast.textContent = text; ui.toast.classList.remove('off');
    clearTimeout(toastTimer);
    if (ms) toastTimer = setTimeout(() => ui.toast.classList.add('off'), ms);
  }
  function sendAll() {
    if (editing) stopEditing();
    if (document.activeElement === host) root.activeElement?.blur?.();
    sent = true;
    save(true);
    toast(STR.sent, 0);
  }

  function refreshUI(structural) {
    if (!ui.count) return;
    ui.modeEdit.classList.toggle('on', mode === 'edit');
    ui.modeInt.classList.toggle('on', mode === 'interact');
    ui.undo.disabled = !ops.length; ui.redo.disabled = !redo.length;
    ui.count.textContent = STR.changes(changeCount());
    if (structural) { renderTree(); renderProps(); } else updateFields();
  }

  // ----- layers -----
  function iconOf(el) {
    if (IMAGE.has(el.tagName)) return '◩';
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return '▭';
    if (!layerKids(el).length && el.innerText && el.innerText.trim()) return 'T';
    const d = getComputedStyle(el).display;
    if (d.includes('flex')) return getComputedStyle(el).flexDirection.startsWith('column') ? '☰' : '⫼';
    if (d.includes('grid')) return '▦';
    return '#';
  }
  function renderTree() {
    if (!ui.tree) return;
    const frag = document.createDocumentFragment();
    let rows = 0;
    const walk = (el, depth) => {
      if (rows++ > 2500) return;
      const kids = layerKids(el);
      const open = expanded.has(el);
      const hidden = getComputedStyle(el).display === 'none';
      const row = h('div', { class: 'row' + (el === selected ? ' sel' : '') + (hidden ? ' hidden' : '') });
      row.style.paddingInlineStart = `${6 + depth * 12}px`;
      row.append(
        h('span', { class: 'car', onclick: (e) => { e.stopPropagation(); open ? expanded.delete(el) : expanded.add(el); renderTree(); } }, kids.length ? (open ? '▾' : (HE ? '◂' : '▸')) : ''),
        h('span', { class: 'ic' }, iconOf(el)),
        h('span', { class: 'nm', dir: 'auto', title: nameOf(el) }, nameOf(el)),
      );
      if (el !== document.body) row.append(h('span', { class: 'eye', title: STR.hide, onclick: (e) => { e.stopPropagation(); toggleHide(el); } }, hidden ? '◌' : '◉'));
      row.addEventListener('click', () => select(el, true));
      row.addEventListener('mouseenter', () => { hovered = el; });
      row.addEventListener('mouseleave', () => { hovered = null; });
      frag.append(row);
      if (open) kids.forEach((k) => walk(k, depth + 1));
    };
    expanded.add(document.body);
    walk(document.body, 0);
    const top = ui.tree.scrollTop;
    ui.tree.replaceChildren(frag);
    ui.tree.scrollTop = top;
  }

  // ----- design panel -----
  let fields = [];
  const cs = () => getComputedStyle(selected);
  const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? +n.toFixed(2) : ''; };
  const toCss = (raw, unit = 'px') => {
    const s = String(raw).trim();
    if (s === '') return '';
    return /^-?\d*\.?\d+$/.test(s) ? s + unit : s;
  };

  // A Figma-style number field: type a value, scrub the label left and right, or use arrow keys.
  function numField({ label, title, get, set, unit = 'px', step = 1, cls = '' }) {
    const input = h('input', { type: 'text', spellcheck: 'false' });
    const lab = h('label', { title: title || '' }, label);
    let gid = null;
    const commit = (v) => { set(v, gid); };
    input.addEventListener('focus', () => { gid = nextGid(); input.select(); });
    input.addEventListener('change', () => { commit(toCss(input.value, unit)); gid = nextGid(); });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { input.blur(); return; }
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
      e.preventDefault();
      const n = (parseFloat(input.value) || 0) + (e.key === 'ArrowUp' ? 1 : -1) * step * (e.shiftKey ? 10 : 1);
      input.value = +n.toFixed(2);
      commit(toCss(input.value, unit));
    });
    lab.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      const x0 = e.clientX, v0 = parseFloat(input.value) || 0, g = nextGid();
      const mv = (ev) => { const n = v0 + Math.round((ev.clientX - x0) / 2) * step * (ev.shiftKey ? 10 : 1); input.value = +n.toFixed(2); set(toCss(input.value, unit), g); };
      const up = () => { removeEventListener('pointermove', mv, true); removeEventListener('pointerup', up, true); };
      addEventListener('pointermove', mv, true); addEventListener('pointerup', up, true);
    });
    const el = h('div', { class: 'f ' + cls, title: title || '' }, lab, input);
    fields.push({ input, update: () => { if (root.activeElement !== input) input.value = get(); } });
    return el;
  }
  function textField({ label, title, get, set, cls = '', list }) {
    const input = h('input', { type: 'text', spellcheck: 'false', list: list || null });
    let gid = null;
    input.addEventListener('focus', () => { gid = nextGid(); });
    input.addEventListener('change', () => { set(input.value.trim(), gid); gid = nextGid(); });
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') input.blur(); });
    const el = h('div', { class: 'f ' + cls, title: title || '' }, label ? h('label', {}, label) : null, input);
    fields.push({ input, update: () => { if (root.activeElement !== input) input.value = get(); } });
    return el;
  }
  function selectField({ label, title, options, get, set, cls = '' }) {
    const sel = h('select', { onchange: () => set(sel.value, nextGid()) }, options.map((o) => h('option', { value: Array.isArray(o) ? o[0] : o }, Array.isArray(o) ? o[1] : o)));
    const el = h('div', { class: 'f ' + cls, title: title || '' }, label ? h('label', {}, label) : null, sel);
    fields.push({ input: sel, update: () => {
      const v = get();
      if (![...sel.options].some((o) => o.value === v)) sel.append(h('option', { value: v }, v));
      sel.value = v;
    } });
    return el;
  }
  function colorField({ get, set, cls = 'full' }) {
    const pick = h('input', { type: 'color' });
    const text = h('input', { type: 'text', spellcheck: 'false' });
    let gid = null;
    pick.addEventListener('focus', () => { gid = nextGid(); });
    pick.addEventListener('input', () => { text.value = pick.value.toUpperCase(); set(pick.value.toUpperCase(), gid); });
    text.addEventListener('focus', () => { gid = nextGid(); });
    text.addEventListener('change', () => { set(text.value.trim(), gid); });
    text.addEventListener('keydown', (e) => { if (e.key === 'Enter') text.blur(); });
    fields.push({ input: text, update: () => {
      const v = rgbHex(get());
      if (root.activeElement !== text) text.value = v === 'rgba(0, 0, 0, 0)' || v === '#00000000' ? 'transparent' : v;
      if (/^#[0-9A-F]{6}/i.test(v)) pick.value = v.slice(0, 7).toLowerCase();
    } });
    return h('div', { class: 'f ' + cls }, pick, text);
  }
  const prop = (name, unit) => ({
    get: () => num(cs().getPropertyValue(name)),
    set: (v, g) => setStyle(selected, name, toCss(v, unit), g),
    unit,
  });
  const raw = (name) => ({ get: () => cs().getPropertyValue(name), set: (v, g) => setStyle(selected, name, v, g) });

  function section(title, ...kids) { return h('div', { class: 'sec' }, h('h4', {}, ...[].concat(title)), ...kids); }
  function fontList() {
    const set = new Set(['Inter', 'system-ui', 'Helvetica Neue', 'Arial', 'Georgia', 'Times New Roman', 'ui-monospace']);
    try { document.fonts.forEach((f) => set.add(f.family.replace(/["']/g, ''))); } catch {}
    for (const el of [document.body, ...document.body.querySelectorAll('h1,h2,h3,p,button,a')].slice(0, 60)) {
      set.add(getComputedStyle(el).fontFamily.split(',')[0].replace(/["']/g, '').trim());
    }
    return [...set].filter(Boolean);
  }

  function renderProps() {
    if (!ui.props) return;
    fields = [];
    const el = selected;
    if (!el) {
      const ta = h('textarea', { placeholder: STR.pageNotePh, oninput: () => { pageNote = ta.value; refreshUI(); scheduleSave(); } });
      ta.value = pageNote;
      ui.props.replaceChildren(h('div', { class: 'empty' }, STR.empty), section(STR.pageNote, ta));
      return;
    }
    const s = cs();
    const isFlex = s.display.includes('flex') || s.display.includes('grid');
    const hasText = !!(el.innerText && el.innerText.trim());
    const out = [];

    out.push(h('div', { class: 'title' }, h('b', { dir: 'auto' }, nameOf(el)), h('code', { title: selOf(el) }, selOf(el)),
      h('div', { class: 'acts' },
        h('button', { title: 'Esc', onclick: () => select(parentOf(el)) }, '↑ ' + STR.parent),
        h('button', { title: '⌘D', onclick: () => duplicate(el) }, STR.dup),
        h('button', { onclick: () => toggleHide(el) }, STR.hide),
        h('button', { title: 'Delete', onclick: () => remove(el) }, STR.del))));

    const tx = { get: () => parseTranslate(selected)[0], set: (v, g) => { const [, y] = parseTranslate(selected); setStyle(selected, 'translate', `${parseFloat(v) || 0}px ${y}px`, g, 'move'); } };
    const ty = { get: () => parseTranslate(selected)[1], set: (v, g) => { const [x] = parseTranslate(selected); setStyle(selected, 'translate', `${x}px ${parseFloat(v) || 0}px`, g, 'move'); } };
    out.push(section(STR.position, h('div', { class: 'grid' },
      numField({ label: 'X', title: 'translate x', ...tx }), numField({ label: 'Y', title: 'translate y', ...ty }),
      numField({ label: '⟳', title: 'rotate', get: () => num(cs().rotate) || 0, set: (v, g) => setStyle(selected, 'rotate', toCss(v, 'deg'), g), unit: 'deg' }),
      selectField({ label: '⌖', title: 'position', options: ['static', 'relative', 'absolute', 'fixed', 'sticky'], ...raw('position') }))));

    const size = (name) => ({
      get: () => Math.round(selected.getBoundingClientRect()[name]),
      set: (v, g) => setStyle(selected, name, toCss(v), g),
    });
    out.push(section(STR.layout,
      h('div', { class: 'grid' },
        numField({ label: 'W', title: 'width (px, %, auto, fit-content)', ...size('width') }),
        numField({ label: 'H', title: 'height (px, %, auto)', ...size('height') }),
        numField({ label: 'min', title: 'min-width', ...prop('min-width', 'px') }),
        numField({ label: 'max', title: 'max-width', get: () => { const v = cs().maxWidth; return v === 'none' ? 'none' : num(v); }, set: (v, g) => setStyle(selected, 'max-width', toCss(v), g) }),
        selectField({ label: 'D', title: 'display', options: ['block', 'inline-block', 'inline', 'flex', 'inline-flex', 'grid', 'none', 'contents'], ...raw('display'), cls: 'full' }))));

    const autoHead = [STR.auto, isFlex
      ? h('button', { class: 'link', onclick: () => setStyle(selected, 'display', 'block', nextGid()) }, STR.removeAuto)
      : h('button', { class: 'link', onclick: () => { const g = nextGid(); setStyle(selected, 'display', 'flex', g); setStyle(selected, 'flex-direction', 'column', g); renderProps(); } }, STR.addAuto)];
    out.push(section(autoHead, isFlex ? h('div', { class: 'grid' },
      selectField({ label: '→', title: 'flex-direction', options: [['row', HE ? 'אופקי' : 'Horizontal'], ['column', HE ? 'אנכי' : 'Vertical'], 'row-reverse', 'column-reverse'], ...raw('flex-direction') }),
      numField({ label: 'gap', title: 'gap', get: () => num(cs().rowGap) || num(cs().columnGap) || 0, set: (v, g) => setStyle(selected, 'gap', toCss(v), g) }),
      selectField({ label: '⇹', title: 'justify-content', options: ['normal', 'flex-start', 'center', 'flex-end', 'space-between', 'space-around', 'space-evenly'], ...raw('justify-content') }),
      selectField({ label: '⇳', title: 'align-items', options: ['normal', 'stretch', 'flex-start', 'center', 'flex-end', 'baseline'], ...raw('align-items') }),
      selectField({ label: '↵', title: 'flex-wrap', options: ['nowrap', 'wrap'], ...raw('flex-wrap') }),
      s.display.includes('grid') ? textField({ label: 'cols', title: 'grid-template-columns', ...raw('grid-template-columns') }) : selectField({ label: '◫', title: 'align-self / flex child', options: ['auto', 'stretch', 'flex-start', 'center', 'flex-end'], ...raw('align-self') })) : null));

    const four = (base, title) => h('div', { class: 'grid4' }, ['top', 'right', 'bottom', 'left'].map((side) =>
      numField({ label: { top: '↑', right: '→', bottom: '↓', left: '←' }[side], title: `${base}-${side}`, ...prop(`${base}-${side}`, 'px') })));
    out.push(section(STR.padding, four('padding')));
    out.push(section(STR.margin, four('margin')));

    out.push(section(STR.appearance, h('div', { class: 'grid' },
      numField({ label: '%', title: 'opacity', get: () => Math.round(parseFloat(cs().opacity) * 100), set: (v, g) => setStyle(selected, 'opacity', String((parseFloat(v) || 0) / 100), g), unit: '' }),
      numField({ label: '◜', title: 'border-radius', get: () => num(cs().borderTopLeftRadius), set: (v, g) => setStyle(selected, 'border-radius', toCss(v), g) }),
      selectField({ label: '⧉', title: 'overflow', options: ['visible', 'hidden', 'auto', 'clip'], ...raw('overflow') }),
      numField({ label: 'z', title: 'z-index', get: () => cs().zIndex, set: (v, g) => setStyle(selected, 'z-index', String(v), g), unit: '' }))));

    out.push(section(STR.fill, h('div', { class: 'grid' },
      colorField({ ...raw('background-color') }),
      textField({ label: '∇', title: 'background (gradient or image)', get: () => cs().backgroundImage, set: (v, g) => setStyle(selected, 'background-image', v, g), cls: 'full' }))));

    out.push(section(STR.stroke, h('div', { class: 'grid' },
      numField({ label: 'W', title: 'border-width', get: () => num(cs().borderTopWidth), set: (v, g) => { setStyle(selected, 'border-width', toCss(v), g); if (cs().borderTopStyle === 'none') setStyle(selected, 'border-style', 'solid', g); } }),
      selectField({ label: '┄', title: 'border-style', options: ['none', 'solid', 'dashed', 'dotted', 'double'], get: () => cs().borderTopStyle, set: (v, g) => setStyle(selected, 'border-style', v, g) }),
      colorField({ get: () => cs().borderTopColor, set: (v, g) => setStyle(selected, 'border-color', v, g) }))));

    const shadow = textField({ label: '◐', title: 'box-shadow', ...raw('box-shadow'), cls: 'full' });
    const presets = h('div', { class: 'presets' }, [
      [STR.none, 'none'], ['S', '0 1px 3px rgba(0,0,0,.12)'], ['M', '0 6px 16px -4px rgba(0,0,0,.16)'], ['L', '0 18px 40px -12px rgba(0,0,0,.28)'],
    ].map(([l, v]) => h('button', { onclick: () => setStyle(selected, 'box-shadow', v, nextGid()) }, l)));
    out.push(section(STR.effects, h('div', { class: 'grid' }, shadow,
      textField({ label: 'blur', title: 'filter', ...raw('filter') }),
      textField({ label: 'bg', title: 'backdrop-filter', ...raw('backdrop-filter') })), presets));

    if (hasText) {
      const dl = h('datalist', { id: 'le-fonts' }, fontList().map((f) => h('option', { value: f })));
      out.push(section(STR.text, dl, h('div', { class: 'grid' },
        textField({ label: 'Aa', title: 'font-family', list: 'le-fonts', get: () => cs().fontFamily.split(',')[0].replace(/["']/g, '').trim(), set: (v, g) => setStyle(selected, 'font-family', /[\s,]/.test(v) && !/["',]/.test(v) ? `"${v}"` : v, g), cls: 'full' }),
        numField({ label: 'size', title: 'font-size', ...prop('font-size', 'px') }),
        selectField({ label: 'wt', title: 'font-weight', options: ['100', '200', '300', '400', '500', '600', '700', '800', '900'], ...raw('font-weight') }),
        numField({ label: 'lh', title: 'line-height (number = multiplier)', get: () => { const v = cs().lineHeight; return v === 'normal' ? 'normal' : num(v); }, set: (v, g) => setStyle(selected, 'line-height', toCss(v), g) }),
        numField({ label: 'ls', title: 'letter-spacing', get: () => { const v = cs().letterSpacing; return v === 'normal' ? 0 : num(v); }, set: (v, g) => setStyle(selected, 'letter-spacing', toCss(v), g), step: 0.1 }),
        selectField({ label: '≡', title: 'text-align', options: ['start', 'left', 'center', 'right', 'end', 'justify'], ...raw('text-align') }),
        selectField({ label: 'Tt', title: 'text-transform', options: ['none', 'uppercase', 'lowercase', 'capitalize'], ...raw('text-transform') }),
        selectField({ label: 'I', title: 'font-style', options: ['normal', 'italic'], ...raw('font-style') }),
        selectField({ label: 'U', title: 'text-decoration-line', options: ['none', 'underline', 'line-through'], ...raw('text-decoration-line') }),
        colorField({ ...raw('color') }))));
    }
    if (el.tagName === 'IMG') {
      const attr = (name) => ({ get: () => el.getAttribute(name) || '', set: (v, g) => push({ type: 'attr', el: selected, name, before: selected.getAttribute(name), after: v, gid: g }) });
      out.push(section(STR.image, h('div', { class: 'grid' },
        textField({ label: 'src', ...attr('src'), cls: 'full' }), textField({ label: 'alt', ...attr('alt'), cls: 'full' }),
        selectField({ label: 'fit', title: 'object-fit', options: ['fill', 'contain', 'cover', 'none', 'scale-down'], ...raw('object-fit'), cls: 'full' }))));
    }

    const ta = h('textarea', { placeholder: STR.intentPh, oninput: () => { notes.set(el, ta.value); refreshUI(); scheduleSave(); } });
    ta.value = notes.get(el) || '';
    out.push(section(STR.intent, ta));

    const top = ui.props.scrollTop;
    ui.props.replaceChildren(...out);
    ui.props.scrollTop = top;
    updateFields();
  }
  function updateFields() {
    if (!selected) return;
    for (const f of fields) { try { f.update(); } catch {} }
  }

  // ----- overlay boxes, redrawn every frame -----
  const place = (box, r) => { box.style.left = r.left + 'px'; box.style.top = r.top + 'px'; box.style.width = r.width + 'px'; box.style.height = r.height + 'px'; };
  function drawDrop(d) {
    if (!d) { ui.drop.classList.add('off'); return; }
    const r = d.rect, vertical = d.axis === 'y';
    ui.drop.classList.remove('off');
    if (vertical) place(ui.drop, { left: r.left, top: (d.after ? r.bottom : r.top) - 1, width: r.width, height: 3 });
    else place(ui.drop, { left: (d.after ? r.right : r.left) - 1, top: r.top, width: 3, height: r.height });
  }
  function frame() {
    requestAnimationFrame(frame);
    if (!ui.sel || !active) return;
    const showSel = mode === 'edit' && selected && selected.isConnected;
    const showHov = mode === 'edit' && hovered && hovered !== selected && hovered.isConnected && !drag;
    ui.hov.classList.toggle('off', !showHov);
    if (showHov) place(ui.hov, hovered.getBoundingClientRect());
    ui.sel.classList.toggle('off', !showSel);
    ui.tag.classList.toggle('off', !showSel);
    ui.par.classList.toggle('off', !(showSel && parentOf(selected)));
    ui.handles.forEach((x) => x.classList.toggle('off', !showSel || !!editing));
    if (!showSel) return;
    const r = selected.getBoundingClientRect();
    place(ui.sel, r);
    if (parentOf(selected)) place(ui.par, parentOf(selected).getBoundingClientRect());
    ui.tag.textContent = `${Math.round(r.width)} × ${Math.round(r.height)}`;
    ui.tag.style.left = r.left + r.width / 2 - ui.tag.offsetWidth / 2 + 'px';
    ui.tag.style.top = r.bottom + 6 + 'px';
    const pts = { nw: [r.left, r.top], n: [r.left + r.width / 2, r.top], ne: [r.right, r.top], e: [r.right, r.top + r.height / 2],
      se: [r.right, r.bottom], s: [r.left + r.width / 2, r.bottom], sw: [r.left, r.bottom], w: [r.left, r.top + r.height / 2] };
    for (const hd of ui.handles) { const [x, y] = pts[hd.dataset.d]; hd.style.left = x - 4 + 'px'; hd.style.top = y - 4 + 'px'; }
  }

  // ---------- start ----------
  function start() {
    if (!document.body) return;
    buildUI();
    for (const t of ['click', 'dblclick', 'mousedown', 'mouseup', 'auxclick', 'contextmenu', 'submit', 'touchstart', 'dragstart']) addEventListener(t, block, true);
    addEventListener('pointerdown', onPointerDown, true);
    addEventListener('pointermove', onPointerMove, true);
    addEventListener('pointerup', onPointerUp, true);
    addEventListener('keydown', onKey, true);
    addEventListener('beforeunload', (e) => { if (ops.length && !sent) { e.preventDefault(); e.returnValue = STR.leave; } });
    if (!CFG.waitForReady) ready();
    else wrapVisible(false);
    requestAnimationFrame(frame);
  }
  function wrapVisible(v) { if (ui.wrap) ui.wrap.style.display = v ? '' : 'none'; }
  function ready() { active = true; wrapVisible(true); renderTree(); renderProps(); refreshUI(); }

  window.__liveEdit = {
    ready,
    // edit.mjs hides the editor while it takes the before/after screenshots
    chrome: (v) => { wrapVisible(v); if (!v) { hovered = null; } },
    sentToast: () => toast(STR.sent, 0),
    report,
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
