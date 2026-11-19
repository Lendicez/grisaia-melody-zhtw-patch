// 《灰色的旋律》（The Melody of Grisaia / グリザイアの旋律，Steam 日文版）繁體中文化補丁安裝程式。
// 以 Windows 內建 .NET Framework 4 csc.exe 編譯；payload.json（譯文位元組與檔案）與 version.dll（顯示 hook）為內嵌資源。
// 安裝：自動在 Steam 遊戲庫尋找遊戲 → 核對原版雜湊 → 原檔備份到 <遊戲>\_zhTW_backup\ → 由使用者自己的原檔重組 scene.int／config.int／fes.int
//       並加入 version.dll、zhtw_map.bin、zhtw.ini。解除安裝：還原備份、移除新增檔案。不碰存檔。
// 命令列：/status <dir>、/install <dir>、/uninstall <dir>（自動測試用）；/dir=<dir> 指定 GUI 預設資料夾。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("灰色的旋律 繁體中文化補丁")]
[assembly: AssemblyProduct("grisaia-melody-zhtw-patch")]
[assembly: AssemblyVersion(GrisaiaZhTW.Ver.Assembly)]

namespace GrisaiaZhTW
{
    static partial class Ver { }

    class Payload
    {
        public string Version; public uint Key; public HashSet<string> ExeSha = new HashSet<string>();
        public Dictionary<string, object> Archives; public Dictionary<string, byte[]> Files = new Dictionary<string, byte[]>();
        public static Payload Load()
        {
            var asm = Assembly.GetExecutingAssembly();
            Func<string, byte[]> res = n => { using (var s = asm.GetManifestResourceStream(n)) { var m = new MemoryStream(); s.CopyTo(m); return m.ToArray(); } };
            var j = (Dictionary<string, object>)new MiniJson(Encoding.UTF8.GetString(res("payload.json"))).Parse();
            var p = new Payload { Version = (string)j["version"], Key = (uint)(long)j["key"], Archives = (Dictionary<string, object>)j["archives"] };
            foreach (var s in (List<object>)j["exe_sha256"]) p.ExeSha.Add((string)s);
            foreach (var kv in (Dictionary<string, object>)j["files"]) p.Files[kv.Key] = Convert.FromBase64String((string)kv.Value);
            p.Files["version.dll"] = res("version.dll");
            return p;
        }
        public string OrigSha(string arc) { return (string)((Dictionary<string, object>)Archives[arc])["orig_sha256"]; }
    }

    enum St { NotFound, Original, Installed, Outdated, Unknown }

    class Engine
    {
        public const string Exe = "GrisaiaAno3.exe", Bk = "_zhTW_backup";
        readonly Payload P; public readonly string Dir; readonly Action<string> Log;
        public Engine(Payload p, string dir, Action<string> log) { P = p; Dir = dir; Log = log ?? (Action<string>)(s => { }); }
        string F(string n) { return Path.Combine(Dir, n); }
        string B(string n) { return Path.Combine(Dir, Bk, n); }
        public static string Sha(byte[] b) { using (var h = SHA256.Create()) return BitConverter.ToString(h.ComputeHash(b)).Replace("-", "").ToLowerInvariant(); }
        static string ShaFile(string p) { return File.Exists(p) ? Sha(File.ReadAllBytes(p)) : null; }

        Dictionary<string, object> Record()
        {
            string r = B("installed.json");
            return File.Exists(r) ? (Dictionary<string, object>)new MiniJson(File.ReadAllText(r, Encoding.UTF8)).Parse() : null;
        }

        public St State(out string detail)
        {
            detail = "";
            if (!File.Exists(F(Exe))) { detail = "找不到 " + Exe; return St.NotFound; }
            if (!P.ExeSha.Contains(ShaFile(F(Exe)))) { detail = Exe + " 不是支援的版本（需 Steam 日文版；若遊戲剛更新或為英文版，請先切換為日文）"; return St.Unknown; }
            var rec = Record();
            int orig = 0, inst = 0, other = 0;
            foreach (var arc in P.Archives.Keys)
            {
                string cur = ShaFile(F(arc));
                if (cur == P.OrigSha(arc)) orig++;
                else if (rec != null && rec.ContainsKey(arc) && (string)rec[arc] == cur) inst++;
                else { other++; detail += arc + " 與原版不同；"; }
            }
            if (other > 0) return St.Unknown;
            if (inst == P.Archives.Count) return rec.ContainsKey("version") && (string)rec["version"] == P.Version ? St.Installed : St.Outdated;
            if (orig == P.Archives.Count) return St.Original;
            detail = "部分檔案已修改、部分為原版"; return St.Unknown;
        }

