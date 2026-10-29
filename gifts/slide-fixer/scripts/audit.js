/* Slide layout audit. Runs inside the deck page (any HTML/React deck).
   window.__slideAudit()               -> report object for the slide(s) visible now
   window.__slideAudit({overlay:true}) -> also outlines problems on screen, with a copy button
   It only measures. It never changes the deck. */
(function () {
  if (window.__slideAudit) return;

  var EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F000}-\u{1F2FF}]/u;

  function vis(el) {
    var cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function sel(el) {
    var parts = [];
    while (el && el.nodeType === 1 && parts.length < 4) {
      var s = el.tagName.toLowerCase();
      if (el.id) { parts.unshift(s + '#' + el.id); break; }
      var c = (el.className && typeof el.className === 'string') ? el.className.trim().split(/\s+/).slice(0, 2).join('.') : '';
      if (c) s += '.' + c;
      var p = el.parentElement;
      if (p) { var sib = [].filter.call(p.children, function (x) { return x.tagName === el.tagName; }); if (sib.length > 1) s += ':nth-of-type(' + (sib.indexOf(el) + 1) + ')'; }
      parts.unshift(s); el = el.parentElement;
    }
    return parts.join(' > ');
  }
  function snippet(el) { return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 50); }
  function inter(a, b) {
    var w = Math.min(a.right, b.right) - Math.max(a.left, b.left), h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    return w > 0 && h > 0 ? w * h : 0;
  }
  function textRect(el) {
    // bounds of the element's own text, not its box
    var rects = [];
    el.childNodes.forEach(function (n) {
      if (n.nodeType === 3 && n.textContent.trim()) {
        var rg = document.createRange(); rg.selectNodeContents(n);
        [].forEach.call(rg.getClientRects(), function (r) { if (r.width && r.height) rects.push(r); });
      }
    });
    if (!rects.length) return null;
    return rects.reduce(function (a, r) {
      return { left: Math.min(a.left, r.left), top: Math.min(a.top, r.top), right: Math.max(a.right, r.right), bottom: Math.max(a.bottom, r.bottom) };
    }, { left: 1e9, top: 1e9, right: -1e9, bottom: -1e9 });
  }
  function rel(r, S) { return { x: Math.round(r.left - S.left), y: Math.round(r.top - S.top), w: Math.round(r.right - r.left), h: Math.round(r.bottom - r.top) }; }

  // ---- find slides ----
  function findSlides() {
    var cands = [].slice.call(document.querySelectorAll('[class*="slide" i],[data-slide],section,[role="group"]')).filter(function (el) {
      if (!vis(el)) return false;
      var r = el.getBoundingClientRect(), ar = r.width / r.height;
      return r.width >= 480 && ar > 1.2 && ar < 2.0;
    });
    // keep outermost slide-like boxes that are not containers of other candidates of the same size
    cands = cands.filter(function (el) {
      return !cands.some(function (o) { return o !== el && el.contains(o) && Math.abs(o.getBoundingClientRect().width - el.getBoundingClientRect().width) < 4; });
    });
    cands = cands.filter(function (el) { return !cands.some(function (o) { return o !== el && o.contains(el); }); });
    if (!cands.length) cands = [document.body];
    return cands;
  }

  function auditSlide(S, idx) {
    var R = S.getBoundingClientRect(), W = R.width, H = R.height, issues = [];
    function add(type, sev, el, msg, rect) { issues.push({ type: type, severity: sev, selector: el ? sel(el) : '', text: el ? snippet(el) : '', message: msg, rect: rect ? rel(rect, R) : (el ? rel(el.getBoundingClientRect(), R) : null) }); if (el) el.__auditFlag = sev; }

    var all = [].slice.call(S.querySelectorAll('*')).filter(vis);
    var texts = [], media = [], icons = [];
    all.forEach(function (el) {
      var tag = el.tagName.toLowerCase(), r = el.getBoundingClientRect();
      if (el.closest('svg') && tag !== 'svg') return;
      var isIconish = /icon|lucide|fa-|material|bi-/i.test(typeof el.className === 'string' ? el.className : (el.getAttribute('class') || ''));
      if (tag === 'svg' || tag === 'img' || tag === 'i' && isIconish) {
        if (Math.max(r.width, r.height) <= 96 || isIconish) icons.push(el); else media.push(el);
        return;
      }
      if (tag === 'video' || tag === 'canvas' || tag === 'picture') { media.push(el); return; }
      var bg = getComputedStyle(el).backgroundImage;
      if (bg && bg.indexOf('url(') > -1 && r.width * r.height > 0.04 * W * H) media.push(el);
      var tr = textRect(el);
      var fsz = parseFloat(getComputedStyle(el).fontSize);
      if (tr) { var ins = Math.min(0.2 * fsz, (tr.bottom - tr.top) / 4); tr = { left: tr.left, right: tr.right, top: tr.top + ins, bottom: tr.bottom - ins }; }
      if (tr) texts.push({ el: el, r: tr, fs: fsz, len: snippet(el).length, fw: +getComputedStyle(el).fontWeight || 400 });
    });

    // 1. outside the slide / clipped
    texts.forEach(function (t) {
      if (t.r.left < R.left - 1 || t.r.right > R.right + 1 || t.r.top < R.top - 1 || t.r.bottom > R.bottom + 1) add('out-of-slide', 'high', t.el, 'Text runs past the slide edge', t.r);
    });
    all.forEach(function (el) {
      var cs = getComputedStyle(el);
      if ((cs.overflow === 'hidden' || cs.overflowY === 'hidden' || cs.textOverflow === 'ellipsis') && (el.scrollHeight > el.clientHeight + 2 || el.scrollWidth > el.clientWidth + 2) && snippet(el).length > 0 && el !== S)
        add('clipped', 'high', el, 'Text is cut off inside its box (' + el.scrollHeight + 'px content in ' + el.clientHeight + 'px)');
    });

    // 2. overlaps
    for (var i = 0; i < texts.length; i++) for (var j = i + 1; j < texts.length; j++) {
      var a = texts[i], b = texts[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      // a 1-2 character glyph much bigger than its neighbour is decoration (a quote mark, a big number)
      if ((a.len <= 2 && a.fs > 2 * b.fs) || (b.len <= 2 && b.fs > 2 * a.fs)) continue;
      var ov = inter(a.r, b.r), small = Math.min((a.r.right - a.r.left) * (a.r.bottom - a.r.top), (b.r.right - b.r.left) * (b.r.bottom - b.r.top));
      if (ov > 0.08 * small) add('overlap-text', 'high', a.el, 'Text overlaps other text: "' + snippet(b.el) + '"', a.r);
    }
    var big = function (m) { var r = m.getBoundingClientRect(); return r.width * r.height > 0.6 * W * H; };
    texts.forEach(function (t) {
      media.forEach(function (m) {
        if (m.contains(t.el) || big(m)) return; // text inside a background card or over a full background is intended
        var mr = m.getBoundingClientRect(), ov = inter(t.r, mr), ta = (t.r.right - t.r.left) * (t.r.bottom - t.r.top);
        if (ov > 0.1 * ta) add('overlap-image', 'high', t.el, 'Text sits on top of an image', t.r);
      });
      icons.forEach(function (ic) {
        var ir = ic.getBoundingClientRect(), ov = inter(t.r, ir);
        if (ov > 0.25 * ir.width * ir.height && !t.el.contains(ic)) add('overlap-icon', 'medium', ic, 'Icon overlaps text "' + snippet(t.el) + '"');
      });
    });
    for (var m1 = 0; m1 < media.length; m1++) for (var m2 = m1 + 1; m2 < media.length; m2++) {
      var A = media[m1], B = media[m2]; if (A.contains(B) || B.contains(A) || big(A) || big(B)) continue;
      var ra = A.getBoundingClientRect(), rb = B.getBoundingClientRect();
      if (inter(ra, rb) > 0.05 * Math.min(ra.width * ra.height, rb.width * rb.height)) add('overlap-media', 'medium', A, 'Two images overlap');
    }

    // 3. type hierarchy
    var sizes = {}; texts.forEach(function (t) { var k = Math.round(t.fs); sizes[k] = (sizes[k] || 0) + t.len; });
    var keys = Object.keys(sizes).map(Number).sort(function (x, y) { return y - x; });
    var topTexts = texts.filter(function (t) { return t.r.top - R.top < H * 0.4 && t.len > 2; });
    var title = (topTexts.length ? topTexts : texts).slice().sort(function (x, y) { return y.fs - x.fs || x.r.top - y.r.top; })[0];
    var bodyFs = keys.length ? keys.slice().sort(function (x, y) { return sizes[y] - sizes[x]; })[0] : 0;
    var info = { titleSize: title ? Math.round(title.fs) : null, titleTop: title ? Math.round(title.r.top - R.top) : null, titleLeft: title ? Math.round(title.r.left - R.left) : null, titleRight: title ? Math.round(R.right - title.r.right) : null, bodySize: bodyFs, sizes: keys, slideWidth: Math.round(W) };
    if (title && bodyFs && title.fs !== bodyFs) {
      var ratio = title.fs / bodyFs; info.titleToBody = +ratio.toFixed(2);
      if (ratio < 1.5) add('weak-hierarchy', 'medium', title.el, 'Title is only ' + ratio.toFixed(2) + 'x the body text; it does not read as a title');
      if (ratio > 4.5 && title.len > 12) add('title-too-big', 'low', title.el, 'Title is ' + ratio.toFixed(2) + 'x the body; it dominates the slide');
    }
    var mids = keys.filter(function (k) { return title && k < title.fs && (k > bodyFs || bodyFs === Math.round(title.fs)); });
    mids.forEach(function (k) {
      if (title && (title.fs - k) / title.fs < 0.15) add('subtitle-too-close', 'medium', texts.filter(function (t) { return Math.round(t.fs) === k; })[0].el, 'Subtitle size (' + k + 'px) is almost the title size (' + Math.round(title.fs) + 'px)');
      if (k > bodyFs && k - bodyFs < Math.max(3, bodyFs * 0.1)) add('subtitle-too-close', 'low', texts.filter(function (t) { return Math.round(t.fs) === k; })[0].el, 'Subtitle size (' + k + 'px) is almost the body size (' + bodyFs + 'px)');
    });
    if (keys.length > 6) add('too-many-sizes', 'low', null, keys.length + ' different text sizes on one slide: ' + keys.join(', '));
    texts.forEach(function (t) {
      if (t.fs < H * 0.016 && t.len > 3) add('text-too-small', 'medium', t.el, 'Text is ' + Math.round(t.fs) + 'px on a ' + Math.round(H) + 'px slide; unreadable when presented');
      var cpl = (t.r.right - t.r.left) / (t.fs * 0.5);
      if (cpl > 95 && (t.r.bottom - t.r.top) > t.fs * 2.5) add('long-lines', 'low', t.el, 'Lines are about ' + Math.round(cpl) + ' characters long; hard to read');
    });

    // 4. images
    media.forEach(function (m) {
      var r = m.getBoundingClientRect();
      if (m.tagName === 'IMG' && m.naturalWidth) {
        var fit = getComputedStyle(m).objectFit, nat = m.naturalWidth / m.naturalHeight, shown = r.width / r.height;
        if ((fit === 'fill' || !fit) && Math.abs(nat - shown) / nat > 0.04) add('image-stretched', 'high', m, 'Image is stretched (natural ' + nat.toFixed(2) + ', shown ' + shown.toFixed(2) + ')');
        if (!m.complete || m.naturalWidth === 0) add('image-broken', 'high', m, 'Image did not load');
      }
      if (m.tagName === 'IMG' && m.complete && m.naturalWidth === 0) add('image-broken', 'high', m, 'Image did not load');
      var gaps = [r.left - R.left, R.right - r.right, r.top - R.top, R.bottom - r.bottom];
      gaps.forEach(function (g, k) { if (g > 1 && g < W * 0.02) add('image-near-edge', 'low', m, 'Image is ' + Math.round(g) + 'px from the ' + ['left', 'right', 'top', 'bottom'][k] + ' edge: either bleed to the edge or keep the slide margin'); });
      if (r.right > R.right + 1 || r.left < R.left - 1 || r.bottom > R.bottom + 1) add('image-out', 'medium', m, 'Image runs past the slide');
      var share = r.width * r.height / (W * H); info.imageShare = Math.max(info.imageShare || 0, +share.toFixed(2));
      if (share < 0.06) add('image-tiny', 'low', m, 'Image takes only ' + Math.round(share * 100) + '% of the slide');
    });
    var textArea = texts.reduce(function (s, t) { return s + (t.r.right - t.r.left) * (t.r.bottom - t.r.top); }, 0);
    info.textShare = +(textArea / (W * H)).toFixed(2);
    if (info.textShare > 0.45) add('crowded', 'medium', null, 'Text fills ' + Math.round(info.textShare * 100) + '% of the slide; split it or cut text');

    // 5. icons
    texts.forEach(function (t) { if (EMOJI.test(t.el.textContent)) add('emoji-icon', 'medium', t.el, 'Emoji used as an icon'); });
    if (icons.length > 1) {
      var roles = {};
      icons.forEach(function (ic) {
        var pe = ic.parentElement, gp = pe && pe.parentElement;
        var key = gp ? gp.tagName + '.' + (typeof gp.className === 'string' ? gp.className : '') : 'x';
        var r = ic.getBoundingClientRect(); (roles[key] = roles[key] || []).push({ el: ic, s: Math.round(Math.max(r.width, r.height)) });
      });
      Object.keys(roles).forEach(function (k) {
        var g = roles[k]; if (g.length < 2) return;
        var ss = g.map(function (o) { return o.s; }), mx = Math.max.apply(null, ss), mn = Math.min.apply(null, ss);
        if (mx / mn > 1.2) add('icon-sizes', 'medium', g[ss.indexOf(mx)].el, 'Icons that play the same role come in different sizes: ' + ss.filter(function (v, i, a) { return a.indexOf(v) === i; }).join(', ') + 'px');
      });
      var styles = {};
      icons.forEach(function (ic) {
        if (ic.tagName !== 'svg') { styles[ic.tagName.toLowerCase()] = 1; return; }
        var p = ic.querySelector('path,circle,rect,line,polyline,polygon'); if (!p) return;
        var cs = getComputedStyle(p), filled = cs.fill !== 'none' && cs.fill !== 'transparent' && cs.fill !== 'rgba(0, 0, 0, 0)';
        var sw = parseFloat(cs.strokeWidth) || 0, stroked = cs.stroke !== 'none' && sw > 0;
        styles[(filled && !stroked) ? 'filled' : (stroked ? 'line-' + sw : 'other')] = 1;
      });
      var sk = Object.keys(styles); info.iconStyles = sk;
      if (sk.length > 1) add('icon-styles', 'medium', icons[0], 'Mixed icon styles on one slide: ' + sk.join(', '));
    }

    // 6. margins and near-miss alignment
    var minL = 1e9, minR = 1e9, minT = 1e9, minB = 1e9;
    texts.forEach(function (t) { minL = Math.min(minL, t.r.left - R.left); minR = Math.min(minR, R.right - t.r.right); minT = Math.min(minT, t.r.top - R.top); minB = Math.min(minB, R.bottom - t.r.bottom); });
    info.margins = { left: Math.round(minL), right: Math.round(minR), top: Math.round(minT), bottom: Math.round(minB) };
    if (texts.length && Math.min(minL, minR) < W * 0.03 && Math.min(minL, minR) > -1) add('tight-margin', 'medium', null, 'Text is only ' + Math.round(Math.min(minL, minR)) + 'px from the side edge');
    var edges = texts.filter(function (t) { var b = t.el.getBoundingClientRect(); return Math.abs(b.right - t.r.right) < 3 || Math.abs(b.left - t.r.left) < 3; })
      .map(function (t) { return { el: t.el, l: t.r.left, r: t.r.right, t: t.r.top }; });
    for (var x = 0; x < edges.length; x++) for (var y = x + 1; y < edges.length; y++) {
      var dR = Math.abs(edges[x].r - edges[y].r), dL = Math.abs(edges[x].l - edges[y].l), dT = Math.abs(edges[x].t - edges[y].t);
      var rtl = getComputedStyle(S).direction === 'rtl', dE = rtl ? dR : dL;
      if (dE > 2 && dE < 10) { add('misaligned', 'low', edges[y].el, 'Text edge is ' + Math.round(dE) + 'px off from "' + snippet(edges[x].el) + '"'); break; }
      if (dT > 2 && dT < 8 && edges[x].el.parentElement === edges[y].el.parentElement) { add('misaligned', 'low', edges[y].el, 'Top is ' + Math.round(dT) + 'px off from "' + snippet(edges[x].el) + '"'); break; }
    }

    // dedupe
    var seen = {}; issues = issues.filter(function (s) { var k = s.type + s.selector; if (seen[k]) return false; seen[k] = 1; return true; });
    return { slide: idx, issues: issues, info: info };
  }

  function overlay(report, slides) {
    var old = document.getElementById('__audit_panel'); if (old) old.remove();
    document.querySelectorAll('.__audit_box').forEach(function (b) { b.remove(); });
    var col = { high: '#FF3B30', medium: '#FF9500', low: '#AF52DE' };
    report.slides.forEach(function (s, k) {
      var R = slides[k].getBoundingClientRect();
      s.issues.forEach(function (it) {
        if (!it.rect) return;
        var b = document.createElement('div'); b.className = '__audit_box';
        b.style.cssText = 'position:fixed;pointer-events:none;z-index:2147483646;border:3px solid ' + col[it.severity] + ';left:' + (R.left + it.rect.x) + 'px;top:' + (R.top + it.rect.y) + 'px;width:' + it.rect.w + 'px;height:' + it.rect.h + 'px';
        document.body.appendChild(b);
      });
    });
    var n = report.slides.reduce(function (a, s) { return a + s.issues.length; }, 0);
    var p = document.createElement('div'); p.id = '__audit_panel';
    p.style.cssText = 'position:fixed;top:12px;left:12px;z-index:2147483647;background:#111;color:#fff;font:13px/1.4 system-ui;padding:10px 12px;border-radius:10px;max-width:360px;max-height:60vh;overflow:auto;direction:ltr;text-align:left';
    p.innerHTML = '<b>' + n + ' layout issues</b> <button id="__audit_copy" style="margin-left:8px">Copy report</button> <button id="__audit_x">×</button><ul style="margin:6px 0 0 16px;padding:0">' +
      report.slides.map(function (s) { return s.issues.map(function (it) { return '<li><span style="color:' + col[it.severity] + '">●</span> ' + it.type + ': ' + it.message.replace(/</g, '&lt;') + '</li>'; }).join(''); }).join('') + '</ul>';
    document.body.appendChild(p);
    document.getElementById('__audit_copy').onclick = function () { navigator.clipboard.writeText(JSON.stringify(report)); this.textContent = 'Copied'; };
    document.getElementById('__audit_x').onclick = function () { p.remove(); document.querySelectorAll('.__audit_box').forEach(function (b) { b.remove(); }); };
  }

  window.__slideAudit = function (opts) {
    opts = opts || {};
    var slides = findSlides();
    var report = { slides: slides.map(function (s, k) { return auditSlide(s, k + 1); }) };
    if (opts.overlay) overlay(report, slides);
    return report;
  };
})();
