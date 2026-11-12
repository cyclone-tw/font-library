# AGENTS.md

給 coding agent 的規則。使用說明見 README.md。

## 做網頁、學習單、簡報要選字型時

1. 先讀 `fonts.toml`，從這裡挑字型；不要憑記憶判斷授權。
2. 網頁：`web.google_fonts` 有值就用 Google Fonts；否則用 `scripts/fontlib.py subset` 裁出用到的字。
   不要把完整字型檔放進網頁或其他 repo。
3. `license.modify = false` 的字型不能裁字、不能轉網頁字型。
4. 裁切版的 `font-family` 用 `subset` 指令印出的名稱（有保留名稱的字型會被改名）。
5. 作品頁尾或版權頁放 `license.attribution`；`attribution_required = true` 的一定要放。

## 改這個 repo 時

- `fonts.toml` 是唯一正本，`docs/index.html` 由 `showcase` 指令產生，不要手改；要改版面就改 `scripts/showcase.template.html` 再重產。
- `docs/` 是 GitHub Pages 網站。`docs/about.html` 手寫維護，個人 IP 文字照 `personal-ip` skill，不自行改寫。
- `docs/assets/` 的奧瑞恩插圖與龍頭像不是 MIT，不要拿去別的 repo。
- 授權欄位要讀過上游授權原文才填，`license.verified` 寫查證日期；部落格、整理站只能拿來發現新字型。
- 字型檔（`.ttf`／`.otf`／`.woff2`／`.zip`）不進 git，`.gitignore` 已擋。
- 改完跑 `python3 scripts/fontlib.py check`。
