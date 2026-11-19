r"""在背景派 Codex CLI 工作（不卡住 bridge 佇列）。
  python codex_job.py start --id TX1 --cwd C:\GameDev\grisaia-melody-lab\tx-ja --prompt "請依 TASK.md 完成任務。"
  python codex_job.py status
紀錄：C:\GameDev\grisaia-melody-lab\codex-jobs\<id>\（log.txt、state.json）
沿用 LD2 慣例：用 codex 既有訂閱登入（移除 OPENAI_API_KEY 等環境變數）、預設 gpt-6-astra／推理 max。
"""
import argparse, json, os, subprocess, sys, time, datetime as dt
from pathlib import Path
ROOT = Path(r"C:\GameDev\grisaia-melody-lab\codex-jobs")

def now(): return dt.datetime.now().astimezone().isoformat(timespec="seconds")

def env():
    e = dict(os.environ)
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CODEX_API_KEY"): e.pop(k, None)
    e["PYTHONUTF8"] = "1"
    return e

def worker(a):
    d = ROOT / a.id; st = d / "state.json"
    s = json.loads(st.read_text("utf-8"))
    prompt = " ".join(l.strip() for l in a.prompt.splitlines() if l.strip())
    argv = ["codex.cmd", "exec", "-m", a.model, "-c", f"model_reasoning_effort={a.effort}",
            "--sandbox", "workspace-write", "--skip-git-repo-check", prompt]
    s.update(status="running", argv=argv[:7], started=now()); st.write_text(json.dumps(s, ensure_ascii=False, indent=1), "utf-8")
    with open(d / "log.txt", "w", encoding="utf-8", errors="replace") as log:
        p = subprocess.run(argv, cwd=a.cwd, env=env(), stdout=log, stderr=subprocess.STDOUT, text=True,
                           encoding="utf-8", errors="replace", timeout=a.timeout)
    s.update(status="done" if p.returncode == 0 else "error", rc=p.returncode, finished=now())
    st.write_text(json.dumps(s, ensure_ascii=False, indent=1), "utf-8")

def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="c", required=True)
    for name in ("start", "_work"):
        x = sp.add_parser(name)
        x.add_argument("--id", required=True); x.add_argument("--cwd", required=True); x.add_argument("--prompt", required=True)
        x.add_argument("--model", default="gpt-6-astra"); x.add_argument("--effort", default="max")
        x.add_argument("--timeout", type=int, default=6 * 3600)
    sp.add_parser("status")
    a = ap.parse_args()
    if a.c == "status":
        for d in sorted(ROOT.glob("*/state.json")): print(d.parent.name, d.read_text("utf-8"))
        return
    if a.c == "_work": return worker(a)
    d = ROOT / a.id; d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps({"id": a.id, "cwd": a.cwd, "status": "queued", "created": now()}, ensure_ascii=False), "utf-8")
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([sys.executable, __file__, "_work", "--id", a.id, "--cwd", a.cwd, "--prompt", a.prompt,
                      "--model", a.model, "--effort", a.effort, "--timeout", str(a.timeout)],
                     creationflags=flags, close_fds=True, env=env())
    print("started", a.id)

if __name__ == "__main__":
    main()
