# MultipleVideoPlayer

Windows 多格影片播放器，目前版本 **0.6.1 Rust**。主程式與介面已改用 Rust，播放與逐格解碼使用隨包附帶的原生 mpv／FFmpeg，不需要 Python、Qt 或另裝 VLC。

重寫需求、計劃與驗收：[PR-009](VideoPlayer/docs/PR-009-RUST-REWRITE.md)。歷史版本改造自 [GridPlayer（vzhd1701 與貢獻者）](https://github.com/vzhd1701/gridplayer)，原作者署名及 GPL 授權保留；本程式不是上游官方發行。

## 功能

下一項更新的需求與工作計劃：[PR-010：播放與畫面調整](VideoPlayer/docs/PR-010-PLAYBACK-PICTURE-CONTROLS.md)（已實作）。

- 預設六格，最多十二格；二至四欄、跨行跨欄與單格放大查看。
- 單擊畫面切換播放／暫停；全域播放／暫停按鈕；雙擊該格全螢幕，再雙擊還原。
- 各格獨立播放、音量與靜音；音量在播放按鈕旁展開調整。
- 亮度、對比、飽和度、Gamma、色相：全域設定及各格逐項覆寫，隨 preset 保存。
- Fit、Fill、符合寬度、符合高度、Stretch、原始像素 1:1。
- 游標定點滾輪縮放、中鍵平移、倍率與重置；視圖隨 preset 保存。
- 拖入影片或資料夾，遞迴自然排序；前後影片首尾循環。
- 時間軸點擊／持續拖曳、毫秒預覽、AB 標記拖動、直接輸入及區間長度。
- 跳出 AB 暫停循環，回到 A 恢復；左右鍵按自訂秒數控制最後懸停格。
- 暫停精準前後逐格，使用實際解碼影格索引，支援可變幀率。
- 多個 preset、正常關閉保存上一次、重開恢復暫停；相容舊 JSON 格式。
- 懸停覆蓋控制列，無邊框與全螢幕。

## 啟動與建置

本倉庫存放原始碼、建置腳本與文件，不包含影片、個人設定或預先建置的二進位檔。

1. 安裝 Rust MSVC 工具鏈與 Visual Studio C++ Build Tools。
2. 執行 `RustPlayer/build.ps1 -Install`。
3. 雙擊 `VideoPlayer/Start-Player.cmd`；視窗標題顯示版本。

免安裝包產生在 `RustPlayer/dist/MultipleVideoPlayer-0.6.1-win64.zip`。完整解壓後直接執行 **MultipleVideoPlayer.exe**，保留旁邊的 `runtime` 與 `licenses`。

專案入口沿用 `VideoPlayer/dist/GridPlayerWorkspace/portable_data`，不搬移或覆寫既有 preset；獨立解壓包則使用 exe 旁的 `portable_data`。影片只保存路徑。詳見 [Rust 操作與建置說明](RustPlayer/README.md)。

## 驗證與限制

在 `RustPlayer` 執行 `cargo test --locked --bin multiple-video-player`；原生解碼／GPU 畫面整合驗證使用 `verify` 程式，詳見其 README 和 PR-009。

首次逐格會在背景建立影片解碼索引，長影片需要等待；無法保證精準的重複或逆序時間戳會報錯，不改用平均幀率近似。AB 回跳無縫播放仍是先前延期項目。

本次驗證環境為 Windows 11 x64，未於另一台 Windows 10 實機驗證。十二格不代表任意十二條 4K 影片都能流暢播放。

## 署名與授權

GPL-3.0-or-later，見 [LICENSE](LICENSE) 和 [第三方說明](THIRD_PARTY_NOTICES.md)。Rust 的固定依賴版本見 `RustPlayer/Cargo.lock`，原生元件來源與校驗碼見 `RustPlayer/native-components.json`。

`VideoPlayer/src` 及原建置腳本保留作歷史與相容性參考；Rust 版不執行或封裝其中的 Python 程式。
