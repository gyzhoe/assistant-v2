"""pull-models-gui.py — Download Ollama models with a native tkinter progress window.

Launch via pythonw.exe so no console window appears.
Usage: pythonw.exe pull-models-gui.py [--app-dir <path>]
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from tkinter import ttk

OLLAMA_BASE = "http://localhost:11435"
MODELS = ["nomic-embed-text", "qwen3.5:9b"]
OLLAMA_START_TIMEOUT = 30  # seconds to wait for Ollama to become reachable
AUTO_CLOSE_DELAY = 3000  # ms to wait before closing after success


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", default=None, help="App install directory")
    return parser.parse_args()


def find_ollama_exe(app_dir: str) -> str:
    return os.path.join(app_dir, "tools", "ollama.exe")


def fmt_size(n: int) -> str:
    if n >= 1_073_741_824:
        return f"{n / 1_073_741_824:.1f} GB"
    return f"{n / 1_048_576:.1f} MB"


def ollama_reachable() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=2)
        return True
    except Exception:
        return False


def _ollama_env(ollama_exe: str) -> dict[str, str]:
    """Build environment for Ollama with runners dir and custom port."""
    env = os.environ.copy()
    env["OLLAMA_HOST"] = "127.0.0.1:11435"
    runners_dir = os.path.join(os.path.dirname(ollama_exe), "lib", "ollama")
    if os.path.isdir(runners_dir):
        env["OLLAMA_RUNNERS_DIR"] = runners_dir
    return env


def ensure_ollama_running(ollama_exe: str) -> bool:
    if ollama_reachable():
        return True
    if os.path.isfile(ollama_exe):
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.Popen([ollama_exe, "serve"], creationflags=flags,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=_ollama_env(ollama_exe))
    deadline = time.time() + OLLAMA_START_TIMEOUT
    while time.time() < deadline:
        time.sleep(1)
        if ollama_reachable():
            return True
    return False


def pull_model(name: str, on_progress: "callable") -> None:
    """Stream-pull a model; call on_progress(status, pct) on each JSON line."""
    body = json.dumps({"name": name, "stream": True}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/pull",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            status = obj.get("status", "")
            total = obj.get("total", 0)
            completed = obj.get("completed", 0)
            pct = (completed / total * 100) if total > 0 else None
            size_info = f"  ({fmt_size(completed)} / {fmt_size(total)})" if total > 0 else ""
            on_progress(status + size_info, pct)


class PullWindow:
    def __init__(self, root: tk.Tk, app_dir: str) -> None:
        self.root = root
        self.app_dir = app_dir
        self._build_ui()

    def _build_ui(self) -> None:
        root = self.root
        root.title("AI Helpdesk Assistant \u2014 Downloading Models")
        root.resizable(False, False)
        root.attributes("-topmost", True)

        W = 460
        root.geometry(f"{W}x170")
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = (sw - W) // 2
        y = (sh - 170) // 2
        root.geometry(f"{W}x170+{x}+{y}")

        pad = {"padx": 16, "pady": 4}

        self.model_label = ttk.Label(root, text="Starting\u2026", font=("Segoe UI", 9, "bold"))
        self.model_label.pack(anchor="w", **pad)

        self.bar = ttk.Progressbar(root, length=W - 32, mode="indeterminate")
        self.bar.pack(padx=16, pady=2)
        self.bar.start(12)

        self.status_label = ttk.Label(root, text="", font=("Segoe UI", 8), foreground="#555")
        self.status_label.pack(anchor="w", **pad)

        self.overall_label = ttk.Label(root, text=f"0 of {len(MODELS)} models", font=("Segoe UI", 8))
        self.overall_label.pack(anchor="w", padx=16, pady=(8, 2))

    def _update(self, model_text: str, status_text: str, pct: "float | None", overall: str) -> None:
        self.model_label.config(text=model_text)
        self.status_label.config(text=status_text)
        self.overall_label.config(text=overall)
        if pct is None:
            if self.bar["mode"] != "indeterminate":
                self.bar.config(mode="indeterminate")
                self.bar.start(12)
        else:
            if self.bar["mode"] != "determinate":
                self.bar.stop()
                self.bar.config(mode="determinate")
            self.bar["value"] = pct

    def post(self, model_text: str, status_text: str, pct: "float | None", overall: str) -> None:
        self.root.after(0, self._update, model_text, status_text, pct, overall)

    def post_done(self) -> None:
        def _done() -> None:
            self.model_label.config(text="Done!")
            self.bar.stop()
            self.bar.config(mode="determinate")
            self.bar["value"] = 100
            self.status_label.config(text="All models downloaded successfully.")
            self.overall_label.config(text=f"{len(MODELS)} of {len(MODELS)} models")
            self.root.after(AUTO_CLOSE_DELAY, self.root.destroy)
        self.root.after(0, _done)

    def post_error(self, msg: str) -> None:
        def _err() -> None:
            self.model_label.config(text="Error")
            self.bar.stop()
            self.bar.config(mode="determinate")
            self.bar["value"] = 0
            self.status_label.config(text=msg, foreground="#c00")
        self.root.after(0, _err)


def worker(win: PullWindow, app_dir: str) -> None:
    ollama_exe = find_ollama_exe(app_dir)

    win.post("Starting Ollama\u2026", "Waiting for Ollama to become reachable\u2026", None, f"0 of {len(MODELS)} models")
    if not ensure_ollama_running(ollama_exe):
        win.post_error(f"Ollama did not start within {OLLAMA_START_TIMEOUT}s. Check {ollama_exe}")
        return

    for idx, model in enumerate(MODELS):
        overall = f"{idx} of {len(MODELS)} models"
        win.post(f"Pulling {model}", "Connecting\u2026", None, overall)
        try:
            def on_progress(status: str, pct: "float | None", _m: str = model, _i: int = idx) -> None:
                win.post(f"Pulling {_m}", status, pct, f"{_i} of {len(MODELS)} models")

            pull_model(model, on_progress)
        except Exception as exc:
            win.post_error(f"Failed to pull {model}: {exc}")
            return

    win.post_done()


def main() -> None:
    args = parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = args.app_dir or os.path.dirname(script_dir)

    root = tk.Tk()
    style = ttk.Style(root)
    style.theme_use("vista")

    win = PullWindow(root, app_dir)
    t = threading.Thread(target=worker, args=(win, app_dir), daemon=True)
    t.start()
    root.mainloop()


if __name__ == "__main__":
    main()
