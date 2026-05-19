# Garmin CSV to GitHub Pages Dashboard

這個 repo 的流程已改成不使用 Garmin API、Google Sheets、Google Drive 或 Cloudflare Workers。

## 流程

1. 手動登入 Garmin Connect 並下載步數 CSV。
2. 把 CSV 上傳到 `data/raw/<member>/`，例如：
   - `data/raw/york/2026-05-19.csv`
   - `data/raw/rita/2026-05-19.csv`
3. Push 到 GitHub 後，GitHub Actions 會執行 `build_dashboard.py`。
4. 腳本會產生：
   - `data/processed/steps.json`
   - `site/index.html`
5. GitHub Pages 會發布 `site/`，手機可直接打開 dashboard 網址。

## 本機產生 dashboard

```powershell
python build_dashboard.py
```

產生結果：

```text
data/processed/steps.json
site/index.html
```

## CSV 規則

- 每個成員一個資料夾：`data/raw/<member>/`。
- 成員名稱會從資料夾名稱推導，`data/raw/york/...` 會顯示為 `York`。
- 支援 Garmin 目前常見的欄位：
  - 日期
  - 實際步數
  - 目標步數
- 同一位成員同一天若有多個 CSV，會保留較新的檔案資料；若修改時間相同，使用檔名排序較後者。

## GitHub Pages

此 workflow 使用 GitHub Pages 官方 Actions 部署 `site/`。請到 GitHub repo 的 Settings → Pages，將來源設定為 GitHub Actions。

注意：GitHub Pages 從 private repo 發布可能需要 GitHub Pro、Team 或 Enterprise 方案。若目前方案不支援，可改成 Cloudflare Pages 連接 private GitHub repo，但資料與 build 流程仍可維持本 repo 的設計。

## 舊流程狀態

舊的 Google Sheets、Google Drive、Garmin API、Cloudflare Workers 自動化已移除。現在唯一的必要手動步驟是從 Garmin Connect 下載 CSV，並上傳到 GitHub。
