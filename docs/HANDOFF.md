# 交接（2026-11-19 起，Claude 主導）

## 目前狀態（2026-11-20）

| 項目 | 狀態 |
|---|---|
| 解包／組裝工具 | 完成（KIF、CST、FES、HG-3 皆可往返） |
| 劇本翻譯 | **完成**：1,350 則（`translation/zh/out-000..011.json`），交叉審稿完成（`fix-*.json`） |
| exe 字串表 | **完成**：`language.txt` 903 條（`translation/lang/lang-out-*.json`），以 CP932＋借位碼寫出 |
| 顯示 hook | 完成並實機確認：對話（微軟正黑體）、名字欄、換行、刪節號／破折號（細明體）、借位字、對話框標題與按鈕 |
| UI 圖片 | **完成**：標題選單、設定各頁、存讀檔、CG／BGM／影片／場景鑑賞說明、對話設定、進度、跳轉中、場景標題、開機注意畫面（caution1/2） |
| 安裝程式 | **RC2**：`<lab>\release-rc2\GrisaiaMelody-zhTW-Patch-0.9.1.exe`（含存檔路徑修正）；自我測試通過。RC1（0.9.0）擁有者已實機確認安裝／解除安裝 |
| GitHub | `Lendicez/grisaia-melody-zhtw-patch`（私人） |

實機確認（payload-r8，2026-11-19）：開機注意畫面、標題選單、設定 Text／Dialog 頁、CG 鑑賞說明、結束確認對話框皆為繁中且無破圖。

## 結束時卡住（已解決，2026-11-20）
- 原因：存檔資料夾是 `%APPDATA%\フロントウイング\グリザイアの迷宮 ～グリザイアの旋律～`，引擎以 Shift-JIS 位元組呼叫
  `CreateDirectoryA`／`CreateFileA`；在非日文系統（CP950）會被當成系統代碼頁解讀而失敗，結束時寫系統存檔失敗並跳出
  「セーブデータの作成に失敗しました」訊息框，看起來像卡住。原版在中文系統同樣如此（等於中文系統原本完全無法存檔）。
- 修正：`hook/zhtw_fs.c` 把含高位元組的路徑轉成 Unicode 改呼叫 W 版 API（系統前綴照系統代碼頁、其餘照 CP932），
  路徑與日文系統／Locale Emulator／Steam Cloud 的資料夾名稱一致。`zhtw.ini` 的 `[fs] enable=0` 可關閉。
- 診斷工具：`hook/zhtw_diag.c`（`[diag] exit=1`）記錄結束流程並在結束後傾印各執行緒堆疊；`[diag] fast_exit=1` 可在 ExitProcess 時直接結束程序（目前不需要）。
- 驗證：diag-hang2（除錯版）與 rc2-exit（正式設定）按「是」後 4 秒內程序正常結束；存檔資料夾已寫入 savegen.dat、setup.xml。

## 已知問題
- 自動測試時，選單的點擊偶爾只變成滑鼠停留（未進入頁面）；手動操作無此問題，System／Sound／Shortcut 頁以離線比對圖確認。

## 下一步
1. 擁有者以 RC2 安裝（會覆蓋 RC1），確認：按結束遊戲能正常關閉、遊戲內存檔／讀檔正常（bridge 不允許執行白名單外的 exe，需手動）。
2. 擁有者實機通玩抽查（長訊息、backlog、存讀檔註記）後發行。
3. RC1 的 payload 由 `build_patch.py … --lang <lab>\tx-lang --ui <lab>\ui\out --payload <lab>\reports\payload-rc1.json --version 0.9.0 --ini <lab>\reports\zhtw-release.ini` 產生（release ini 關閉 log）。
4. `lab_run.py --payload` 結束後**不會**自動還原；測完用 `lab/restore_steam.py` 還原（會與 `pristine-ja` 比對）。

## 環境
- 本機（lendicez-9800X3D，Win11，系統 ANSI 代碼頁 950）。
- 遊戲：`D:\SteamLibrary\steamapps\common\The Melody of Grisaia`（Steam AppID 464500，**日文版**；exe 有 SteamStub，只能經 Steam 啟動）。
- 開發庫：`C:\GameDev\grisaia-melody-zhtw`（本庫）。lab：`C:\GameDev\grisaia-melody-lab`（解包原文、譯稿工作區、截圖、原版備份 `pristine-ja\`；**不入庫**）。
- 雲端 Claude 經 LD2 的 bridge watcher（`C:\GameDev\LD2\zhTW_lab\ld2-autotest\bridge\queue`）在本機執行 python／git；Codex 以 `tools/codex_job.py` 背景派工。
- UI 工具需要 Pillow、numpy、opencv（`opencv-contrib-python-headless` 亦可）。

## 流程
1. 解包：`tools/cs2int.py x <遊戲>\scene.int <lab>\extract-ja\scene --exe <遊戲>\GrisaiaAno3.exe`
2. 抽字：`tools/extract_ja.py <lab>\extract-ja\scene <lab>\tx-ja`（in-NNN.json，含原文，僅 lab）
3. 翻譯：Codex 依 `translation/TASK.md` 產出 out-NNN.json；審稿依 `REVIEW_TASK.md` 產出 fix-NNN.json；`translation/validate.py` 把關。exe 字串依 `translation/TASK_LANG.md`。
4. UI 圖片（在 `<lab>\ui`，`src\` 為 `hg3.py dec` 解出的 frame）：
   1. `tools/ui_redraw.py ui/specs/spec-sys_*.json src ../fonts out`（一般按鈕／標籤：取樣底色重畫，字高對齊原日文墨跡，必要時撐高圖框並寫 sidecar 座標）
   2. `tools/ui_title.py src ../fonts out`（標題選單與副標）
   3. `tools/ui_help.py ui/specs/spec-help.json …`、`spec-labels.json`（由 `gen_labels.py` 自動偵測產生）、`spec-scenetitle.json`（壓在紋理上的說明字／設定頁標籤：遮罩＋同底圖互補＋inpaint，再畫中文）
   4. `tools/ui_caution.py ui/specs/spec-caution.json …`（開機注意畫面：逐行修補＋整塊柔焦略暗，再畫白字黑框紅重點）
   全部輸出到同一個 `out\`，`build_patch.py --ui out` 會只替換有改的 frame。
5. 組裝：`tools/build_patch.py --game <lab>\pristine-ja --tx <lab>\tx-ja --out <lab>\payload-X --lang <lab>\tx-lang --ui <lab>\ui\out [--payload payload.json --version V --ini zhtw.ini]`
6. 實機：`lab/lab_run.py --steam --run-id R --steps lab/steps_*.json --payload <lab>\payload-X`（原檔備份到 `_zhTW_backup`，結束後還原）。
   起動時「表示モード」對話框一律按右邊（視窗化）。步驟支援 wait／shot／screen／click／rclick／move／key／close。
7. 安裝程式：`tools/make_installer.py --payload … --dll hook\build\version.dll --version V --orig <lab>\pristine-ja --out … --expect <lab>\payload-X`

## 譯名依據
系列既有：灰色的果實／迷宮／樂園／旋律、風見雄二、日下部麻子、JB（春寺由梨亞）、CIRS。
本作新角色（系列無官方繁中）：瑪麗安‧加蘭德、伊莎貝拉‧菲茨傑拉德（依中文圈通行譯名轉繁體）；
Noboa＝諾波亞（中央社慣用）。詳見 `translation/glossary.zh-TW.json`。
