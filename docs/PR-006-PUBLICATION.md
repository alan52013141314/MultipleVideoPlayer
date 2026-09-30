# PR-006：MultipleVideoPlayer 原始碼發布

日期：2026-10-01。

使用者指定：GitHub repository 名稱為 `MultipleVideoPlayer`，公開，只包含影片播放器。

## 工作計劃及驗收

1. 從本機播放器來源匯出獨立倉庫，保留 `VideoPlayer` 目錄結構，避免更動建置及測試相對路徑。
2. 只納入播放器原始碼、測試、建置入口、播放器需求文件、GPL／LGPL 及第三方署名；排除剪輯器及原綜合倉庫歷史。
3. 排除影片、preset、虛擬環境、下載套件、執行檔、ZIP 和測試產物；本機原檔保留。
4. 檢查完整來源及授權文字、CMD 的 CRLF checkout 規則、測試及乾淨工作目錄。
5. 建立 `alan52013141314/MultipleVideoPlayer` 公開倉庫，推送獨立初始提交，核對遠端可見性及 commit。

發布內容為原始碼，不建立二進位 Release。公開執行檔前須另確認完整對應原始碼、依賴授權及實際套件的再散布條件。
