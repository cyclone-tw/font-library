#!/usr/bin/env python3
"""font-library 管理工具。

用法：
  python3 scripts/fontlib.py list                  列出清單
  python3 scripts/fontlib.py check                 檢查 fonts.toml 欄位
  python3 scripts/fontlib.py fetch [id ...|--all]  下載字型，核對／記錄 sha256
  python3 scripts/fontlib.py licenses [id ...]     把授權原文存進 licenses/<id>/
  python3 scripts/fontlib.py path <id>             印出本機字型檔路徑
  python3 scripts/fontlib.py install <id> ...      裝到 ~/Library/Fonts（Word、Pages 用）
  python3 scripts/fontlib.py attribution <id> ...  印出署名文字
  uv run --with fonttools --with brotli python scripts/fontlib.py subset <id> --text-file page.html -o out.woff2
  uv run --with fonttools --with brotli python scripts/fontlib.py showcase

字型檔放在 $FONT_LIBRARY_HOME（預設 ~/Cyclone-System/SpedAI-Assets/fonts），不進 git。
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import html
import json
import os
import re
import shutil
import sys
import tomllib
import urllib.parse
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "fonts.toml"
LOCK = ROOT / "fonts.lock.json"
LICENSES = ROOT / "licenses"
HOME = Path(os.environ.get("FONT_LIBRARY_HOME", Path.home() / "Cyclone-System/SpedAI-Assets/fonts")).expanduser()
UA = {"User-Agent": "font-library/1 (+https://github.com)"}
IVS_RANGE = range(0xE01E0, 0xE01F0)  # bpmfvs 與臺灣拼音楷用到的異體字選擇子

REQUIRED = {
    "font": ["id", "name", "name_en", "style", "features", "use", "notes"],
    "source": ["kind"],
    "license": ["spdx", "summary", "commercial", "modify", "attribution_required", "reserved_names", "attribution", "verified"],
}
KINDS = {"github-release": ["repo", "tag", "asset"], "github-file": ["repo", "ref", "path", "version"], "url": ["url", "version"], "manual": ["homepage"]}


# ───────────── 清單與 lock ─────────────

def load_fonts() -> list[dict]:
    with MANIFEST.open("rb") as f:
        return tomllib.load(f)["font"]


def get_font(fid: str) -> dict:
    for f in load_fonts():
        if f["id"] == fid:
            return f
    sys.exit(f"找不到字型 id：{fid}（用 list 看全部）")


def load_lock() -> dict:
    return json.loads(LOCK.read_text()) if LOCK.exists() else {}


def save_lock(lock: dict) -> None:
    LOCK.write_text(json.dumps(dict(sorted(lock.items())), ensure_ascii=False, indent=2) + "\n")


def version_of(font: dict) -> str:
    s = font["source"]
    return s.get("tag") or s.get("version") or "unknown"


def source_url(font: dict) -> str | None:
    s = font["source"]
    if s["kind"] == "github-release":
        return f"https://github.com/{s['repo']}/releases/download/{s['tag']}/{urllib.parse.quote(s['asset'])}"
    if s["kind"] == "github-file":
        return f"https://raw.githubusercontent.com/{s['repo']}/{s['ref']}/{urllib.parse.quote(s['path'])}"
    if s["kind"] == "url":
        return s["url"]
    return None


def font_dir(font: dict) -> Path:
    return HOME / font["id"] / version_of(font)


def local_font_file(font: dict) -> Path | None:
    entry = load_lock().get(font["id"])
    if not entry or entry.get("version") != version_of(font):
        return None
    p = font_dir(font) / entry["file"]
    return p if p.exists() else None


# ───────────── 指令 ─────────────

def cmd_list(_):
    lock = load_lock()
    for f in load_fonts():
        mark = "已下載" if local_font_file(f) else ("手動" if f["source"]["kind"] == "manual" else "未下載")
        gf = f.get("web", {}).get("google_fonts") or "-"
        print(f"{f['id']:<20} {f['name']:<10} {f['style']:<5} {'/'.join(f['license']['spdx']):<22} GF:{gf:<20} {mark}")
    _ = lock


def cmd_check(_):
    errors, ids = [], set()
    for i, f in enumerate(load_fonts()):
        where = f.get("id", f"#{i}")
        for k in REQUIRED["font"]:
            if k not in f:
                errors.append(f"{where}: 缺 {k}")
        if f.get("id") in ids:
            errors.append(f"{where}: id 重複")
        ids.add(f.get("id"))
        src, lic = f.get("source", {}), f.get("license", {})
        for k in REQUIRED["source"]:
            if k not in src:
                errors.append(f"{where}: source 缺 {k}")
        for k in KINDS.get(src.get("kind"), []):
            if k not in src:
                errors.append(f"{where}: source.kind={src.get('kind')} 需要 {k}")
        if src.get("kind") not in KINDS:
            errors.append(f"{where}: 未知的 source.kind {src.get('kind')}")
        for k in REQUIRED["license"]:
            if k not in lic:
                errors.append(f"{where}: license 缺 {k}")
        if lic.get("verified") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", lic["verified"]):
            errors.append(f"{where}: license.verified 要寫 YYYY-MM-DD")
        if not re.fullmatch(r"[a-z0-9-]+", f.get("id", "")):
            errors.append(f"{where}: id 只能用小寫英數與 -")
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    print(f"OK：{len(ids)} 套字型")


def download(url: str, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r, tmp.open("wb") as out:
        while chunk := r.read(1 << 20):
            h.update(chunk)
            out.write(chunk)
    tmp.replace(dest)
    return h.hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def pick_member(names: list[str], pattern: str) -> str:
    hits = [n for n in names if not n.endswith("/") and fnmatch.fnmatch(Path(n).name, pattern)]
    if len(hits) != 1:
        listing = "\n  ".join(n for n in names if re.search(r"\.(ttf|otf|ttc)$", n, re.I))
        sys.exit(f"member「{pattern}」比對到 {len(hits)} 個檔案，請改 fonts.toml。壓縮檔內的字型：\n  {listing}")
    return hits[0]


def cmd_fetch(args):
    fonts = load_fonts() if args.all else [get_font(i) for i in args.ids]
    if not fonts:
        sys.exit("請給字型 id，或用 --all")
    lock = load_lock()
    for f in fonts:
        fid, src = f["id"], f["source"]
        if src["kind"] == "manual":
            print(f"[略過] {fid}：需手動下載，見 {src['homepage']}")
            continue
        url, d = source_url(f), font_dir(f)
        raw = d / Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name
        prev = lock.get(fid, {})
        if raw.exists():
            digest = sha256_file(raw)
        else:
            print(f"[下載] {fid} ← {url}")
            digest = download(url, raw)
        if prev.get("version") == version_of(f) and prev.get("sha256") and prev["sha256"] != digest:
            sys.exit(f"[錯誤] {fid} sha256 與 fonts.lock.json 不符，上游檔案可能被換掉：\n  lock {prev['sha256']}\n  now  {digest}")
        file_name, member = raw.name, None
        if zipfile.is_zipfile(raw):
            with zipfile.ZipFile(raw) as z:
                member = pick_member(z.namelist(), src.get("member", "*.ttf"))
                out = d / Path(member).name
                with z.open(member) as m, out.open("wb") as o:
                    shutil.copyfileobj(m, o)
                file_name = out.name
        lock[fid] = {
            "version": version_of(f), "url": url, "sha256": digest,
            "archive_member": member, "file": file_name,
            "file_sha256": sha256_file(d / file_name),
            "fetched": prev.get("fetched") if prev.get("sha256") == digest else date.today().isoformat(),
        }
        save_lock(lock)
        print(f"[完成] {fid}：{d / file_name}")


def cmd_licenses(args):
    fonts = [get_font(i) for i in args.ids] if args.ids else load_fonts()
    for f in fonts:
        src, out = f["source"], LICENSES / f["id"]
        got = []
        if src.get("license_url"):
            out.mkdir(parents=True, exist_ok=True)
            dest = out / Path(urllib.parse.urlparse(src["license_url"]).path).name
            download(src["license_url"], dest)
            got.append(dest.name)
        if src.get("license_members"):
            entry = load_lock().get(f["id"])
            if not entry:
                print(f"[略過] {f['id']}：授權在壓縮檔內，先 fetch")
                continue
            arc = font_dir(f) / Path(urllib.parse.urlparse(entry["url"]).path).name
            with zipfile.ZipFile(arc) as z:
                for pat in src["license_members"]:
                    m = pick_member(z.namelist(), pat)
                    out.mkdir(parents=True, exist_ok=True)
                    (out / Path(m).name).write_bytes(z.read(m))
                    got.append(Path(m).name)
        print(f"{f['id']}: {', '.join(got) if got else '（無自動來源，見 licenses/' + f['id'] + '/NOTE.md）'}")


def cmd_path(args):
    p = local_font_file(get_font(args.id))
    if not p:
        sys.exit(f"{args.id} 尚未下載：python3 scripts/fontlib.py fetch {args.id}")
    print(p)


def cmd_install(args):
    target = Path.home() / "Library/Fonts"
    for fid in args.ids:
        p = local_font_file(get_font(fid))
        if not p:
            sys.exit(f"{fid} 尚未下載：python3 scripts/fontlib.py fetch {fid}")
        shutil.copy2(p, target / p.name)
        print(f"[安裝] {p.name} → {target}（Office 要完全結束再開才看得到）")


def cmd_attribution(args):
    for fid in args.ids:
        print(get_font(fid)["license"]["attribution"])


# ───────────── 裁字（需要 fonttools） ─────────────

def safe_family(font: dict) -> str:
    """裁過的字型算修改版；有保留名稱就改名，避免違反 OFL 的 Reserved Font Name。"""
    reserved = font["license"]["reserved_names"]
    name = font["name_en"]
    if any(r.lower() in name.lower() for r in reserved) or any(r in font["name"] for r in reserved):
        name = "FL " + re.sub(r"-+", "-", re.sub("|".join(map(re.escape, reserved)), "", font["id"], flags=re.I)).strip("-")
    return name


def subset_bytes(font: dict, text: str, family: str) -> bytes:
    if not font["license"]["modify"]:
        sys.exit(f"{font['id']} 的授權禁止改作，不能裁字或轉網頁字型")
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except ImportError:
        sys.exit("需要 fonttools：uv run --with fonttools --with brotli python scripts/fontlib.py ...")
    src = local_font_file(font)
    if not src:
        sys.exit(f"{font['id']} 尚未下載：python3 scripts/fontlib.py fetch {font['id']}")
    opts = subset.Options()
    opts.layout_features = ["*"]
    opts.flavor = "woff2"
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.drop_tables += ["DSIG"]
    tt = TTFont(src, fontNumber=0, lazy=False)
    unicodes = {ord(c) for c in text} | set(IVS_RANGE)
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=unicodes)
    sub.subset(tt)
    if family != font["name_en"]:
        for rec in tt["name"].names:
            if rec.nameID in (1, 4, 16, 21):
                rec.string = family
            elif rec.nameID in (3, 6):
                rec.string = family.replace(" ", "") + "-Subset"
    import io
    buf = io.BytesIO()
    tt.flavor = "woff2"
    tt.save(buf)
    return buf.getvalue()


def cmd_subset(args):
    font = get_font(args.id)
    text = args.text or ""
    if args.text_file:
        text += Path(args.text_file).read_text(encoding="utf-8")
    if not text:
        sys.exit("請給 --text 或 --text-file")
    family = safe_family(font)
    data = subset_bytes(font, text, family)
    Path(args.output).write_bytes(data)
    print(f"[完成] {args.output}（{len(data)/1024:.1f} KB，font-family: '{family}'）")
    print(f"署名：{font['license']['attribution']}")


# ───────────── 說明頁 ─────────────

SAMPLES = {
    "注音": "小朋友在圖書館看繪本，覺得好快樂！",
    "漢語拼音": "我們去銀行，行人很多；長大以後頭髮很長。",
    "default": "小朋友在圖書館看繪本，覺得好快樂！",
}
GRID_CHAR = "學"
LATIN = "ABC abc 0123456789"
IVS_DEMO = "會議／會\U000E01E1計"  # 第二讀音 ㄎㄨㄞˋ


def sample_for(font: dict) -> str:
    if "注音" in font["features"]:
        return SAMPLES["注音"]
    if "漢語拼音" in font["features"]:
        return SAMPLES["漢語拼音"]
    return SAMPLES["default"]


REPO_URL = "https://github.com/cyclone-tw/font-library"


def cmd_showcase(args):
    fonts = load_fonts()
    faces, cards, rows, gf_families = [], [], [], []
    for f in fonts:
        sample = sample_for(f)
        demo = IVS_DEMO if "IVS 選破音字" in f["features"] else ""
        text = sample + GRID_CHAR + LATIN + demo + "／"
        css_family, render = None, "none"
        if f["license"]["modify"] and local_font_file(f):
            css_family = f"fl-{f['id']}"
            data = subset_bytes(f, text, safe_family(f))
            faces.append(f"@font-face{{font-family:'{css_family}';src:url(data:font/woff2;base64,{base64.b64encode(data).decode()}) format('woff2');font-display:block}}")
            render = "embed"
        elif f.get("web", {}).get("google_fonts"):
            css_family = f["web"]["google_fonts"]
            gf_families.append((css_family, text))
            render = "google"
        cards.append(card_html(f, css_family, sample, demo, render))
        rows.append(license_row(f))
    gf_links = "\n".join(
        f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={urllib.parse.quote_plus(fam)}&text={urllib.parse.quote(t)}&display=swap">'
        for fam, t in gf_families
    )
    rfn = "、".join(f"{f['name']}（{'、'.join(f['license']['reserved_names'])}）"
                   for f in fonts if f["license"]["reserved_names"])
    values = {
        "GF_LINKS": gf_links,
        "FONT_FACES": "\n".join(faces),
        "CARDS": "\n".join(cards),
        "LICENSE_ROWS": "\n".join(rows),
        "RFN_LIST": html.escape(rfn),
        "COUNT": str(len(fonts)),
        "N_COMMERCIAL": str(sum(f["license"]["commercial"] for f in fonts)),
        "N_ZHUYIN": str(sum("注音" in f["features"] for f in fonts)),
        "N_GF": str(sum(bool(f.get("web", {}).get("google_fonts")) for f in fonts)),
        "N_OFL": str(sum(f["license"]["spdx"] == ["OFL-1.1"] for f in fonts)),
        "VERIFIED": max(f["license"]["verified"] for f in fonts),
        "BUILT": date.today().isoformat(),
    }
    page = (ROOT / "scripts/showcase.template.html").read_text(encoding="utf-8")
    for k, v in values.items():
        page = page.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", page)
    if left:
        sys.exit(f"[錯誤] 範本還有沒填的欄位：{sorted(set(left))}")
    out = Path(args.output)
    out.write_text(page, encoding="utf-8")
    print(f"[完成] {out}（{out.stat().st_size/1024:.0f} KB，{len(fonts)} 套字型）")


def chip(text: str, cls: str = "") -> str:
    return f'<span class="chip {cls}">{html.escape(text)}</span>'


def web_route(f: dict) -> tuple[str, str]:
    """回傳（狀態, 說明）：這套字型放上網頁的做法。"""
    if f.get("web", {}).get("google_fonts"):
        return "yes", f"Google Fonts 直接載入（{f['web']['google_fonts']}）"
    if f["license"]["modify"]:
        return "yes", "用 fontlib.py subset 裁出用到的字"
    return "no", "不能轉成網頁字型"


def uses_html(f: dict) -> str:
    lic = f["license"]
    e = html.escape
    rn = "、".join(lic["reserved_names"])
    items = [("yes", "印學習單、做簡報", "安裝到電腦後直接用")]
    items.append(("yes", "收費教材、商業作品", "可以") if lic["commercial"] else ("no", "收費教材、商業作品", "不可以"))
    items.append((*web_route(f)[:1], "放上網頁", web_route(f)[1]))
    if not lic["modify"]:
        items.append(("no", "修改、裁字", "授權禁止改作"))
    elif rn:
        items.append(("warn", "修改、裁字", f"可以，但要換名字（保留名稱：{rn}）"))
    else:
        items.append(("yes", "修改、裁字", "可以"))
    items.append(("warn", "署名", "一定要放，用下方「複製署名」") if lic["attribution_required"]
                 else ("yes", "署名", "不強制，建議放"))
    mark = {"yes": "✓", "no": "✕", "warn": "!"}
    li = "".join(f'<li class="{c}"><i aria-hidden="true">{mark[c]}</i><b>{e(t)}</b><span>{e(d)}</span></li>'
                 for c, t, d in items)
    return f'<ul class="can" aria-label="可以怎麼用">{li}</ul>'


def upstream_link(f: dict) -> str:
    src = f["source"]
    if src["kind"] in ("github-release", "github-file"):
        return f"https://github.com/{src['repo']}"
    return src.get("homepage") or src.get("url")


def card_html(f: dict, family: str | None, sample: str, demo: str, render: str) -> str:
    lic = f["license"]
    e = html.escape
    tags = [v for k, v in {"注音": "zhuyin", "漢語拼音": "pinyin"}.items() if k in f["features"]]
    if lic["modify"]:
        tags.append("web")
    if f.get("web", {}).get("google_fonts"):
        tags.append("gf")
    if not lic["attribution_required"]:
        tags.append("noattr")
    style_attr = f" style=\"font-family:'{family}',var(--fallback)\"" if family else ""
    if family:
        specimen = (f'<div class="specimen"{style_attr}>'
                    f'<div class="grid-cell" aria-hidden="true"><span>{GRID_CHAR}</span></div>'
                    f'<p class="sample" lang="zh-Hant-TW">{e(sample)}</p></div>')
        if demo:
            specimen += (f'<p class="ivs"><span{style_attr}>{e(demo)}</span>'
                         f'<small>同一個「會」：預設讀音，與加上 IVS 後的第二讀音</small></p>')
    else:
        specimen = ('<div class="specimen none"><p>這套字型的授權禁止改作，說明頁不嵌入裁切後的字型。'
                    '請整檔安裝在電腦上使用。</p></div>')
    src_label = {"embed": "樣張：本機裁字嵌入", "google": "樣張：Google Fonts", "none": "沒有樣張"}[render]
    return f'''<article class="card" data-style="{e(f['style'])}" data-tags="{' '.join(tags)}" id="{e(f['id'])}">
  <header>
    <h3>{e(f['name'])}</h3>
    <p class="en">{e(f['name_en'])}</p>
    <div class="chips">{chip(f['style'], 'style')}{''.join(chip(x) for x in f['features'])}</div>
  </header>
  {specimen}
  {uses_html(f)}
  <p class="lic"><strong>{e(' + '.join(lic['spdx']))}</strong>{e(lic['summary'])}</p>
  <p class="notes">{e(f['notes'])}</p>
  <p class="use">適合：{e('、'.join(f['use']))}</p>
  <div class="attr"><code id="attr-{e(f['id'])}">{e(lic['attribution'])}</code><button type="button" class="copy" data-target="attr-{e(f['id'])}">複製署名</button></div>
  <ul class="meta">
    <li>版本 {e(version_of(f))}</li>
    <li>授權查證 {e(lic['verified'])}</li>
    <li><a href="{REPO_URL}/tree/main/licenses/{e(f['id'])}" target="_blank" rel="noopener">授權原文</a></li>
    <li><a href="{e(upstream_link(f))}" target="_blank" rel="noopener">上游來源</a></li>
    <li>{src_label}</li>
  </ul>
</article>'''


def license_row(f: dict) -> str:
    lic = f["license"]
    e = html.escape
    yes, no = '<span class="y">✓</span>', '<span class="n">✕</span>'
    if not lic["modify"]:
        mod = f"{no}禁止"
    elif lic["reserved_names"]:
        mod = '<span class="c">!</span>可以，要改名'
    else:
        mod = f"{yes}可以"
    attr = '<span class="c">!</span>必須' if lic["attribution_required"] else "非必要，建議放"
    state, route = web_route(f)
    route = {"yes": yes, "no": no}[state] + e(route.split("（")[0])
    return (f'            <tr><th scope="row"><a href="#{e(f["id"])}">{e(f["name"])}</a></th>'
            f'<td><code>{e(" + ".join(lic["spdx"]))}</code></td>'
            f'<td>{yes if lic["commercial"] else no}</td><td>{mod}</td><td>{attr}</td>'
            f'<td>{e("、".join(lic["reserved_names"])) or "—"}</td><td>{route}</td>'
            f'<td><a href="{REPO_URL}/tree/main/licenses/{e(f["id"])}" target="_blank" rel="noopener">licenses/{e(f["id"])}</a></td></tr>')


def main():
    p = argparse.ArgumentParser(description="font-library 管理工具")
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("list").set_defaults(fn=cmd_list)
    sp.add_parser("check").set_defaults(fn=cmd_check)
    a = sp.add_parser("fetch"); a.add_argument("ids", nargs="*"); a.add_argument("--all", action="store_true"); a.set_defaults(fn=cmd_fetch)
    a = sp.add_parser("licenses"); a.add_argument("ids", nargs="*"); a.set_defaults(fn=cmd_licenses)
    a = sp.add_parser("path"); a.add_argument("id"); a.set_defaults(fn=cmd_path)
    a = sp.add_parser("install"); a.add_argument("ids", nargs="+"); a.set_defaults(fn=cmd_install)
    a = sp.add_parser("attribution"); a.add_argument("ids", nargs="+"); a.set_defaults(fn=cmd_attribution)
    a = sp.add_parser("subset"); a.add_argument("id"); a.add_argument("--text"); a.add_argument("--text-file"); a.add_argument("-o", "--output", required=True); a.set_defaults(fn=cmd_subset)
    a = sp.add_parser("showcase"); a.add_argument("-o", "--output", default=str(ROOT / "docs/index.html")); a.set_defaults(fn=cmd_showcase)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
