# 交接（2026-11-19 起，Claude 主導）

## 目前狀態（2026-11-19 14:50 暫停點）

| 項目 | 狀態 |
|---|---|
| 解包／組裝工具 | 完成（KIF、CST、FES、HG-3 皆可往返；HG-3 `tools/hg3.py` 20 frame 往返位元一致） |
| 劇本初譯 | **完成**：1,350 則（`translation/zh/out-000..011.json`，Codex，全數通過 validate） |
| 交叉審稿 | **進行到一半**：fix-001,003..008 共 13 處；Codex 額度用完於 004:1446 附近中斷（`REVIEW_TASK.md`） |
| 顯示 hook | 已編譯、可載入（log 確認 hook 安裝成功、ACP=950）；**尚未實機確認對話文字顯示** |
| 安裝程式 | C# 單一 EXE 完成，自我測試通過（status→install→與 Python 建置逐檔比對一致→uninstall 還原） |
| UI 圖片 | 未開始改圖；`sys_*.hg3` 56 檔已解出到 lab |
| GitHub | `Lendicez/grisaia-melody-zhtw-patch`（私人） |

## 卡點
1. **Steam 以系統管理員權限執行**（steam.exe 為高權限），它啟動的遊戲是高權限程序：bridge watcher（一般權限）無法點擊、截圖或結束遊戲。
   需擁有者以一般權限重開 Steam，或以系統管理員身分重開 watcher。
2. 遊戲在「表示モード」對話框／關閉時會卡住（擁有者回報）；需確認是否與 `version.dll` hook 有關：
   先在**未安裝** hook 的原版確認是否也會卡，再比較。
3. 2026-11-19 暫停時 Steam 資料夾可能仍是測試狀態（payload-r1：scene/config/fes.int 已換、加了 version.dll 等）。
   遊戲程序結束後執行 `C:\GameDev\grisaia-melody-lab\tools\restore_steam.py` 還原（原檔另有 `lab\pristine-ja\`）。

## 下一步
1. 還原 Steam 資料夾 → 排除權限問題 → `lab/lab_run.py --steam` 以 payload-r1 實機進入劇情，看 `zhtw_hook.log` 確認引擎走哪個文字 API，截圖確認字型、換行、名字欄。
2. Codex 額度恢復後續跑審稿（004:1446 起，含 fix-009..011），套用 fix 後重建。
3. UI 圖片：列出含文字的 sys_*.hg3 frame → 重繪繁中（Codex 繪圖或腳本以 GDI 字型重畫）→ `hg3.py enc` → 打包 image.int 差分。
4. 發行：`tools/make_installer.py` 產生 EXE＋自我測試，擁有者實機確認後才公開。

## 環境
- 本機（lendicez-9800X3D，Win11，系統 ANSI 代碼頁 950）。
- 遊戲：`D:\SteamLibrary\steamapps\common\The Melody of Grisaia`（Steam AppID 464500，**日文版**；exe 有 SteamStub，只能經 Steam 啟動，直接執行 lab 副本會被 Steam 轉去啟動安裝版）。
- 開發庫：`C:\GameDev\grisaia-melody-zhtw`（本庫）。lab：`C:\GameDev\grisaia-melody-lab`（解包原文、譯稿工作區、截圖、原版備份 `pristine-ja\`；**不入庫**）。
- 雲端 Claude 經 LD2 的 bridge watcher（`C:\GameDev\LD2\zhTW_lab\ld2-autotest\bridge\queue`）在本機執行 python／git；Codex 以 `tools/codex_job.py` 背景派工（gpt-6-astra／max）。

## 流程
1. 解包：`tools/cs2int.py x <遊戲>\scene.int <lab>\extract-ja\scene --exe <遊戲>\GrisaiaAno3.exe`
2. 抽字：`tools/extract_ja.py <lab>\extract-ja\scene <lab>\tx-ja`（in-NNN.json，含原文，僅 lab）
3. 翻譯：Codex 依 `translation/TASK.md` 產出 out-NNN.json；審稿依 `REVIEW_TASK.md` 產出 fix-NNN.json；`translation/validate.py` 把關。
4. 組裝：`tools/build_patch.py --game <lab>\pristine-ja --tx <lab>\tx-ja --out <lab>\payload-X [--payload payload.json --version V --ini zhtw.ini]`
5. 實機：`lab/lab_run.py --steam --run-id R --steps lab/steps_*.json --payload <lab>\payload-X`（原檔備份到 `_zhTW_backup`）。
   起動時「表示モード」對話框一律按右邊（視窗化）。
6. 安裝程式：`tools/make_installer.py --payload … --dll hook\build\version.dll --version V --orig <lab>\pristine-ja --out … --expect <lab>\payload-X`

## 譯名依據
系列既有：灰色的果實／迷宮／樂園／旋律、風見雄二、日下部麻子、JB（春寺由梨亞）、CIRS。
本作新角色（系列無官方繁中）：瑪麗安・加蘭德、伊莎貝拉・菲茨傑拉德（依中文圈通行譯名轉繁體）；
Noboa＝諾波亞（中央社慣用）。詳見 `translation/glossary.zh-TW.json`。
