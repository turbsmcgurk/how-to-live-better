# -*- coding: utf-8 -*-
"""Render the selected sections of "The Cost-Effective Life Guide" (高性价比人生指南)
into a self-contained single-file HTML reading page.

Usage:
    python build.py                      # defaults to sections 1, 2, 16
    python build.py 1 2 16 3             # any section numbers (rendered in the given order)
    python build.py all                  # all sections (used for the live site)
    python build.py all -o index.html    # explicit output file name
    python build.py all --repo /path/to/HowToLiveBetter

The source directory can also be given via the HLTB_REPO environment variable
(used by GitHub Actions; takes lower priority than --repo).
The output lands next to this script by default: a single .html file with no
external dependencies — double-click to open, readable offline.

This is the English edition: all rendered UI strings and text are English.
The upstream book's markdown source is Chinese, so the field-name keywords in
the parsing regexes (成本 / 说人话 / 收益 / 证据等级 / 来源 / 备注) and the cost-tag
keys below MUST stay Chinese or nothing parses.

The numbers and labels follow the upstream repository's tools/sync-stats.ps1 and
its index.html COST_W / e.ratio lines exactly: if the upstream changes those two
lines, change them here too, or the value-for-money tiers will drift out of sync
with the official search page.
"""

import argparse
import html
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def parse_args():
    ap = argparse.ArgumentParser(
        description='Render "The Cost-Effective Life Guide" as a single-file reading page')
    ap.add_argument("sections", nargs="*", help="section numbers, or 'all' for every section")
    ap.add_argument("-o", "--out", default=None, help="output file name (default: auto-named from section numbers)")
    ap.add_argument("--repo", default=None, help="upstream repository directory (default: D:\\Agent\\HowToLiveBetter)")
    return ap.parse_args()


ARGS = parse_args()
REPO = Path(ARGS.repo or os.environ.get("HLTB_REPO") or r"D:\Agent\HowToLiveBetter")

UPSTREAM = "https://github.com/eternity4719/HowToLiveBetter"


def avail_sections():
    """Scan the book/ directory for the section numbers that actually exist."""
    return sorted(int(p.name[:2]) for p in REPO.glob("book/[0-9][0-9]-*.md"))


ALL = avail_sections()
if not ALL:
    raise SystemExit("Cannot find book/NN-*.md under %s; point --repo at the correct repository directory" % REPO)

if ARGS.sections:
    if any(a.lower() == "all" for a in ARGS.sections):
        SECTIONS = ALL
    else:
        SECTIONS = [int(a) for a in ARGS.sections]
else:
    SECTIONS = [n for n in (1, 2, 16) if n in ALL]

SCOPE = ("All %d sections" % len(ALL)) if SECTIONS == ALL else ("Section %s" % ", ".join(str(n) for n in SECTIONS))

# Cost weights and tier rules, copied from the COST_W and e.ratio lines in the
# upstream index.html. The keys/values are the upstream book's Chinese tag
# vocabulary (钱=money, 时间=time, 毅力=willpower) and must stay Chinese.
COST_W = {
    "钱": {"0": 0, "少": 1, "多": 2},
    "时间": {"少": 0, "中": 1, "多": 2},
    "毅力": {"否": 0, "些": 1, "是": 2},
}
RATIO_ORDER = {"Exceptional": 0, "High": 1, "Fair": 2}


def find_file(n):
    hits = sorted(REPO.glob("book/%02d-*.md" % n))
    if not hits:
        raise SystemExit("Cannot find section %d" % n)
    return hits[0]


def parse(path):
    lines = path.read_text(encoding="utf-8").split("\n")
    title, intro, entries, cur = "", [], [], None
    for ln in lines:
        m = re.match(r"^#\s+(.*)$", ln)
        if m and not title:
            title = m.group(1).strip()
            continue
        m = re.match(r"^###\s+(\d+)\.\s*(.*)$", ln)
        if m:
            cur = {"no": int(m.group(1)), "title": m.group(2).strip(),
                   "tags_raw": None, "fields": {}, "last": None}
            entries.append(cur)
            continue
        if cur is None:
            if ln.strip() and not ln.startswith("["):
                intro.append(ln.strip())
            continue
        mt = re.match(r"^<!--\s*成本标签:\s*(.*?)\s*-->", ln)
        if mt:
            cur["tags_raw"] = mt.group(1)
            continue
        # Field keywords match the upstream Chinese markdown headings.
        mf = re.match(r"^-\s*(成本|说人话|收益|证据等级|来源|备注)：(.*)$", ln)
        if mf:
            cur["last"] = mf.group(1)
            cur["fields"][mf.group(1)] = mf.group(2).strip()
            continue
        if not ln.strip():
            cur["last"] = None
            continue
        if cur["last"]:
            cur["fields"][cur["last"]] += ln.strip()
    return title, intro, entries


