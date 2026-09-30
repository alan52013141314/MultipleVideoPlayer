# MultipleVideoPlayer

Windows 多格影片播放器，改造自 [vzhd1701 與貢獻者的 GridPlayer](https://github.com/vzhd1701/gridplayer)。目前版本：**0.5.5-local2**。這是獨立修改版，並非 GridPlayer 官方發行。

## 功能

- 預設六格，最多十二格；支援橫跨、縱跨與 2×2 格子。
- 各格獨立播放、暫停、音量與靜音；播放按鈕旁的小型音量按鈕可展開調節。
- 時間軸直接點擊跳轉或拖曳；支援 A／B 區間循環。
- 六種畫面模式：Fit、Fill、符合寬度、符合高度、Stretch、原始像素 1:1。
- 拖入影片或資料夾；資料夾遞迴找出影片並自然排序，上一條／下一條首尾循環。
- 多個 preset；正常關閉保存「上一次」，重開自動恢復並暫停。
- 滑鼠移入格子時顯示覆蓋式控制列；無邊框與全螢幕可分別控制。

## 建置與啟動

本倉庫提供原始碼、建置／測試腳本及文件，沒有預先建置的 exe、影片或個人設定。

1. 安裝 Python 3.12，按 [播放器重建說明](VideoPlayer/README.md#重建)建立環境、安裝依賴並準備官方 libVLC。
2. 在 `VideoPlayer` 執行 `build.ps1`。
3. 雙擊 `VideoPlayer/Start-Player.cmd`。標題會顯示版本；舊視窗仍開啟時先正常關閉再啟動。

專案入口使用 `VideoPlayer/dist/GridPlayerWorkspace/portable_data` 保存設定；更新程式不搬移或覆蓋 preset。影片只保存路徑。詳見 [操作說明](VideoPlayer/README.md)。

## 測試與已知限制

在 `VideoPlayer` 執行：

```powershell
.\.venv\Scripts\python -m pytest src/tests/test_workspace.py src/tests/test_display_modes.py src/tests/test_click_slider.py -q
```

上述資料及元件測試共 13 項。VLC 整合腳本位於 `VideoPlayer/src/scripts`，需要本機 libVLC 和自行準備的測試影片；它們引用的 `verification` 產物不包含在 Git 中。已建置後可執行 `launcher_verify.py`、`release_verify.py` 檢查入口及套件。

AB 循環回到開頭的短暫停頓尚未修正。原生影片畫面的完整目視驗收尚未完成；十二格也不保證任意十二條 4K 影片均流暢。過往本機驗證記錄見播放器 `docs` 中各份需求文件。

## Credit 與授權

基於 GridPlayer v0.5.5，commit `da2a649fcbcb8f1ab945353f090befca53f8725f`；原作者、來源及授權文件保留在 `VideoPlayer/src`。本案修改日期為 2026-09-30，原始碼發布整理日期為 2026-10-01。

播放器衍生程式及本案整合程式採 **GPL-3.0-or-later**。第三方字型、圖示、Python VLC bindings 與依賴保留各自授權。完整資料見 [LICENSE](LICENSE)、[第三方署名](THIRD_PARTY_NOTICES.md)及 [發布範圍](docs/PR-006-PUBLICATION.md)。
