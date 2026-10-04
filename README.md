# MultipleVideoPlayer

Windows 多格影片播放器，改造自 [vzhd1701 與貢獻者的 GridPlayer](https://github.com/vzhd1701/gridplayer)。目前版本：**0.5.5-local4**。這是獨立修改版，並非 GridPlayer 官方發行。

## 功能

本次更新：[PR-008：精簡控制列、AB 編輯、縮放及精準逐格](VideoPlayer/docs/PR-008-COMPACT-MARKERS-ZOOM.md)。

- 精簡單行時間資訊、可拖動的 AB 標記及直接輸入區間。
- 游標定點滾輪縮放、倍率顯示與重置；縮放及平移隨 preset 保存。
- 暫停時真正解碼相鄰影格，可前進／後退；支援單格放大查看及返回網格。

- 預設六格，最多十二格；支援橫跨、縱跨與 2×2 格子。
- 各格獨立播放、暫停、音量與靜音；播放按鈕旁的小型音量按鈕可展開調節。
- 時間軸直接點擊跳轉或拖曳；支援 A／B 區間循環。
- ←／→ 依自訂秒數控制最後懸停格；時間軸預覽毫秒時間。跳出 AB 暫停循環並保留標記，可按「回到循環」。
- 中鍵拖曳平移被裁切的影片，切換影片／畫面模式時置中。
- 六種畫面模式：Fit、Fill、符合寬度、符合高度、Stretch、原始像素 1:1。
- 拖入影片或資料夾；資料夾遞迴找出影片並自然排序，上一條／下一條首尾循環。
- 多個 preset；正常關閉保存「上一次」，重開自動恢復並暫停。
- 滑鼠移入格子時顯示覆蓋式控制列；無邊框與全螢幕可分別控制。

## 建置與啟動

本倉庫提供原始碼、建置／測試腳本及文件，沒有預先建置的 exe、影片或個人設定。

建置產生 Windows 10／11 x64 免安裝 ZIP；完整解壓後直接開 `GridPlayerWorkspace.exe`，不需要另裝 Python 或 VLC，需保留元件資料夾。最新需求與驗證見 [PR-007](VideoPlayer/docs/PR-007-SEEK-PAN-PORTABLE.md)。

1. 安裝 Python 3.12，按 [播放器重建說明](VideoPlayer/README.md#重建)建立環境、安裝依賴並準備官方 libVLC。
2. 在 `VideoPlayer` 執行 `build.ps1`。
3. 雙擊 `VideoPlayer/Start-Player.cmd`。標題會顯示版本；舊視窗仍開啟時先正常關閉再啟動。

專案入口使用 `VideoPlayer/dist/GridPlayerWorkspace/portable_data` 保存設定；更新程式不搬移或覆蓋 preset。影片只保存路徑。詳見 [操作說明](VideoPlayer/README.md)。

## 測試與已知限制

在 `VideoPlayer` 執行：

```powershell
.\.venv\Scripts\python -m pytest src/tests/test_workspace.py src/tests/test_display_modes.py src/tests/test_click_slider.py src/tests/test_workspace_interaction.py src/tests/test_frame_step.py -q
```

上述資料及元件測試共 28 項。VLC 整合腳本位於 `VideoPlayer/src/scripts`，需要本機 libVLC 和自行準備的測試影片；它們引用的 `verification` 產物不包含在 Git 中。`interaction_verify.py` 可驗證本次操作，加入 `--software` 驗證軟體解碼；已建置後可執行 `launcher_verify.py`、`release_verify.py` 檢查入口及套件。

AB 循環回到開頭的短暫停頓尚未修正。此次已在 Windows 11 驗證打包版原生影片畫面與主要控制，尚未用獨立 Windows 10 電腦驗證；十二格也不保證任意十二條 4K 影片均流暢。詳細驗證範圍見播放器 `docs` 中各份需求文件。

## Credit 與授權

基於 GridPlayer v0.5.5，commit `da2a649fcbcb8f1ab945353f090befca53f8725f`；原作者、來源及授權文件保留在 `VideoPlayer/src`。本次修改日期為 2026-10-04。

播放器衍生程式及本案整合程式採 **GPL-3.0-or-later**。第三方字型、圖示、Python VLC bindings 與依賴保留各自授權。完整資料見 [LICENSE](LICENSE)、[第三方署名](THIRD_PARTY_NOTICES.md)及 [發布範圍](docs/PR-006-PUBLICATION.md)。