        public static bool IgnoreRunning;   // 僅供自動測試（/ignore-running）
        static bool Running() { return !IgnoreRunning && Process.GetProcessesByName("GrisaiaAno3").Length > 0; }

        public void Install()
        {
            if (Running()) throw new Exception("遊戲正在執行，請先關閉遊戲。");
            string d; var st = State(out d);
            if (st == St.NotFound || st == St.Unknown) throw new Exception("無法安裝：" + d);
            string vdll = F("version.dll");
            if (File.Exists(vdll) && !File.Exists(B("installed.json")))
                throw new Exception("遊戲資料夾已有其他程式的 version.dll（可能是其他模組），為避免衝突不進行安裝。");
            Directory.CreateDirectory(Path.Combine(Dir, Bk));
            File.WriteAllText(Path.Combine(Dir, Bk, "說明.txt"),
                "《灰色的旋律》繁體中文化補丁的原檔備份，解除安裝時使用。請勿刪除；也可用 Steam「驗證遊戲檔案完整性」還原原版。\r\n", Encoding.UTF8);
            var rec = new Dictionary<string, string>();
            foreach (var arc in P.Archives.Keys)
            {
                string cur = F(arc), bk = B(arc);
                byte[] src;
                if (ShaFile(cur) == P.OrigSha(arc)) { src = File.ReadAllBytes(cur); if (ShaFile(bk) != P.OrigSha(arc)) File.Copy(cur, bk, true); }
                else if (ShaFile(bk) == P.OrigSha(arc)) src = File.ReadAllBytes(bk);   // 更新：由備份重建
                else throw new Exception("找不到 " + arc + " 的原版（請用 Steam「驗證遊戲檔案完整性」還原後再安裝）");
                Log("處理 " + arc + " …");
                byte[] outb = Patch(arc, src);
                WriteAtomic(cur, outb); rec[arc] = Sha(outb);
            }
            foreach (var kv in P.Files) { WriteAtomic(F(kv.Key), kv.Value); Log("寫入 " + kv.Key); }
            var sb = new StringBuilder("{\"version\":\"" + P.Version + "\"");
            foreach (var kv in rec) sb.Append(",\"" + kv.Key + "\":\"" + kv.Value + "\"");
            sb.Append(",\"added\":[" + string.Join(",", P.Files.Keys.Select(k => "\"" + k + "\"")) + "]}");
            File.WriteAllText(B("installed.json"), sb.ToString(), Encoding.UTF8);
            Log("安裝完成（版本 " + P.Version + "）。");
        }

        public void Uninstall()
        {
            if (Running()) throw new Exception("遊戲正在執行，請先關閉遊戲。");
            var rec = Record();
            if (rec == null) throw new Exception("沒有安裝紀錄（_zhTW_backup\\installed.json）。");
            foreach (var arc in P.Archives.Keys)
                if (ShaFile(B(arc)) == P.OrigSha(arc)) { File.Copy(B(arc), F(arc), true); Log("還原 " + arc); }
            foreach (var o in (List<object>)rec["added"]) { string n = (string)o; if (File.Exists(F(n))) { File.Delete(F(n)); Log("移除 " + n); } }
            foreach (var n in new[] { "zhtw_hook.log" }) if (File.Exists(F(n))) File.Delete(F(n));
            File.Delete(B("installed.json"));
            Log("已解除安裝，恢復原版。");
        }

        static void WriteAtomic(string path, byte[] data)
        {
            string tmp = path + ".zhtw-tmp"; File.WriteAllBytes(tmp, data);
            if (File.Exists(path)) File.Delete(path);
            File.Move(tmp, path);
        }

