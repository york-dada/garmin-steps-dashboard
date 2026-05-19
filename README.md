# 豬豬步數記分板

用 Garmin Connect 手動匯出的 CSV 產生多人步數排行榜，並透過 GitHub Pages 發布成手機可看的靜態頁面。

## 使用流程

1. 到 Garmin Connect 手動下載步數 CSV。
2. 將 CSV 上傳到對應成員資料夾：
   - `data/raw/york/`
   - `data/raw/rita/`
3. GitHub Actions 會執行 `build_dashboard.py`。
4. 程式會輸出：
   - `data/processed/steps.json`
   - `site/index.html`
5. GitHub Pages 會發布 `site/` 內容。

## CSV 命名規範

CSV 檔案必須放在 `data/raw/<member>/` 底下，檔名請使用 ISO 日期：

```text
data/raw/york/YYYY-MM-DD.csv
data/raw/rita/YYYY-MM-DD.csv
```

範例：

```text
data/raw/york/2026-05-19.csv
data/raw/rita/2026-05-19.csv
```

規則：

- `<member>` 來自資料夾名稱，例如 `data/raw/york/...` 會顯示為 `York`。
- `YYYY-MM-DD.csv` 代表這份 CSV 的匯出或更新日期。
- 如果同一位成員、同一天步數出現在多個 CSV，會只保留一筆。
- 覆蓋優先序是「檔案修改時間較新者」勝出。
- 如果檔案修改時間完全相同，則用檔名較後者勝出，例如 `2026-05-19.csv` 會覆蓋 `2026-05-17.csv` 裡同一天的資料。
- 建議每次重新匯出 Garmin 資料時，用當天日期建立新 CSV，不要覆蓋舊檔。這樣本機和 GitHub 上都比較容易追蹤資料來源。

## 支援的 CSV 格式

一般直式 CSV：

```csv
日期,步數,目標
2026-05-19,8200,5000
```

也支援 Garmin 匯出常見的第一欄空白格式：

```csv
,實際,目標
05/19/2026,8200,5000
```

## 本機產生 dashboard

```powershell
python build_dashboard.py
```

產生後可打開：

```text
site/index.html
```

## 自動部署

`.github/workflows/build-and-deploy.yml` 會在以下情況自動建置並部署：

- `data/raw/**` 有新的 CSV
- `build_dashboard.py` 有修改
- `site/assets/**` 有修改
- 每天 00:00 UTC 固定跑一次
- 手動執行 GitHub Actions 的 `workflow_dispatch`

公開頁面只顯示彙整後的 dashboard，不會直接列出原始 CSV 內容。
