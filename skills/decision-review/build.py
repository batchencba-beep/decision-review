#!/usr/bin/env python3
"""Turn a findings JSON file into a self-contained decision page.

Usage: python3 build.py findings.json decisions.html

The agent only writes the JSON. This script owns all of the markup, so a
review round costs a few hundred tokens of data instead of a hand-written page.
See SKILL.md for the schema.
"""
import hashlib
import html
import json
import os
import re
import struct
import sys

LABELS = {
    "en": {
        "today": "Today", "proposed": "Proposed", "critical": "Critical",
        "approve": "Approve", "reject": "Reject", "discuss": "Discuss",
        "note": "Note (optional)", "copy": "Copy all decisions as a prompt",
        "copied": "Copied", "decided": "{n} of {t} decided",
        "undecided": "Not decided", "recommended": "recommended",
        "option": "option", "missing": "Image missing",
        "prompt_head": "Apply the approved items, using the chosen option on choice cards. "
                       "Rejected and undecided items stay as they are, unless a note asks for something else. "
                       "Answer the Discuss items before changing them. A note overrides the proposal. "
                       "Look up each id in findings.json for the exact change.",
        "note_word": "note",
    },
    "he": {
        "today": "היום", "proposed": "מוצע", "critical": "קריטי",
        "approve": "אישור", "reject": "דחייה", "discuss": "לדיון",
        "note": "הערה (לא חובה)", "copy": "העתק את כל ההחלטות כפרומפט",
        "copied": "הועתק", "decided": "{n} מתוך {t} הוחלטו",
        "undecided": "לא הוחלט", "recommended": "מומלץ",
        "option": "אפשרות", "missing": "התמונה חסרה",
        "prompt_head": "תיישם את מה שאושר, ובכרטיסי בחירה את האפשרות שנבחרה. "
                       "מה שנדחה או לא הוחלט נשאר כמו שהוא, אלא אם ההערה מבקשת משהו אחר. "
                       "על מה שסומן לדיון תענה לפני שמשנים. הערה גוברת על ההצעה. "
                       "את השינוי המדויק לכל id תמצא ב־findings.json.",
        "note_word": "הערה",
    },
}

RTL_CHARS = re.compile("[֐-׿؀-ۿ]")


def esc(s):
    return html.escape(str(s or ""), quote=True)


def tdir(s):
    """Any Hebrew or Arabic in the text means RTL, even when it starts with an English word."""
    return "rtl" if RTL_CHARS.search(str(s or "")) else "ltr"


def short(s):
    """Short labels follow the page direction; <bdi> keeps their own punctuation in place."""
    return f'<bdi>{esc(s)}</bdi>'

def pixel_width(path):
    """Width in pixels of a PNG or JPEG, read from the file header. None if unknown."""
    try:
        with open(path, "rb") as f:
            head = f.read(26)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return struct.unpack(">I", head[16:20])[0]
            if head[:2] == b"\xff\xd8":
                f.seek(2)
                while True:
                    marker = f.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        return None
                    size = struct.unpack(">H", f.read(2))[0]
                    if marker[1] in (0xC0, 0xC1, 0xC2):
                        f.read(3)
                        return struct.unpack(">H", f.read(2))[0]
                    f.seek(size - 2, 1)
    except (OSError, struct.error):
        return None
    return None


