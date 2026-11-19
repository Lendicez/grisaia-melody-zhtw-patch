# 交接（2026-11-19 起，Claude 主導）

## 環境
- 本機（lendicez-9800X3D，Win11，系統 ANSI 代碼頁 950）。
- 遊戲：`D:\SteamLibrary\steamapps\common\The Melody of Grisaia`（Steam AppID 464500，**日文版**；exe 有 SteamStub，只能經 Steam 啟動）。
- 開發庫：`C:\GameDev\grisaia-melody-zhtw`（本庫）。lab：`C:\GameDev\grisaia-melody-lab`（解包原文、譯稿工作區、截圖、原版備份 `pristine-ja\`；**不入庫**）。
- 雲端 Claude 經 LD2 的 bridge watcher（`C:\GameDev\LD2\zhTW_lab\ld2-autotest\bridge\queue`）在本機執行 python／git；Codex 以 `tools/codex_job.py` 背景派工。

## 流程
1. 解包：`tools/cs2int.py x <遊戲>\scene.int <lab>\extract-ja\scene --exe <遊戲>\GrisaiaAno3.exe`
2. 抽字：`tools/extract_ja.py <lab>\extract-ja\scene <lab>\tx-ja`（in-NNN.json，含原文，僅 lab）
3. 翻譯：Codex 依 `translation/TASK.md` 產出 out-NNN.json，`translation/validate.py` 把關；審稿產出 fix-*.json。
4. 組裝：`tools/build_patch.py --game <lab>\pristine-ja --tx <lab>\tx-ja --out <lab>\payload-X [--payload payload.json --version V --ini zhtw.ini]`
5. 實機：`lab/lab_run.py --steam --run-id R --steps lab/steps_*.json --payload <lab>\payload-X`（原檔備份到 `_zhTW_backup`；`--restore` 還原）。
   起動時「表示モード」對話框一律按右邊（視窗化）。Steam 必須以一般權限執行，否則自動化無法操作遊戲。
6. 安裝程式：`tools/make_installer.py --payload … --dll hook\build\version.dll --version V --orig <lab>\pristine-ja --out … --expect <lab>\payload-X`

## 已知
- 引擎文字 API 待實測確認（hook 已涵蓋 MultiByteToWideChar／GetGlyphOutlineA／GetTextExtentPoint32A／CreateFontIndirectA）。
- UI 多為 HG3 圖片（sys_*.hg3），待處理。
