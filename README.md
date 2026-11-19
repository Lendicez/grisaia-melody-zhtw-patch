# 灰色的旋律 繁體中文化補丁（grisaia-melody-zhtw-patch）

Steam 版《The Melody of Grisaia》（グリザイアの旋律，`GrisaiaAno3.exe`，**日文版**）的繁體中文化補丁開發庫。

> 狀態：開發中（尚未發行）。

## 玩家安裝（發行後）

1. 在 Steam 將遊戲語言設為**日文**（遊戲內容 → 語言），等更新完成。
2. 關閉遊戲，執行 `GrisaiaMelody-zhTW-Patch-<版號>.exe`。程式會自動在 Steam 遊戲庫找到遊戲資料夾（也可手動選擇），按「安裝」。
3. 原檔備份在遊戲資料夾 `_zhTW_backup\`；可隨時「解除安裝」還原。不修改存檔。
4. Steam「驗證遊戲檔案完整性」或遊戲更新會還原原版，重新執行安裝程式即可。

安裝程式只含**譯文與自製程式**，不含任何遊戲檔；它讀取你電腦上的原版檔案並在本機重組，必須搭配合法持有的 Steam 版。

## 技術路線

| 層 | 做法 |
|---|---|
| 封包 | CatSystem2 KIF（`.int`，Blowfish＋MT 名稱混淆）。`tools/cs2int.py`（Python）與 `installer/Cs2.cs`（C#）可解包、以原金鑰重組 |
| 劇本 | CatScene（`.cst`，zlib）。只替換訊息列（0x20）與名字列（0x21），指令列不動；逐列核對原文 SHA-256 前 16 碼 |
| 編碼 | 引擎以 CP932 位元組處理文字。繁中字若 CP932 可表示就直接用；其餘借用「譯文未用到的第二水準漢字碼」當**隧道碼**，對照表 `zhtw_map.bin` |
| 顯示 | `version.dll` 代理（MinHook）：`MultiByteToWideChar`（CP932／ACP）解碼時把隧道碼換回 Unicode；`GetGlyphOutlineA`／`GetTextExtentPoint32A` 轉為 W 版；`CreateFontIndirectA` 改用繁中字型（預設 Microsoft JhengHei，可在 `zhtw.ini` 調整）。最終顯示一律走 Unicode |
| 名字 | `config.int/nametable.csv` 追加中文名列（語音、名字顏色沿用原設定） |
| 系統字 | `fes.int/_saveload.fes` 章節名等 |
| 安裝 | `installer/`：.NET Framework 4 內建 csc 編譯的單一 EXE；自動偵測 Steam 路徑（登錄檔＋`libraryfolders.vdf`＋`appmanifest_464500.acf`） |

為什麼不是「整個換成 UTF-8」：本作 CatSystem2 為 2016 年 SJIS 版引擎（UTF-8 需移植新版引擎，牽涉 Steam DRM 執行檔），
因此採「檔案內 CP932＋隧道碼、顯示時全程 Unicode」的折衷；譯文原稿本身全部以 UTF-8 JSON 管理。

## 目錄

| 路徑 | 用途 |
|---|---|
| `tools/` | 解包／CST／組裝（`build_patch.py`）、抽字（只在本機 lab 用）、安裝程式編譯與自我測試 |
| `hook/` | `version.dll` 顯示 hook 原始碼（`third_party/minhook`，BSD-2） |
| `installer/` | C# 安裝程式 |
| `translation/` | 繁中譯文（只含 id 與中文）、專有名詞表、翻譯任務規範與驗證腳本 |
| `lab/` | Windows 本機 lab 自動化（經 Steam 啟動、處理視窗化對話框、截圖） |
| `docs/` | 交接與技術紀錄 |

## 原則

- 只上傳原始碼、自製程式與繁中譯文；**不上傳遊戲檔、日文原文全文、截圖或其衍生物**。
- 譯文由 Codex 翻譯與交叉審稿，專有名詞依 `translation/glossary.zh-TW.json`（系列既有中文譯名，附依據）。
- 原遊戲、商標、圖音、程式與資源屬 Frontwing 等各權利人；見 [NOTICE.md](NOTICE.md)。
