# Garmin 步數 Dashboard 操作說明

這個專案用來把 York 和 Rita 的 Garmin 步數 CSV 上傳到 GitHub，然後由 GitHub Pages 自動更新網頁 dashboard。

Dashboard 網址：

https://york-dada.github.io/garmin-steps-dashboard/

## 最簡單的日常流程

1. 下載或準備新的 Garmin 步數 CSV。
2. 把 CSV 放到正確的資料夾：
   - York 的資料放到 `data/raw/york/`
   - Rita 的資料放到 `data/raw/rita/`
3. 檔名建議用日期，例如：
   - `data/raw/york/2026-05-24.csv`
   - `data/raw/rita/2026-05-24.csv`
4. 雙擊執行：
   - `GarminUploadToGitHub.exe`
5. 等黑色視窗跑完。
6. 看到 `完成，上傳到 origin/main 了。` 就代表已經上傳到 GitHub。
7. 如果看到 `沒有偵測到新的 CSV 或 dashboard 相關變更。`，代表沒有偵測到新資料，所以不會上傳。
8. 看完訊息後，按 Enter 關閉視窗。
9. 如果有上傳，等 GitHub 自動更新網頁，通常約 1 到 3 分鐘。
10. 到這裡看結果：
   - https://york-dada.github.io/garmin-steps-dashboard/

## CSV 放置規則

每個人的資料要放在自己的資料夾下面：

```text
data/raw/
  york/
    2026-05-24.csv
  rita/
    2026-05-24.csv
```

資料夾名稱會變成 dashboard 上顯示的人名。例如 `data/raw/york/` 會顯示成 York。

CSV 內容至少要有日期、實際步數、目標步數。現在常用格式如下：

```csv
,實際,目標
05/24/2026,1462,3410
```

也可以一個 CSV 裡放多天資料：

```csv
,實際,目標
05/18/2026,5979,2670
05/19/2026,3078,2670
05/20/2026,6896,2710
```

## 上傳工具

日常最常用的檔案。

更新完 CSV 後，雙擊最上層的這個檔案就好：

```text
GarminUploadToGitHub.exe
```

它會自動做這些事：

1. 重新產生 dashboard 需要的資料。
2. 檢查哪些 CSV 或相關檔案有更新。
3. 建立 Git commit。
4. 上傳到 GitHub。
5. 觸發 GitHub Pages 更新網站。

如果沒有任何 CSV 或相關檔案更新，它會顯示沒有變更，並且不會上傳。

## 怎麼知道上傳成功

雙擊 `GarminUploadToGitHub.exe` 後，黑色視窗最後如果看到類似這段：

```text
完成，上傳到 origin/main 了。
GitHub 會自動更新 dashboard，通常約 1 到 3 分鐘。
查看結果: https://york-dada.github.io/garmin-steps-dashboard/
看完訊息後，按 Enter 關閉視窗...
```

代表 CSV 已經成功上傳到 GitHub。

接著等 1 到 3 分鐘，再打開 dashboard：

https://york-dada.github.io/garmin-steps-dashboard/

如果網頁還沒變，通常是 GitHub Pages 還在更新，可以稍等一下再重新整理。

## 如果看到錯誤

如果黑色視窗最後出現 `上傳失敗`，代表沒有成功上傳。

常見原因：

- 網路沒有連線。
- GitHub 登入狀態失效。
- CSV 還開在 Excel 裡，檔案沒有正確存好。
- CSV 格式不對，程式讀不到日期或步數。

可以先確認：

1. CSV 已經存檔。
2. CSV 放在正確資料夾。
3. 檔案沒有被 Excel 鎖住。
4. 網路正常。

確認後再重新雙擊 `GarminUploadToGitHub.exe`。

## 開發者用指令

如果不想用 exe，也可以手動執行：

```powershell
python build_dashboard.py
```

這會在本機產生：

```text
data/processed/steps.json
site/index.html
```

但一般使用者不需要手動執行這個。日常更新請直接用：

```text
GarminUploadToGitHub.exe
```

## 自動更新原理

這個專案的 GitHub Actions 會在資料上傳到 `main` 分支後自動執行。

它會：

1. 讀取 `data/raw/**` 裡的 CSV。
2. 執行 `build_dashboard.py`。
3. 產生最新 dashboard。
4. 發布到 GitHub Pages。

所以本機只需要負責把 CSV 上傳到 GitHub，網頁更新由 GitHub 自動處理。
