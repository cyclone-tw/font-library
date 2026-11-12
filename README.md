# font-library 教學字型庫

收集台灣教學網頁與學習單可以使用的開源字型，記錄來源、版本、授權與署名文字。
字型檔本身**不進 git**，由腳本依清單下載並核對 sha256。

- 說明頁：https://cyclone-tw.github.io/font-library/ （GitHub Pages，來源 `docs/`）
  - `docs/index.html` 由 `fonts.toml` 和 `scripts/showcase.template.html` 產生，含樣張與授權說明
  - `docs/about.html` 關於與聲明頁，手寫維護
- 清單正本：`fonts.toml`
- 下載紀錄與 sha256：`fonts.lock.json`（腳本寫入）
- 授權原文：`licenses/<id>/`
- 字型檔：`$FONT_LIBRARY_HOME`，預設 `~/Cyclone-System/SpedAI-Assets/fonts/<id>/<版本>/`

## 常用指令

```bash
python3 scripts/fontlib.py list                      # 看有哪些字型、哪些已下載
python3 scripts/fontlib.py fetch bpmf-zihi-kai-std   # 下載一套（--all 下載全部，約 400MB）
python3 scripts/fontlib.py path bpmf-zihi-kai-std    # 印出本機字型檔路徑
python3 scripts/fontlib.py install bpmf-zihi-kai-std # 裝到 ~/Library/Fonts（Word、Pages 用）
python3 scripts/fontlib.py attribution iansui        # 印出署名文字

# 網頁字型：只裁出頁面用到的字（需要 fonttools，用 uv 臨時帶入）
uv run --with fonttools --with brotli python scripts/fontlib.py \
  subset iansui --text-file lesson.html -o fonts/iansui-lesson.woff2

# 重產說明頁（會用到已下載的字型；沒下載但在 Google Fonts 上的改用 Google Fonts 樣張）
uv run --with fonttools --with brotli python scripts/fontlib.py showcase
```

`subset` 會做兩件授權相關的事：

1. 授權禁止改作（`modify = false`，例如教育部標準楷書）的字型直接拒絕。
2. 有保留名稱（Reserved Font Name）的字型，裁切版自動改名（例如「字嗨」→ `FL bpmf-kai-std`），
   因為 OFL 規定修改版不能沿用保留名稱。網頁 CSS 的 `font-family` 用指令印出的名稱。

注音字型（bpmfvs）用 IVS 選破音字，`subset` 會保留 U+E01E0–E01EF 的對應，裁切後破音字照樣能用。

## 網頁用哪一條路

| 情況 | 做法 |
|---|---|
| 字型在 Google Fonts 上（`web.google_fonts` 有值） | 直接 `<link>` Google Fonts，它會自動分片載入；最省事 |
| 不在 Google Fonts，或要離線 HTML | `subset` 裁出用到的字，woff2 跟網頁放一起 |
| 授權禁止改作 | 不放網頁；改用同類可改作的字型 |

不要把完整字型檔（常常 10–80MB）直接放進網頁。

## 清單格式

每套字型一筆 `[[font]]`：

| 欄位 | 說明 |
|---|---|
| `id` | 小寫英數與 `-`，也是資料夾名稱 |
| `name`／`name_en` | 中文名、英文名（英文名通常就是安裝後的字型名稱） |
| `style` | 楷書、手寫楷、手寫、黑體、明體、圓體、像素 |
| `features`／`use`／`notes` | 特色、適合用途、注意事項 |
| `source.kind` | `github-release`（repo＋tag＋asset）、`github-file`（repo＋釘選 commit＋path）、`url`（固定網址＋version）、`manual`（只能手動下載） |
| `source.member` | 下載的是壓縮檔時，要取出的字型檔名（可用 `*` 萬用字元，必須剛好比對到一個） |
| `source.license_url`／`license_members` | 授權原文的位置，`licenses` 指令會存進 `licenses/<id>/` |
| `license.spdx` | 授權代碼，可多個 |
| `license.commercial`／`modify`／`attribution_required` | 可否商用、可否修改裁字、是否必須署名 |
| `license.reserved_names` | OFL 保留名稱；修改版不能用 |
| `license.attribution` | 可直接貼到作品頁尾的署名文字 |
| `license.verified` | 讀過上游授權原文的日期 |
| `web.google_fonts` | Google Fonts 上的家族名稱；沒有就留空字串 |

## 新增一套字型

1. 讀上游的授權原文（不是部落格整理），填好 `fonts.toml`。
2. `python3 scripts/fontlib.py check`
3. `python3 scripts/fontlib.py fetch <id>`，再 `python3 scripts/fontlib.py licenses <id>`
4. 重產說明頁，commit `fonts.toml`、`fonts.lock.json`、`licenses/<id>/`、`docs/index.html`。

## 升級版本

改 `fonts.toml` 的 `tag`／`ref`／`version` 後重新 `fetch`。同一版本的檔案 sha256 若與
`fonts.lock.json` 不同，腳本會停下來：代表上游換了檔案，要先確認再處理。

## 授權

清單（`fonts.toml`）、腳本與網頁程式以 MIT 授權公開（見 `LICENSE`）。
`docs/assets/` 裡的奧瑞恩插圖與 Cyclone 龍頭像 © 2026 Cyclone，不在 MIT 授權範圍內。
各字型的授權見 `licenses/<id>/` 與 `fonts.toml`，以上游原文為準。