class Page:
    """Everything a card needs to know about the page it lives on."""

    def __init__(self, data, out_dir):
        lang = data.get("lang", "en")
        self.L = dict(LABELS.get(lang, LABELS["en"]), **data.get("labels", {}))
        self.out_dir = out_dir
        self.scale = float(data.get("scale", 2))
        self.group_max = None

    def images(self, imgs, alt):
        out = []
        for im in imgs or []:
            if isinstance(im, str):
                im = {"src": im}
            src = im["src"]
            cap = f'<figcaption>{short(im["caption"])}</figcaption>' if im.get("caption") else ""
            local = os.path.join(self.out_dir, src)
            if not re.match(r"^(https?:|data:)", src) and not os.path.exists(local):
                out.append(f'<figure>{cap}<div class="missing">{esc(self.L["missing"])}: {esc(src)}</div></figure>')
                continue
            css_w = self.css_width(im)
            width = ""
            if css_w and self.group_max:
                # Proportional to the widest image in the card, and never wider than its real size.
                width = f' style="width:{100 * css_w / self.group_max:.1f}%;max-width:{css_w:.0f}px"'
            out.append(f'<figure>{cap}<img src="{esc(src)}" alt="{esc(im.get("alt") or im.get("caption") or alt)}"{width}></figure>')
        return "".join(out)

    def css_width(self, im):
        if isinstance(im, str):
            im = {"src": im}
        src = im.get("src", "")
        if re.match(r"^(https?:|data:)", src):
            return None
        px = pixel_width(os.path.join(self.out_dir, src))
        return px / float(im.get("scale", self.scale)) if px else None

    def preview(self, side, alt):
        parts = self.images(side.get("images"), alt)
        if side.get("html"):
            parts += side["html"]  # trusted: written by the agent for this local page
        return f'<div class="prev">{parts}</div>' if parts else ""

    def options(self, opts, title):
        L, figs = self.L, []
        for i, o in enumerate(opts):
            rec = f' <span>({L["recommended"]})</span>' if o.get("recommended") else ""
            vis = self.images(o.get("images"), f'{title}: {o["label"]}')
            if o.get("html"):
                vis += o["html"]
            figs.append(
                f'<div class="opt" role="radio" tabindex="0" aria-checked="false" data-i="{i}" '
                f'data-label="{esc(o["label"])}" data-rec="{1 if o.get("recommended") else 0}">'
                f'<div class="opt-l">{short(o["label"])}{rec}</div>{vis}</div>')
        return (f'<div class="prev opts" role="radiogroup" aria-label="{esc(title)}" '
                f'style="--n:{len(opts)}">{"".join(figs)}</div>')

    def card(self, it):
        L, title = self.L, it["title"]
        today, prop = it.get("today") or {}, it.get("proposed") or {}
        crit = f'<span class="crit">{L["critical"]}</span>' if it.get("critical") is True else ""
        has_opts = bool(prop.get("options"))
        every = list(today.get("images") or []) + list(prop.get("images") or [])
        for o in prop.get("options") or []:
            every += o.get("images") or []
        widths = [w for w in (self.css_width(im) for im in every) if w]
        self.group_max = max(widths) if widths else None
        prop_vis = self.options(prop["options"], title) if has_opts else self.preview(prop, f'{title}: {L["proposed"]}')
        return f'''
<article class="card" data-id="{esc(it["id"])}">
  <h3 dir="{tdir(title)}"><span class="t">{esc(title)}</span>{crit}</h3>
  <div class="cmp{" wide" if has_opts else ""}">
    <div class="side cur"><div class="lbl">{L["today"]}</div>{self.preview(today, f'{title}: {L["today"]}')}<p dir="{tdir(today.get("text"))}">{esc(today.get("text"))}</p></div>
    <div class="side prop"><div class="lbl">{L["proposed"]}</div>{prop_vis}<p dir="{tdir(prop.get("text"))}">{esc(prop.get("text"))}</p></div>
  </div>
  <footer>
    <div class="btns" role="group" aria-label="{esc(title)}">
      <button class="b" data-v="approve">{L["approve"]}</button>
      <button class="b" data-v="reject">{L["reject"]}</button>
      <button class="b" data-v="discuss">{L["discuss"]}</button>
    </div>
    <input class="note" type="text" dir="auto" placeholder="{L["note"]}" aria-label="{L["note"]}">
  </footer>
</article>'''