        byte[] Patch(string arc, byte[] src)
        {
            var kif = new Kif(src, P.Key);
            var ents = (Dictionary<string, object>)((Dictionary<string, object>)P.Archives[arc])["entries"];
            foreach (var kv in ents)
            {
                var e = kif.Find(kv.Key);
                if (e == null) throw new Exception(arc + " 內找不到 " + kv.Key);
                var spec = (Dictionary<string, object>)kv.Value;
                var data = kif.Read(e);
                string type = (string)spec["type"];
                if (type == "cst")
                {
                    var cst = new Cst(data);
                    foreach (var lv in (Dictionary<string, object>)spec["lines"])
                    {
                        int idx = int.Parse(lv.Key); var pair = (List<object>)lv.Value;
                        if (idx >= cst.Lines.Count || Sha(cst.Lines[idx]).Substring(0, 16) != (string)pair[0])
                            throw new Exception(kv.Key + " 第 " + idx + " 列與預期原文不符（遊戲版本不同？）");
                        cst.Lines[idx] = Convert.FromBase64String((string)pair[1]);
                    }
                    e.NewData = cst.Build();
                }
                else if (type == "append")
                {
                    var add = Convert.FromBase64String((string)spec["data"]);
                    var nd = new byte[data.Length + add.Length]; Buffer.BlockCopy(data, 0, nd, 0, data.Length); Buffer.BlockCopy(add, 0, nd, data.Length, add.Length);
                    e.NewData = nd;
                }
                else if (type == "fes")
                {
                    var text = Fes.Text(data);
                    foreach (var o in (List<object>)spec["replace"])
                    {
                        var pr = (List<object>)o; var a = Convert.FromBase64String((string)pr[0]); var b = Convert.FromBase64String((string)pr[1]);
                        int at = IndexOf(text, a); if (at < 0) throw new Exception(kv.Key + " 找不到要替換的字串");
                        var nt = new byte[text.Length - a.Length + b.Length];
                        Buffer.BlockCopy(text, 0, nt, 0, at); Buffer.BlockCopy(b, 0, nt, at, b.Length);
                        Buffer.BlockCopy(text, at + a.Length, nt, at + b.Length, text.Length - at - a.Length);
                        text = nt;
                    }
                    e.NewData = Fes.Pack(data, text);
                }
                else throw new Exception("未知的修補類型 " + type);
            }
            return kif.Build();
        }
        static int IndexOf(byte[] h, byte[] n)
        {
            for (int i = 0; i + n.Length <= h.Length; i++) { int k = 0; while (k < n.Length && h[i + k] == n[k]) k++; if (k == n.Length) return i; }
            return -1;
        }
    }