def parse_tags(raw):
    if not raw:
        return {}
    return dict(re.findall(r"(钱|时间|毅力|收益|口径)=(\S+)", raw))


def ratio_of(t):
    try:
        cs = sum(COST_W[k][t[k]] for k in ("钱", "时间", "毅力"))
    except KeyError:
        return None
    lv = t.get("收益")
    if lv == "大":
        return "Exceptional" if cs == 0 else ("High" if cs <= 2 else "Fair")
    if lv == "中" and cs == 0:
        return "High"
    return "Fair"


def inline(s):
    """Convert a short piece of markdown inline syntax to HTML. Escape everything
    first, then re-insert links through placeholders."""
    stash = []

    def mk(url, text=None):
        shown = text or url
        if len(shown) > 62:
            shown = shown[:59] + "…"
        stash.append('<a href="%s" target="_blank" rel="noopener">%s</a>' % (url, shown))
        return "\u0001%d\u0001" % (len(stash) - 1)

    s = html.escape(s, quote=False)
    s = re.sub(r"&lt;(https?://[^\s]+?)&gt;", lambda m: mk(m.group(1)), s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", lambda m: mk(m.group(2), m.group(1)), s)
    # The character class keeps the Chinese punctuation that appears in the
    # upstream source text.
    s = re.sub(r"(?<![\w\"=])(https?://[^\s，。；）)]+)", lambda m: mk(m.group(1)), s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = s.replace("\\*", "*").replace("\\_", "_")
    s = re.sub("\u0001(\\d+)\u0001", lambda m: stash[int(m.group(1))], s)
    return s


def link_count(s):
    return len(re.findall(r"https?://", s or ""))


def source_rev():
    """Short hash and date of the upstream's current commit.

    Deliberately derived from the upstream git state rather than the build time:
    rerunning with the same source state produces byte-identical output, which
    makes it easy to confirm "nothing got broken".
    """
    try:
        p = subprocess.run(["git", "-C", str(REPO), "log", "-1", "--date=short",
                            "--format=%h|%cd"],
                           capture_output=True, text=True, encoding="utf-8", timeout=15)
        if p.returncode == 0 and "|" in (p.stdout or ""):
            h, d = p.stdout.strip().split("|", 1)
            return h.strip(), d.strip()
    except Exception:
        pass
    return "", ""


CSS = r"""
*,*::before,*::after{box-sizing:border-box}
:root{
  --bg:#ffffff;--bg-alt:#f6f6f7;--bg-elv:#ffffff;--bg-mute:#f1f1f2;
  --divider:#e2e2e3;
  --t1:rgba(60,60,67,1);--t2:rgba(60,60,67,.78);--t3:rgba(60,60,67,.56);
  --brand-1:#3451b2;--brand-2:#3a5ccc;--brand-soft:rgba(100,108,255,.12);
  --green-1:#18794e;--green-soft:rgba(16,185,129,.13);
  --yellow-1:#915930;--yellow-soft:rgba(234,179,8,.15);
  --red-1:#b8272c;--red-soft:rgba(244,63,94,.12);
  --gray-1:#565a5f;--gray-soft:rgba(142,150,170,.15);
  --mark:rgba(234,179,8,.34);
  --font:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  --bar:56px;--side:296px;
}
[data-theme=dark]{
  --bg:#1b1b1f;--bg-alt:#161618;--bg-elv:#202127;--bg-mute:#2b2b2f;
  --divider:#2e2e32;
  --t1:rgba(255,255,245,.88);--t2:rgba(235,235,245,.62);--t3:rgba(235,235,245,.4);
  --brand-1:#a8b1ff;--brand-2:#c3c9ff;--brand-soft:rgba(100,108,255,.18);
  --green-1:#3dd68c;--green-soft:rgba(16,185,129,.16);
  --yellow-1:#f9b44e;--yellow-soft:rgba(234,179,8,.16);
  --red-1:#f66f81;--red-soft:rgba(244,63,94,.16);
  --gray-1:#a4a8ae;--gray-soft:rgba(142,150,170,.16);
  --mark:rgba(234,179,8,.3);
}
html{scroll-behavior:smooth;scroll-padding-top:calc(var(--bar) + 14px)}
body{margin:0;background:var(--bg);color:var(--t1);font:15px/1.75 var(--font);
  -webkit-font-smoothing:antialiased;-webkit-text-size-adjust:100%}
a{color:var(--brand-1);text-decoration:none}
a:hover{color:var(--brand-2);text-decoration:underline;text-underline-offset:2px}
mark{background:var(--mark);color:inherit;border-radius:2px;padding:0 1px}
strong{font-weight:600;color:var(--t1)}

/* min-height uses the constant, not --bar: --bar is measured and written back by JS.
   If it were used as min-height, the collapsed top bar could not shrink back because
   min-height would still be stuck at the old height. */
.bar{position:sticky;top:0;z-index:30;display:flex;flex-wrap:wrap;align-items:center;gap:10px;
  padding:0 18px;min-height:56px;background:var(--bg);border-bottom:1px solid var(--divider)}
.bar h1{font-size:15px;font-weight:600;margin:0;white-space:nowrap;min-width:0}
.bar h1 small{font-weight:400;font-size:12px;color:var(--t3);margin-left:8px}
.spacer{flex:1}
.search{position:relative;width:300px;max-width:42vw}
.search input{width:100%;height:34px;padding:0 30px 0 32px;border-radius:8px;border:1px solid var(--divider);
  background:var(--bg-alt);color:var(--t1);font:inherit;font-size:13px}
.search input:focus{outline:0;border-color:var(--brand-1);background:var(--bg-elv)}
.search svg{position:absolute;left:9px;top:50%;transform:translateY(-50%);width:15px;height:15px;
  fill:none;stroke:var(--t3);stroke-width:2;pointer-events:none}
.search kbd{position:absolute;right:8px;top:50%;transform:translateY(-50%);font:500 10px/1 var(--font);
  color:var(--t3);border:1px solid var(--divider);border-radius:4px;padding:2px 4px;background:var(--bg-elv)}
.btn{height:30px;padding:0 11px;border-radius:999px;border:1px solid var(--divider);background:var(--bg-elv);
  color:var(--t2);font:500 12px/1 var(--font);cursor:pointer;transition:all .18s;white-space:nowrap}
.btn:hover{border-color:var(--brand-2);color:var(--t1)}
.btn[aria-pressed=true]{background:var(--brand-soft);border-color:var(--brand-1);color:var(--brand-1)}
.count{font-size:12px;color:var(--t3);white-space:nowrap;font-variant-numeric:tabular-nums}
.jump{display:none;height:30px;max-width:38vw;padding:0 6px;border-radius:8px;border:1px solid var(--divider);
  background:var(--bg-elv);color:var(--t2);font:500 12px/1 var(--font)}

.shell{display:flex;align-items:flex-start}
.toc{position:sticky;top:var(--bar);flex:none;width:var(--side);height:calc(100vh - var(--bar));
  overflow-y:auto;padding:18px 14px 80px 18px;background:var(--bg-alt);border-right:1px solid var(--divider)}
.toc .gt{font-size:13px;font-weight:600;margin:0 0 6px;color:var(--t1);display:flex;justify-content:space-between;align-items:baseline}
.toc .gt small{font-weight:400;font-size:11px;color:var(--t3)}
.toc .grp{padding-bottom:14px;margin-bottom:14px;border-bottom:1px solid var(--divider)}
.toc .grp:last-child{border-bottom:0;margin-bottom:0}
.toc a{display:flex;gap:6px;align-items:baseline;padding:3px 6px;border-radius:6px;font-size:12.5px;
  line-height:1.5;color:var(--t2)}
.toc a:hover{background:var(--bg-elv);color:var(--t1);text-decoration:none}
.toc a.active{background:var(--brand-soft);color:var(--brand-1)}
.toc a i{font-style:normal;color:var(--t3);font-variant-numeric:tabular-nums;flex:none;min-width:16px;text-align:right}
.dot{width:6px;height:6px;border-radius:50%;flex:none;margin-top:6px}
.d0{background:var(--brand-1)}.d1{background:var(--green-1)}.d2{background:var(--t3)}

main{flex:1;min-width:0;padding:26px 40px 140px;max-width:940px}
section{margin-bottom:44px}
.sec-h{display:flex;align-items:baseline;gap:12px;padding-bottom:10px;border-bottom:2px solid var(--divider);margin-bottom:6px}
.sec-h h2{font-size:22px;font-weight:600;margin:0;letter-spacing:-.2px}
.sec-h .meta{font-size:12px;color:var(--t3);font-variant-numeric:tabular-nums}
.intro{color:var(--t2);font-size:14px;margin:12px 0 22px;padding-left:12px;border-left:2px solid var(--divider)}

.card{background:var(--bg-elv);border:1px solid var(--divider);border-radius:12px;padding:16px 18px 14px;margin-bottom:12px}
.chead{display:flex;gap:10px;align-items:flex-start}
.num{flex:none;min-width:24px;height:24px;padding:0 6px;border-radius:7px;background:var(--bg-mute);color:var(--t3);
  font:600 12px/24px var(--font);text-align:center;font-variant-numeric:tabular-nums}
.chead h3{margin:0;font-size:16px;font-weight:600;line-height:1.5;letter-spacing:-.1px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 12px 34px}
.badge{font:500 11px/1 var(--font);padding:4px 9px;border-radius:999px;border:1px solid transparent}
.gA{background:var(--green-soft);color:var(--green-1);border-color:var(--green-soft)}
.gB{background:var(--yellow-soft);color:var(--yellow-1);border-color:var(--yellow-soft)}
.gC{background:var(--gray-soft);color:var(--gray-1);border-color:var(--gray-soft)}
.r0{background:var(--brand-soft);color:var(--brand-1);border-color:var(--brand-soft)}
.r1{background:var(--green-soft);color:var(--green-1);border-color:var(--green-soft)}
.r2{background:var(--gray-soft);color:var(--gray-1);border-color:var(--gray-soft)}
.tag{font:400 11px/1 var(--font);padding:4px 9px;border-radius:999px;background:var(--bg-mute);color:var(--t3)}

.plain{margin:0 0 12px 34px;padding:10px 14px;background:var(--brand-soft);
  border-left:3px solid var(--brand-1);border-radius:0 8px 8px 0;font-size:15px;line-height:1.8;color:var(--t1)}
.fields{margin-left:34px}
.f{display:grid;grid-template-columns:52px 1fr;gap:10px;padding:7px 0;border-top:1px solid var(--divider);
  font-size:13.5px;line-height:1.75;color:var(--t2)}
.f b{font-weight:500;color:var(--t3);font-size:12.5px;padding-top:2px}
.f.note b{color:var(--yellow-1)}
.f>div{min-width:0;overflow-wrap:anywhere}
.src{margin:10px 0 0 34px;border-top:1px solid var(--divider);padding-top:8px}
.src summary{cursor:pointer;font-size:12.5px;color:var(--t3);list-style:none;user-select:none}
.src summary::-webkit-details-marker{display:none}
.src summary::before{content:"▸ ";color:var(--t3)}
.src[open] summary::before{content:"▾ "}
.src summary:hover{color:var(--brand-1)}
.src .sbody{font-size:12.5px;line-height:1.8;color:var(--t2);padding:8px 0 2px;word-break:break-word;overflow-wrap:anywhere}

body.plain-only .fields,body.plain-only .src{display:none}
.hidden{display:none!important}

.empty{color:var(--t3);font-size:14px;padding:40px 0;text-align:center}
footer{color:var(--t3);font-size:12px;border-top:1px solid var(--divider);padding-top:14px;line-height:1.9}
footer a{color:var(--t2)}

#top{position:fixed;right:16px;bottom:16px;z-index:40;width:42px;height:42px;border-radius:50%;
  border:1px solid var(--divider);background:var(--bg-elv);color:var(--t2);cursor:pointer;
  font:400 17px/1 var(--font);box-shadow:0 2px 12px rgba(0,0,0,.14);
  opacity:0;pointer-events:none;transition:opacity .2s,color .18s}
#top.show{opacity:1;pointer-events:auto}
#top:hover{color:var(--brand-1);border-color:var(--brand-1)}

@media (max-width:1080px){
  .toc{display:none}
  .jump{display:block}
  main{padding:22px 22px 130px;max-width:none}
}
@media (max-width:820px){
  .bar{padding:8px 12px;gap:8px;min-height:0}
  /* Top bar, three rows: (1) title + section jump + theme, (2) filter buttons + count,
     (3) search (full-width row so typing is easy on a phone) */
  .bar h1{order:1;flex:1 1 120px;font-size:14px;overflow:hidden;text-overflow:ellipsis}
  .spacer{display:none}
  .jump{order:2}
  #theme{order:3}
  #f-all{order:4}#f-a{order:5}#f-plain{order:6}
  .count{order:7;margin-left:auto}
  .search{order:8;width:auto;max-width:none;flex:1 1 100%;margin-top:2px}
  .search input{height:34px}
  .search kbd{display:none}
  /* After scrolling down, collapse to one row (title + search + theme) to give the
     vertical space back to the content; expand again when scrolled back to the top */
  body.compact .jump,body.compact #f-all,body.compact #f-a,
  body.compact #f-plain,body.compact .count{display:none}
  body.compact .search{order:2;flex:1 1 120px;margin-top:0}
  body.compact #theme{order:3}
  main{padding:16px 13px 110px}
  .sec-h h2{font-size:19px}
  .card{padding:14px 14px 12px;border-radius:10px;margin-bottom:10px}
  .chead h3{font-size:15px}
  .plain{font-size:14.5px;padding:9px 12px}
  .f{font-size:13px;grid-template-columns:44px 1fr;gap:8px}
  .intro{font-size:13.5px;margin:10px 0 18px}
}
@media (max-width:520px){
  .bar h1 small{display:none}
  .chips,.plain,.fields,.src{margin-left:0}
  .num{min-width:22px;height:22px;font-size:11px;line-height:22px}
}
/* Narrow 320-380px screens: tighten the buttons and the section dropdown, otherwise
   the top bar wraps onto one or two extra rows */
@media (max-width:380px){
  .btn{padding:0 8px;font-size:11px}
  .bar h1{flex:1 1 90px;font-size:13px}
  .jump{max-width:32vw}
}
@media print{
  .bar,.toc,#top{display:none}
  main{max-width:none;padding:0}
  .card{break-inside:avoid;border-color:#ccc}
  .src .sbody{display:block}
  body{font-size:11pt}
}
"""


def render_entry(e, sec_no):
    t = parse_tags(e["tags_raw"])
    f = e["fields"]
    grade = (f.get("证据等级") or "?").strip()[:1]
    ratio = ratio_of(t)
    chips = []
    gcls = {"A": "gA", "B": "gB", "C": "gC"}.get(grade, "gC")
    chips.append('<span class="badge %s">Grade %s</span>' % (gcls, grade))
    if ratio:
        chips.append('<span class="badge r%d">Value: %s</span>' % (RATIO_ORDER[ratio], ratio))
    for k in ("口径",):
        if t.get(k):
            chips.append('<span class="tag">Basis: %s</span>' % (t[k],))
    label_of = {"钱": "Money", "时间": "Time", "毅力": "Willpower"}
    value_of = {"0": "none", "少": "little", "多": "a lot", "中": "moderate",
                "否": "none", "些": "some", "是": "yes"}
    for k in ("钱", "时间", "毅力"):
        if t.get(k):
            chips.append('<span class="tag">%s: %s</span>' % (label_of[k], value_of.get(t[k], t[k])))
    if t.get("收益"):
        bl = {"大": "large", "中": "medium", "小": "small"}
        chips.append('<span class="tag">Benefit: %s</span>' % bl.get(t["收益"], t["收益"]))

    rows = []
    for k, label in (("成本", "Cost"), ("收益", "Benefit")):
        if f.get(k):
            rows.append('<div class="f"><b>%s</b><div>%s</div></div>' % (label, inline(f[k])))
    if f.get("备注"):
        rows.append('<div class="f note"><b>Note</b><div>%s</div></div>' % inline(f["备注"]))

    src = f.get("来源", "")
    n = link_count(src)
    src_html = ""
    if src:
        src_html = ('<details class="src"><summary>Sources%s</summary>'
                    '<div class="sbody">%s</div></details>'
                    % (" (%d references)" % n if n else "", inline(src)))

    return ('<article class="card" id="s%d-%d" data-grade="%s" data-ratio="%s">'
            '<div class="chead"><span class="num">%d</span><h3>%s</h3></div>'
            '<div class="chips">%s</div>'
            '<p class="plain">%s</p>'
            '<div class="fields">%s</div>%s</article>') % (
        sec_no, e["no"], grade, ratio or "-", e["no"], inline(e["title"]),
        "".join(chips), inline(f.get("说人话", "")), "".join(rows), src_html)


JS = r"""
const cards=[...document.querySelectorAll('.card')];
const secs=[...document.querySelectorAll('section')];
const bar=document.querySelector('.bar');
const q=document.getElementById('q');
const cnt=document.getElementById('cnt');
const jump=document.getElementById('jump');
const fAll=document.getElementById('f-all');
const fA=document.getElementById('f-a');
const fP=document.getElementById('f-plain');
const themeBtn=document.getElementById('theme');
const topBtn=document.getElementById('top');
let grade=null, plainOnly=false;

/* The top bar's height changes as it wraps; JS measures it so that anchor jumps
   are not hidden underneath the bar */
function syncBar(){
  const h=Math.round(bar.getBoundingClientRect().height);
  document.documentElement.style.setProperty('--bar', h+'px');
}

function clearMarks(root){
  const ms=[...root.querySelectorAll('mark')];
  ms.forEach(m=>m.replaceWith(document.createTextNode(m.textContent)));
  if(ms.length) root.normalize();
}
function markAll(root,term){
  if(!term) return;
  const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode(n){
    if(!n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
    const p=n.parentElement;
    if(!p) return NodeFilter.FILTER_REJECT;
    if(p.closest('script,style,mark,a')) return NodeFilter.FILTER_REJECT;
    return NodeFilter.FILTER_ACCEPT;
  }});
  const nodes=[]; while(w.nextNode()) nodes.push(w.currentNode);
  const t=term.toLowerCase();
  nodes.forEach(n=>{
    const raw=n.nodeValue.toLowerCase();
    if(raw.indexOf(t)<0) return;
    const frag=document.createDocumentFragment();
    let i=raw.indexOf(t), last=0;
    while(i>=0){
      frag.appendChild(document.createTextNode(n.nodeValue.slice(last,i)));
      const m=document.createElement('mark');
      m.textContent=n.nodeValue.slice(i,i+t.length);
      frag.appendChild(m);
      last=i+t.length; i=raw.indexOf(t,last);
    }
    frag.appendChild(document.createTextNode(n.nodeValue.slice(last)));
    n.replaceWith(frag);
  });
}
function apply(){
  const term=q.value.trim().toLowerCase();
  clearMarks(document.querySelector('main'));
  let shown=0;
  cards.forEach(c=>{
    let ok=true;
    if(grade && c.dataset.grade!==grade) ok=false;
    if(ok && term && !c.textContent.toLowerCase().includes(term)) ok=false;
    c.classList.toggle('hidden',!ok);
    if(ok) shown++;
  });
  secs.forEach(s=>{
    const n=s.querySelectorAll('.card:not(.hidden)').length;
    s.classList.toggle('hidden',n===0);
    if(jump){
      const o=jump.querySelector('option[value="'+s.id+'"]');
      if(o) o.disabled=(n===0);
    }
  });
  document.getElementById('empty').classList.toggle('hidden',shown>0);
  cnt.textContent=shown+' / '+cards.length+' items';
  if(term) markAll(document.querySelector('main'),term);
  document.querySelectorAll('.toc a').forEach(a=>{
    const el=document.getElementById(a.getAttribute('href').slice(1));
    a.classList.toggle('hidden',!el||el.classList.contains('hidden'));
  });
}
let timer=null;
q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(apply,90);});
function setMode(mode){
  grade=(mode==='A')?'A':null;
  plainOnly=(mode==='plain');
  document.body.classList.toggle('plain-only',plainOnly);
  const map={'all':fAll,'A':fA,'plain':fP};
  Object.keys(map).forEach(k=>map[k].setAttribute('aria-pressed',String(k===mode)));
  apply();
}
fAll.onclick=()=>setMode('all');
fA.onclick=()=>setMode('A');
fP.onclick=()=>setMode('plain');
fAll.setAttribute('aria-pressed','true');

if(jump){
  jump.addEventListener('change',()=>{
    const el=document.getElementById(jump.value);
    if(el) el.scrollIntoView({block:'start'});
  });
}
themeBtn.onclick=()=>{
  const cur=document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark';
  document.documentElement.setAttribute('data-theme',cur);
  try{localStorage.setItem('hltb-theme',cur);}catch(e){}
};
try{
  const t=localStorage.getItem('hltb-theme');
  if(t) document.documentElement.setAttribute('data-theme',t);
  else if(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches)
    document.documentElement.setAttribute('data-theme','dark');
}catch(e){}
document.addEventListener('keydown',e=>{
  if(e.key==='/'&&document.activeElement!==q&&!/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)){
    e.preventDefault();q.focus();
  }
  if(e.key==='Escape'&&document.activeElement===q){q.value='';apply();q.blur();}
});
topBtn.onclick=()=>window.scrollTo({top:0,behavior:'smooth'});
/* Scroll state: (1) collapse the top bar (mobile), (2) show the back-to-top button.
   Throttled with rAF so it does not run on every frame while scrolling; the threshold
   has a hysteresis band to prevent flickering right at the boundary. */
let compact=false, ticking=false;
function onScroll(){
  const y=window.scrollY;
  const want = compact ? (y>200) : (y>420);
  if(want!==compact){compact=want;document.body.classList.toggle('compact',compact);syncBar();}
  topBtn.classList.toggle('show',y>900);
}
addEventListener('scroll',()=>{
  if(ticking) return;
  ticking=true;
  requestAnimationFrame(()=>{ticking=false;onScroll();});
},{passive:true});
addEventListener('resize',syncBar);
if(document.fonts&&document.fonts.ready) document.fonts.ready.then(syncBar);
syncBar();

const links=[...document.querySelectorAll('.toc a')];
const io=new IntersectionObserver(es=>{
  es.forEach(e=>{ if(e.isIntersecting){
    if(e.target.classList.contains('card'))
      links.forEach(a=>a.classList.toggle('active',a.getAttribute('href')==='#'+e.target.id));
    else if(jump && e.target.tagName==='SECTION')
      jump.value=e.target.id;
  }});
},{rootMargin:'-70px 0px -75% 0px'});
cards.forEach(c=>io.observe(c));
if(jump) secs.forEach(s=>io.observe(s));
"""


def main():
    sec_toc = []
    sec_html = []
    jump_opts = []
    total = 0
    grade_cnt = {"A": 0, "B": 0, "C": 0}
    link_total = 0

    for n in SECTIONS:
        p = find_file(n)
        title, intro, entries = parse(p)
        cards = []
        links = []
        for e in entries:
            g = (e["fields"].get("证据等级") or "?").strip()[:1]
            if g in grade_cnt:
                grade_cnt[g] += 1
            total += 1
            link_total += link_count(e["fields"].get("来源", "")) + link_count(e["fields"].get("备注", ""))
            cards.append(render_entry(e, n))
            r = ratio_of(parse_tags(e["tags_raw"]))
            short = e["title"] if len(e["title"]) <= 34 else e["title"][:33] + "…"
            links.append('<a href="#s%d-%d" title="%s"><span class="dot d%d"></span>'
                         '<i>%d</i><span>%s</span></a>'
                         % (n, e["no"], html.escape(e["title"], quote=True),
                            RATIO_ORDER.get(r, 2), e["no"], html.escape(short)))
        sec_toc.append('<div class="grp"><div class="gt">%s<small>%d items</small></div>%s</div>'
                       % (inline(title), len(entries), "".join(links)))
        sec_html.append(
            '<section id="sec%d"><div class="sec-h"><h2>%s</h2>'
            '<span class="meta">%d items</span></div>%s%s</section>'
            % (n, inline(title), len(entries),
               ('<p class="intro">%s</p>' % inline(" ".join(intro))) if intro else "",
               "".join(cards)))
        jump_opts.append('<option value="sec%d">%s</option>' % (n, html.escape(title)))

    rev, rev_date = source_rev()

    head = ('<!DOCTYPE html><html lang="en" data-theme="light"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<meta name="color-scheme" content="light dark">'
            '<meta name="theme-color" media="(prefers-color-scheme: light)" content="#ffffff">'
            '<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#1b1b1f">'
            '<meta name="description" content="The Cost-Effective Life Guide (高性价比人生指南), %s, '
            '%d suggestions in total, each labeled with cost, benefit, evidence grade (A/B/C) '
            'and links to the original sources. Single file, zero dependencies, readable offline.">'
            '<title>The Cost-Effective Life Guide · %s</title><style>%s</style></head><body>'
            % (SCOPE, total, SCOPE, CSS))

    bar = ('<header class="bar"><h1>The Cost-Effective Life Guide<small>%s</small></h1>'
           '<select class="jump" id="jump" aria-label="Jump to a section">%s</select>'
           '<div class="spacer"></div>'
           '<button class="btn" id="f-all">All</button>'
           '<button class="btn" id="f-a">Grade A only</button>'
           '<button class="btn" id="f-plain">Plain words only</button>'
           '<div class="search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/>'
           '<path d="M20 20l-3.5-3.5"/></svg>'
           '<input id="q" type="search" placeholder="Search titles, plain words, benefits…" autocomplete="off">'
           '<kbd>/</kbd></div>'
           '<span class="count" id="cnt">%d / %d items</span>'
           '<button class="btn" id="theme">Light/Dark</button></header>' % (
               SCOPE, "".join(jump_opts), total, total))

    src_line = 'Data source: <a href="%s" target="_blank" rel="noopener">eternity4719/HowToLiveBetter</a>' % UPSTREAM
    src_line += ' (Unlicense, public domain)'
    if rev:
        src_line += '; data as of <span style="font-family:var(--mono)">%s</span>%s' % (
            rev, ' (%s)' % rev_date if rev_date else '')

    footer = ('<footer>%s.<br>'
              'The "Plain words" and "Benefit" columns quote the original book verbatim, without rewriting; '
              'this page has %d items in total — %d Grade A, %d Grade B, %d Grade C — with %d outbound reference links.<br>'
              'Self-contained single file: it loads no external resources (except the reference links in the text) '
              'and can be read offline. Generated by build.py.</footer>'
              % (src_line, total, grade_cnt["A"], grade_cnt["B"], grade_cnt["C"], link_total))

    shell = ('<div class="shell"><aside class="toc">%s</aside><main>%s'
             '<div class="empty hidden" id="empty">No matching items</div>%s'
             '</main></div>'
             '<button id="top" title="Back to top" aria-label="Back to top">↑</button>'
             % ("".join(sec_toc), "".join(sec_html), footer))

    # Note: the JS variable holds only the script body; the <script> open/close tags
    # are concatenated here. An earlier version omitted the opening tag, which made
    # the whole script render as plain text at the bottom of the page and never run.
    out = head + bar + shell + "<script>" + JS + "</script></body></html>"

    if ARGS.out:
        name = Path(ARGS.out)
        if not name.is_absolute():
            name = HERE / name
    else:
        name = HERE / ("The_Cost-Effective_Life_Guide_%s.html" % "_".join("sec%d" % n for n in SECTIONS))

    name.write_text(out, encoding="utf-8")
    print("Scope %s | sections %d | items %d | A %d B %d C %d | outbound links %d"
          % (SCOPE, len(SECTIONS), total, grade_cnt["A"], grade_cnt["B"], grade_cnt["C"], link_total))
    print("Output: %s  (%d bytes)" % (name, len(out.encode("utf-8"))))


if __name__ == "__main__":
    main()