CSS = """
:root{--bg:#F2F2F1;--paper:#fff;--ink:#0F0F2D;--ink-2:#4B4B5E;--line:rgba(15,15,45,.14);--accent:#3C3CF7;--ok:#1F7A4D;--no:#B3261E;--talk:#8A6D00;--r:6px}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;background:var(--bg);color:var(--ink);font-size:16px;line-height:1.55;padding:40px 16px 140px}
.wrap{max-width:1120px;margin:0 auto}
h1{font-family:Georgia,"Times New Roman",serif;font-size:30px;line-height:1.2;font-weight:400;letter-spacing:-.01em;margin-bottom:24px;text-wrap:balance}
.card{background:var(--paper);border:1px solid var(--line);border-radius:var(--r);padding:20px;margin-bottom:14px;border-inline-start:4px solid transparent;transition:border-color .2s}
.card[data-state=approve]{border-inline-start-color:var(--ok)}
.card[data-state=reject]{border-inline-start-color:var(--no)}
.card[data-state=discuss]{border-inline-start-color:var(--talk)}
.card h3{font-size:18px;font-weight:600;line-height:1.3;text-wrap:balance}
.crit{display:inline-block;font-size:12px;font-weight:600;padding:2px 8px;border-radius:4px;background:#FBE9E7;color:var(--no);vertical-align:3px;margin-inline-start:10px}
.cmp{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}
.cmp.wide{grid-template-columns:1fr 2fr}
@media(max-width:720px){.cmp,.cmp.wide{grid-template-columns:1fr}}
.side{border:1px solid var(--line);border-radius:var(--r);padding:14px;background:var(--bg);min-width:0}
.side.prop{background:#fff;border-color:rgba(60,60,247,.35)}
.lbl{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);margin-bottom:8px}
.prop .lbl{color:var(--accent)}
.side p{font-size:14px;color:var(--ink-2);white-space:pre-wrap;text-wrap:pretty;text-align:start}
.side p:empty{display:none}
.prev{background:#fff;border-radius:4px;padding:10px;margin-bottom:10px;overflow:hidden}
.prop .prev{background:var(--bg)}
.prev img{display:block;max-width:100%;height:auto;border-radius:3px}
.prev figure+figure{margin-top:12px}
.prev figcaption{font-size:13px;font-weight:600;margin-bottom:6px}
.missing{font-size:13px;color:var(--no);background:#FBE9E7;border-radius:3px;padding:10px;word-break:break-all}
.opts{display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));gap:10px}
.opt{cursor:pointer;border-radius:4px;padding:6px;outline:1px solid transparent;transition:outline-color .15s}
.opt:hover{outline-color:var(--line)}
.opt.sel{outline:2px solid var(--accent);outline-offset:2px}
.opt:focus-visible{outline:2px solid var(--ink);outline-offset:2px}
.opt-l{font-size:13px;font-weight:600;margin-bottom:6px}
.opt-l span{font-weight:400;color:var(--ink-2)}
.opt figure+figure{margin-top:8px}
@media(max-width:720px){.opts{grid-template-columns:1fr}}
footer{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:16px}
.btns{display:flex;gap:6px}
.b{font:inherit;font-size:14px;padding:8px 14px;min-height:40px;border:1px solid var(--line);border-radius:999px;background:var(--paper);cursor:pointer;color:var(--ink)}
.b:hover{border-color:var(--ink)}
.b:focus-visible,.note:focus-visible,.copy:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.b[data-v=approve].on{background:var(--ok);border-color:var(--ok);color:#fff}
.b[data-v=reject].on{background:var(--no);border-color:var(--no);color:#fff}
.b[data-v=discuss].on{background:var(--talk);border-color:var(--talk);color:#fff}
.note{flex:1;min-width:200px;font:inherit;font-size:14px;padding:8px 12px;border:1px solid var(--line);border-radius:var(--r);background:var(--paper)}
.bar{position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid var(--line);padding:14px 16px}
.bar-in{max-width:1120px;margin:0 auto;display:flex;gap:16px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.count{font-size:14px;color:var(--ink-2)}
.count b{color:var(--ink)}
.copy{font:inherit;font-size:15px;font-weight:600;padding:12px 20px;border:0;border-radius:999px;background:var(--ink);color:#fff;cursor:pointer}
.copy:hover{background:var(--accent)}
.copy.done{background:var(--ok)}
@media(max-width:720px){.bar{padding:8px 12px}.bar-in{gap:8px;flex-wrap:nowrap}.count{font-size:12px}.count .split{display:none}.copy{font-size:13px;padding:10px 14px;white-space:nowrap}}
"""