    static class Steam
    {
        public static List<string> Candidates()
        {
            var roots = new List<string>();
            foreach (var hive in new[] { Registry.CurrentUser, Registry.LocalMachine })
                foreach (var key in new[] { @"Software\Valve\Steam", @"Software\WOW6432Node\Valve\Steam" })
                    try
                    {
                        using (var k = hive.OpenSubKey(key))
                        {
                            if (k == null) continue;
                            foreach (var n in new[] { "SteamPath", "InstallPath" })
                            { var v = k.GetValue(n) as string; if (!string.IsNullOrEmpty(v)) roots.Add(v.Replace('/', '\\')); }
                        }
                    }
                    catch { }
            var libs = new List<string>();
            foreach (var r in roots.Distinct(StringComparer.OrdinalIgnoreCase))
            {
                libs.Add(r);
                try
                {
                    string vdf = Path.Combine(r, @"steamapps\libraryfolders.vdf");
                    if (File.Exists(vdf))
                        foreach (var line in File.ReadAllLines(vdf))
                        {
                            var t = line.Trim();
                            if (!t.StartsWith("\"path\"", StringComparison.OrdinalIgnoreCase)) continue;
                            var parts = t.Split('"');
                            if (parts.Length >= 4) libs.Add(parts[3].Replace(@"\\", @"\"));
                        }
                }
                catch { }
            }
            var res = new List<string>();
            foreach (var l in libs.Distinct(StringComparer.OrdinalIgnoreCase))
                try
                {
                    string acf = Path.Combine(l, @"steamapps\appmanifest_464500.acf"), common = Path.Combine(l, @"steamapps\common");
                    if (File.Exists(acf))
                        foreach (var line in File.ReadAllLines(acf))
                        {
                            var t = line.Trim();
                            if (!t.StartsWith("\"installdir\"", StringComparison.OrdinalIgnoreCase)) continue;
                            var parts = t.Split('"');
                            if (parts.Length >= 4) { string d = Path.Combine(common, parts[3]); if (File.Exists(Path.Combine(d, Engine.Exe))) res.Add(d); }
                        }
                    if (Directory.Exists(common))
                        foreach (var d in Directory.GetDirectories(common))
                            if (File.Exists(Path.Combine(d, Engine.Exe))) res.Add(d);
                }
                catch { }
            return res.Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        }
    }

    class MainForm : Form
    {
        readonly Payload P;
        readonly TextBox dirBox = new TextBox(), logBox = new TextBox();
        readonly Label stateLbl = new Label();
        readonly Button installBtn = new Button(), uninstallBtn = new Button(), browseBtn = new Button(), closeBtn = new Button();

        public MainForm(Payload p, string dir)
        {
            P = p;
            Text = "灰色的旋律 繁體中文化補丁 " + p.Version;
            Font = new Font("Microsoft JhengHei UI", 9.5f);
            ClientSize = new Size(640, 430); FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            var intro = new Label
            {
                Left = 12, Top = 10, Width = 616, Height = 62,
                Text = "本程式會把 Steam 版《The Melody of Grisaia》（グリザイアの旋律，日文版）的劇本與系統文字改為繁體中文。\r\n" +
                       "原檔會備份到遊戲資料夾的 _zhTW_backup，可隨時解除安裝還原；不會修改存檔。\r\n" +
                       "請先在 Steam 將遊戲語言設為「日文」，並關閉遊戲後再安裝。"
            };
            var dl = new Label { Left = 12, Top = 80, Width = 80, Text = "遊戲資料夾：" };
            dirBox.SetBounds(92, 77, 440, 24);
            browseBtn.SetBounds(538, 76, 90, 26); browseBtn.Text = "瀏覽…";
            stateLbl.SetBounds(12, 110, 616, 40);
            installBtn.SetBounds(12, 152, 140, 32); installBtn.Text = "安裝";
            uninstallBtn.SetBounds(160, 152, 140, 32); uninstallBtn.Text = "解除安裝";
            closeBtn.SetBounds(488, 152, 140, 32); closeBtn.Text = "關閉";
            logBox.SetBounds(12, 194, 616, 224); logBox.Multiline = true; logBox.ReadOnly = true; logBox.ScrollBars = ScrollBars.Vertical;
            Controls.AddRange(new Control[] { intro, dl, dirBox, browseBtn, stateLbl, installBtn, uninstallBtn, closeBtn, logBox });
            browseBtn.Click += (s, e) => { using (var f = new FolderBrowserDialog()) if (f.ShowDialog() == DialogResult.OK) { dirBox.Text = f.SelectedPath; Refresh2(); } };
            dirBox.TextChanged += (s, e) => Refresh2();
            closeBtn.Click += (s, e) => Close();
            installBtn.Click += (s, e) => Run(en => en.Install());
            uninstallBtn.Click += (s, e) => Run(en => en.Uninstall());
            if (!string.IsNullOrEmpty(dir)) dirBox.Text = dir;
            else
            {
                var c = Steam.Candidates();
                if (c.Count >= 1) { dirBox.Text = c[0]; Log("已在 Steam 遊戲庫找到遊戲：" + c[0]); }
                else Log("沒有在 Steam 遊戲庫找到遊戲，請按「瀏覽…」選擇含 GrisaiaAno3.exe 的資料夾。");
            }
            Refresh2();
        }
        void Log(string s) { logBox.AppendText(s + "\r\n"); }
        void Run(Action<Engine> a)
        {
            UseWaitCursor = true; installBtn.Enabled = uninstallBtn.Enabled = false;
            try { a(new Engine(P, dirBox.Text.Trim(), Log)); }
            catch (UnauthorizedAccessException) { Log("錯誤：沒有寫入權限。請以系統管理員身分執行本程式後再試。"); }
            catch (Exception ex) { Log("錯誤：" + ex.Message); }
            UseWaitCursor = false; Refresh2();
        }
        void Refresh2()
        {
            string d; var st = new Engine(P, dirBox.Text.Trim(), null).State(out d);
            switch (st)
            {
                case St.NotFound: stateLbl.Text = "狀態：此資料夾找不到遊戲。"; break;
                case St.Original: stateLbl.Text = "狀態：原版（可安裝）。"; break;
                case St.Installed: stateLbl.Text = "狀態：已安裝繁中補丁 " + P.Version + "。"; break;
                case St.Outdated: stateLbl.Text = "狀態：已安裝舊版補丁，按「安裝」更新。"; break;
                default: stateLbl.Text = "狀態：無法辨識的版本，不會修改任何檔案。" + d; break;
            }
            installBtn.Enabled = st == St.Original || st == St.Outdated;
            uninstallBtn.Enabled = st == St.Installed || st == St.Outdated;
            installBtn.Text = st == St.Outdated ? "更新" : "安裝";
        }
    }

    static class Program
    {
        static void Out(string s) { var b = Encoding.UTF8.GetBytes(s); using (var o = Console.OpenStandardOutput()) o.Write(b, 0, b.Length); }
        [STAThread]
        static int Main(string[] args)
        {
            Payload p;
            try { p = Payload.Load(); }
            catch (Exception ex) { MessageBox.Show("安裝資料損毀：" + ex.Message); return 3; }
            if (args.Length >= 2 && (args[0] == "/status" || args[0] == "/install" || args[0] == "/uninstall"))
            {
                var log = new StringBuilder();
                Engine.IgnoreRunning = args.Contains("/ignore-running");
                try
                {
                    var e = new Engine(p, args[1], s => log.AppendLine(s));
                    if (args[0] == "/install") e.Install();
                    if (args[0] == "/uninstall") e.Uninstall();
                    string d; var st = e.State(out d);
                    log.AppendLine("version=" + p.Version + " state=" + st + " " + d);
                    Out(log.ToString()); return 0;
                }
                catch (Exception ex) { Out(log.ToString() + "ERROR " + ex.Message + "\n"); return 1; }
            }
            string dir = null;
            foreach (var a in args) if (a.StartsWith("/dir=")) dir = a.Substring(5);
            Application.EnableVisualStyles();
            Application.Run(new MainForm(p, dir));
            return 0;
        }
    }

    // 最小 JSON 解析（payload 用）
    class MiniJson
    {
        readonly string s; int i;
        public MiniJson(string s) { this.s = s; }
        public object Parse() { Ws(); return Val(); }
        void Ws() { while (i < s.Length && char.IsWhiteSpace(s[i])) i++; }
        object Val()
        {
            Ws(); char c = s[i];
            if (c == '{') { i++; var d = new Dictionary<string, object>(); Ws(); if (s[i] == '}') { i++; return d; }
                while (true) { Ws(); var k = Str(); Ws(); i++; d[k] = Val(); Ws(); if (s[i++] == '}') return d; } }
            if (c == '[') { i++; var l = new List<object>(); Ws(); if (s[i] == ']') { i++; return l; }
                while (true) { l.Add(Val()); Ws(); if (s[i++] == ']') return l; } }
            if (c == '"') return Str();
            if (string.CompareOrdinal(s, i, "true", 0, 4) == 0) { i += 4; return true; }
            if (string.CompareOrdinal(s, i, "false", 0, 5) == 0) { i += 5; return false; }
            if (string.CompareOrdinal(s, i, "null", 0, 4) == 0) { i += 4; return null; }
            int st = i; while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0) i++;
            return long.Parse(s.Substring(st, i - st));
        }
        string Str()
        {
            var b = new StringBuilder(); i++;
            while (s[i] != '"')
            {
                if (s[i] == '\\')
                {
                    i++; char e = s[i];
                    if (e == 'u') { b.Append((char)Convert.ToInt32(s.Substring(i + 1, 4), 16)); i += 4; }
                    else b.Append(e == 'n' ? '\n' : e == 't' ? '\t' : e == 'r' ? '\r' : e == 'b' ? '\b' : e == 'f' ? '\f' : e);
                }
                else b.Append(s[i]);
                i++;
            }
            i++; return b.ToString();
        }
    }
}
