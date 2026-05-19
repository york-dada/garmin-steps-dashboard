# 豬豬步數記分板

用 Garmin Connect 手動匯出的 CSV，產生多人步數排行榜，並透過 GitHub Pages 發布成手機可看的靜態頁面。

## 使用方式

1. 到 Garmin Connect 手動下載步數 CSV。
2. 在 GitHub 上把 CSV 上傳到對應成員資料夾：
   - `data/raw/york/`
   - `data/raw/rita/`
3. GitHub Actions 會自動執行 `build_dashboard.py`。
4. 程式會產生：
   - `data/processed/steps.json`
   - `site/index.html`
5. GitHub Pages 會發布 `site/`，更新線上 dashboard。

## CSV 命名

建議用日期命名，方便分辨版本：

```text
data/raw/york/2026-05-19.csv
data/raw/rita/2026-05-19.csv
```

成員名稱來自資料夾名稱，例如 `data/raw/york/...` 會顯示為 `York`。

## 本機預覽

在專案根目錄執行：

```powershell
python build_dashboard.py
```

完成後用瀏覽器打開：

```text
site/index.html
```

## 自動更新

`.github/workflows/build-and-deploy.yml` 會在以下情況自動重建並部署：

- `data/raw/**` 有新的 CSV
- `build_dashboard.py` 有更新
- `site/assets/**` 有更新
- 每天 00:00 UTC 固定跑一次
- 手動從 GitHub Actions 執行 `workflow_dispatch`

公開頁面只顯示彙整後的 dashboard，不會直接列出原始 CSV 內容。