JS = """
(function(){
  var L=__LABELS__, KEY=__KEY__, TITLE=__TITLE__;
  var st={}; try{st=JSON.parse(localStorage.getItem(KEY)||'{}');}catch(e){}
  function save(){try{localStorage.setItem(KEY,JSON.stringify(st));}catch(e){}}
  var cards=[].slice.call(document.querySelectorAll('.card'));
  function opts(c){return [].slice.call(c.querySelectorAll('.opt'));}
  function chosen(c){var s=st[c.dataset.id]||{},o=opts(c);if(!o.length)return null;
    if(s.o!=null&&o[s.o])return o[s.o];return o.filter(function(x){return x.dataset.rec==='1';})[0]||null;}
  function paint(c){var s=st[c.dataset.id]||{};c.dataset.state=s.v||'';
    c.querySelectorAll('.b').forEach(function(b){var on=b.dataset.v===s.v;b.classList.toggle('on',on);b.setAttribute('aria-pressed',on);});
    var ch=chosen(c);opts(c).forEach(function(o){var on=o===ch;o.classList.toggle('sel',on);o.setAttribute('aria-checked',on);});
    var n=c.querySelector('.note');if(n.value!==(s.n||''))n.value=s.n||'';}
  function count(){var a=0,r=0,d=0;cards.forEach(function(c){var v=(st[c.dataset.id]||{}).v;if(v==='approve')a++;else if(v==='reject')r++;else if(v==='discuss')d++;});
    document.getElementById('count').innerHTML=L.decided.replace('{n}','<b>'+(a+r+d)+'</b>').replace('{t}',cards.length)
      +'<span class="split"> · '+L.approve+' <b>'+a+'</b> · '+L.reject+' <b>'+r+'</b> · '+L.discuss+' <b>'+d+'</b></span>';}
  cards.forEach(function(c){var id=c.dataset.id;
    c.querySelectorAll('.b').forEach(function(b){b.addEventListener('click',function(){st[id]=st[id]||{};
      st[id].v=(st[id].v===b.dataset.v)?'':b.dataset.v;save();paint(c);count();});});
    opts(c).forEach(function(o,i){function pick(){st[id]=st[id]||{};st[id].o=i;save();paint(c);}
      o.addEventListener('click',pick);
      o.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();pick();}});});
    c.querySelector('.note').addEventListener('input',function(e){st[id]=st[id]||{};st[id].n=e.target.value;save();});
    paint(c);});
  count();
  document.getElementById('copy').addEventListener('click',function(){
    var lines=[TITLE,L.prompt_head,''];
    cards.forEach(function(c){var s=st[c.dataset.id]||{};var v=s.v?L[s.v]:L.undecided;var ch=chosen(c);
      var pick=(ch&&(s.v==='approve'||s.o!=null))?' · '+L.option+': '+ch.dataset.label:'';
      var kw=' ['+(s.v||'undecided')+']';
      lines.push(c.dataset.id+' · '+c.querySelector('.t').textContent+' → '+v+kw+pick+(s.n?' · '+L.note_word+': '+s.n:''));});
    var txt=lines.join('\\n'),btn=this;
    function ok(){btn.classList.add('done');btn.textContent=L.copied;setTimeout(function(){btn.classList.remove('done');btn.textContent=L.copy;},1800);}
    function fb(){var ta=document.createElement('textarea');ta.value=txt;document.body.appendChild(ta);ta.select();try{document.execCommand('copy');}catch(e){}ta.remove();ok();}
    if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(txt).then(ok,fb);else fb();});
})();
"""


def storage_key(data):
    """Same content keeps its saved decisions; a new round with new items starts clean."""
    if data.get("key"):
        return data["key"]
    slug = re.sub(r"\W+", "-", data["title"].lower()).strip("-")
    sig = json.dumps([[it.get("id"), it.get("title")] for it in data["items"]], ensure_ascii=False)
    return f"decision-review:{slug}:{hashlib.sha1(sig.encode()).hexdigest()[:8]}"


def build(data, out_dir="."):
    page = Page(data, out_dir)
    lang = data.get("lang", "en")
    title = data["title"]
    js = (JS.replace("__LABELS__", json.dumps(page.L, ensure_ascii=False))
            .replace("__KEY__", json.dumps(storage_key(data)))
            .replace("__TITLE__", json.dumps(title, ensure_ascii=False)))
    return f'''<!doctype html>
<html lang="{lang}" dir="{"rtl" if lang in ("he", "ar", "fa") else "ltr"}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <h1 dir="{tdir(title)}">{esc(title)}</h1>
  {"".join(page.card(it) for it in data["items"])}
</div>
<div class="bar"><div class="bar-in"><div class="count" id="count" aria-live="polite"></div><button class="copy" id="copy">{page.L["copy"]}</button></div></div>
<script>{js}</script>
</body>
</html>
'''


def validate(data, out_dir):
    """Return (errors, warnings) in plain language, so a broken findings file explains itself."""
    errors, warnings = [], []
    if not isinstance(data, dict):
        return ["The file must be one JSON object: { \"title\": ..., \"items\": [...] }"], warnings
    if not str(data.get("title", "")).strip():
        errors.append("Missing top-level \"title\". It names the page and starts the copied prompt.")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        errors.append("\"items\" is missing or empty. Add at least one decision.")
        return errors, warnings
    if data.get("lang", "en") not in LABELS and "labels" not in data:
        warnings.append(f"lang \"{data.get('lang')}\" has no built-in labels, using English. Add \"labels\" to translate.")
    if "scale" in data and not isinstance(data["scale"], (int, float)):
        errors.append("\"scale\" must be a number (pixel density of your screenshots, usually 2).")
    seen = set()
    for n, it in enumerate(items, 1):
        where = f"Item {n}" + (f" ({it.get('id')})" if isinstance(it, dict) and it.get("id") else "")
        if not isinstance(it, dict):
            errors.append(f"{where}: must be an object.")
            continue
        if not str(it.get("id", "")).strip():
            errors.append(f"{where}: missing \"id\".")
        elif it["id"] in seen:
            errors.append(f"{where}: id \"{it['id']}\" is used twice. Each card needs a unique id.")
        seen.add(it.get("id"))
        if not str(it.get("title", "")).strip():
            errors.append(f"{where}: missing \"title\".")
        if "change" in it and not isinstance(it["change"], str):
            errors.append(f"{where}: \"change\" must be text describing the exact edit.")
        if "critical" in it and not isinstance(it["critical"], bool):
            errors.append(f"{where}: \"critical\" must be true or false, not {json.dumps(it['critical'])}.")
        for side in ("today", "proposed"):
            s = it.get(side)
            if s is None:
                continue
            if not isinstance(s, dict):
                errors.append(f"{where}: \"{side}\" must be an object like {{ \"text\": \"...\" }}.")
                continue
            imgs = list(s.get("images") or [])
            for o in s.get("options") or []:
                if isinstance(o, dict):
                    imgs += o.get("images") or []
            for im in imgs:
                src = im.get("src") if isinstance(im, dict) else im
                if not src:
                    errors.append(f"{where}: an image in \"{side}\" has no src.")
                elif not re.match(r"^(https?:|data:)", src) and not os.path.exists(os.path.join(out_dir, src)):
                    warnings.append(f"{where}: image not found: {src} (paths are relative to the HTML file). "
                                    "The card will show a red 'Image missing' box.")
        prop = it.get("proposed") or {}
        if isinstance(prop, dict):
            if not any(prop.get(k) for k in ("text", "images", "html", "options")):
                errors.append(f"{where}: \"proposed\" is empty. Say what you'd change.")
            opts = prop.get("options")
            if opts is not None:
                if not isinstance(opts, list) or len(opts) < 2:
                    errors.append(f"{where}: \"options\" needs at least two choices.")
                else:
                    if len(opts) > 4:
                        warnings.append(f"{where}: {len(opts)} options get cramped. Two to four reads best.")
                    for k, o in enumerate(opts, 1):
                        if not isinstance(o, dict) or not str(o.get("label", "")).strip():
                            errors.append(f"{where}: option {k} needs a \"label\".")
    return errors, warnings


def main(argv):
    if len(argv) != 3:
        sys.exit("Usage: python3 build.py findings.json decisions.html")
    src, out = argv[1], argv[2]
    try:
        with open(src, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        sys.exit(f"Can't find {src}.")
    except json.JSONDecodeError as e:
        sys.exit(f"{src} isn't valid JSON: {e.msg} at line {e.lineno}, column {e.colno}.")
    out_dir = os.path.dirname(os.path.abspath(out))
    errors, warnings = validate(data, out_dir)
    for w in warnings:
        print("warning:", w, file=sys.stderr)
    if errors:
        sys.exit("Can't build the page:\n- " + "\n- ".join(errors))
    with open(out, "w", encoding="utf-8") as f:
        f.write(build(data, out_dir))
    print(out)


if __name__ == "__main__":
    main(sys.argv)
