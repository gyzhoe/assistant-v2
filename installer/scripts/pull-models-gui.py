"""pull-models-gui.py - Download Ollama models with a native tkinter progress window.

Falls back to console-based progress if tkinter is unavailable (e.g. embeddable Python).
Usage: python pull-models-gui.py [--app-dir <path>]
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False

OLLAMA_BASE = "http://127.0.0.1:11435"
MODELS = ["nomic-embed-text", "qwen3.5:9b"]
OLLAMA_START_TIMEOUT = 30  # seconds to wait for Ollama to become reachable
AUTO_CLOSE_DELAY = 3000  # ms to wait before closing after success
PULL_MAX_RETRIES = 3  # retry up to 3 times on failure (4 total attempts)
PULL_RETRY_DELAY = 3  # seconds to wait before retrying
RETRY_SHORTCUT_NAME = "Setup LLM Models"  # Start Menu shortcut for manual retry

# Module-level logger; configured by setup_logging() after app_dir is resolved.
log = logging.getLogger("pull-models-gui")


def write_chain_log(app_dir: str, message: str, script_name: str = "pull-models-gui.py") -> None:
    """Append a timestamped chain-level outcome record to logs/install-chain.log.

    All installer scripts write to this shared file so the complete install
    chain outcome is visible in one place.  Failures here are silent so that
    a logging error never masks the real error.
    """
    try:
        logs_dir = os.path.join(app_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        chain_log = os.path.join(logs_dir, "install-chain.log")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [CHAIN] [{script_name}] {message}\n"
        with open(chain_log, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as exc:
        log.warning("Failed to write to install-chain.log: %s", exc)


def setup_logging(app_dir: str) -> None:
    """Configure file + stream logging to {app_dir}/logs/pull-models-gui.log."""
    logs_dir = os.path.join(app_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, "pull-models-gui.log")

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)

    log.setLevel(logging.DEBUG)
    log.addHandler(fh)
    log.addHandler(sh)
    log.info("pull-models-gui started. Log: %s", log_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", default=None, help="App install directory")
    parser.add_argument(
        "--skip",
        action="store_true",
        default=False,
        help=(
            "Skip model pull and exit 0 cleanly. "
            "Also honoured automatically when the SKIP_MODEL_PULL environment "
            "variable is set to any non-empty value (e.g. in CI builds)."
        ),
    )
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
    except Exception as exc:
        log.debug("Ollama not yet reachable: %s", exc)
        return False


def verify_model_exists(name: str) -> bool:
    """Check /api/tags to confirm *name* was pulled successfully.

    Matches the short name (e.g. ``qwen3.5:9b``) against each model's
    ``name`` field.  When the caller omits a tag the comparison also
    accepts ``<name>:latest``.
    """
    try:
        resp = urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=5)
        data = json.loads(resp.read().decode())
    except Exception as exc:
        log.error("Failed to query /api/tags for model verification: %s", exc)
        return False

    candidates = {name.lower()}
    if ":" not in name:
        candidates.add(f"{name}:latest".lower())

    for m in data.get("models", []):
        if m.get("name", "").lower() in candidates:
            return True
    return False


def _ollama_env(ollama_exe: str) -> dict[str, str]:
    """Build environment for Ollama with runners dir and custom port."""
    env = os.environ.copy()
    env["OLLAMA_HOST"] = "127.0.0.1:11435"
    env["OLLAMA_VULKAN"] = "1"
    runners_dir = os.path.join(os.path.dirname(ollama_exe), "lib", "ollama")
    if os.path.isdir(runners_dir):
        env["OLLAMA_RUNNERS_DIR"] = runners_dir
    return env


def ensure_ollama_running(ollama_exe: str) -> bool:
    if ollama_reachable():
        log.info("Ollama already reachable at %s", OLLAMA_BASE)
        return True
    log.info("Starting Ollama: %s", ollama_exe)
    if os.path.isfile(ollama_exe):
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.Popen([ollama_exe, "serve"], creationflags=flags,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=_ollama_env(ollama_exe))
    else:
        log.warning("Ollama executable not found: %s", ollama_exe)
    deadline = time.time() + OLLAMA_START_TIMEOUT
    while time.time() < deadline:
        time.sleep(1)
        if ollama_reachable():
            log.info("Ollama is reachable")
            return True
    log.error("Ollama did not become reachable within %ds", OLLAMA_START_TIMEOUT)
    return False


class ModelPullError(Exception):
    """Raised when Ollama returns an error during model pull."""


def pull_model(name: str, on_progress: "callable") -> None:
    """Stream-pull a model; call on_progress(status, pct) on each JSON line.

    Raises ModelPullError if Ollama returns an error object in the stream.
    """
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
            # Ollama signals errors via an "error" key in the JSON stream
            if "error" in obj:
                raise ModelPullError(obj["error"])
            status = obj.get("status", "")
            total = obj.get("total", 0)
            completed = obj.get("completed", 0)
            pct = (completed / total * 100) if total > 0 else None
            size_info = f"  ({fmt_size(completed)} / {fmt_size(total)})" if total > 0 else ""
            on_progress(status + size_info, pct)


def pull_model_with_retry(
    name: str,
    on_progress: "callable",
    on_retry: "callable | None" = None,
) -> None:
    """Pull a model, retrying up to PULL_MAX_RETRIES times on failure.

    *on_retry(attempt, error)* is called before each retry so callers can
    update the UI (e.g. "Retrying…").  If all attempts fail the last
    exception is re-raised.
    """
    last_exc: Exception | None = None
    total_attempts = 1 + PULL_MAX_RETRIES
    for attempt in range(total_attempts):
        log.info(
            "Pull attempt %d of %d started for %s",
            attempt + 1, total_attempts, name,
        )
        try:
            pull_model(name, on_progress)
            log.info(
                "Pull attempt %d of %d succeeded for %s",
                attempt + 1, total_attempts, name,
            )
            return  # success
        except Exception as exc:
            last_exc = exc
            log.warning(
                "Pull attempt %d of %d for %s failed [%s]: %s",
                attempt + 1, total_attempts, name, type(exc).__name__, exc,
            )
            if attempt < PULL_MAX_RETRIES:
                log.info(
                    "Sleeping %ds before attempt %d of %d for %s…",
                    PULL_RETRY_DELAY, attempt + 2, total_attempts, name,
                )
                if on_retry is not None:
                    on_retry(attempt + 1, exc)
                time.sleep(PULL_RETRY_DELAY)
    log.error(
        "All %d attempts exhausted for %s. Last error [%s]: %s",
        total_attempts, name, type(last_exc).__name__, last_exc,
    )
    # All attempts exhausted – propagate the last error
    raise last_exc  # type: ignore[misc]


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

        # Disable the X (close) button while a download or failure dialog is
        # pending.  The window is only destroyed programmatically — either after
        # the user explicitly acknowledges an error dialog (post_fatal_error /
        # Ollama/verify error handlers) or after the AUTO_CLOSE_DELAY on success
        # (post_done).  This guarantees the installer's waituntilterminated flag
        # correctly holds the Run sequence until the user has been informed.
        root.protocol("WM_DELETE_WINDOW", lambda: None)

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

    def post_fatal_error(self, model: str, exc: Exception) -> None:
        """Show the inline error label then a blocking messagebox directing the user to retry.

        This is called on the worker thread; both UI updates are dispatched to
        the main thread via root.after so tkinter is only touched from its own
        thread.  The messagebox is modal and will block the event loop until the
        user dismisses it, after which the window is destroyed.
        """
        inline_msg = (
            f"Failed to pull {model} after {1 + PULL_MAX_RETRIES} attempts: {exc}"
        )
        dialog_msg = (
            f"Model download failed: {model}\n\n"
            f"All {1 + PULL_MAX_RETRIES} download attempts were exhausted.\n\n"
            f"To retry, open the Start Menu and run:\n"
            f"  \u2192 AI Helpdesk Assistant \u2192 {RETRY_SHORTCUT_NAME}\n\n"
            f"Error detail: {exc}"
        )

        def _show() -> None:
            # Update the inline status labels first
            self.model_label.config(text="Download Failed")
            self.bar.stop()
            self.bar.config(mode="determinate")
            self.bar["value"] = 0
            self.status_label.config(text=inline_msg, foreground="#c00")
            # Show blocking modal dialog — user must click OK before window closes
            messagebox.showerror(
                title="AI Helpdesk Assistant \u2014 Model Download Failed",
                message=dialog_msg,
                parent=self.root,
            )
            self.root.destroy()

        self.root.after(0, _show)


def worker(win: PullWindow, app_dir: str) -> None:
    ollama_exe = find_ollama_exe(app_dir)

    log.info("worker: starting model pull for %d model(s)", len(MODELS))
    win.post("Starting Ollama\u2026", "Waiting for Ollama to become reachable\u2026", None, f"0 of {len(MODELS)} models")
    if not ensure_ollama_running(ollama_exe):
        msg = f"Ollama did not start within {OLLAMA_START_TIMEOUT}s. Check {ollama_exe}"
        log.error("%s — user directed to '%s' shortcut", msg, RETRY_SHORTCUT_NAME)
        write_chain_log(app_dir, f"FAILED - Ollama did not start within {OLLAMA_START_TIMEOUT}s")
        write_chain_log(app_dir, "=== INSTALL CHAIN COMPLETE - FAILED ===")

        def _ollama_err() -> None:
            win.model_label.config(text="Ollama Startup Failed")
            win.bar.stop()
            win.bar.config(mode="determinate")
            win.bar["value"] = 0
            win.status_label.config(text=msg, foreground="#c00")
            messagebox.showerror(
                title="AI Helpdesk Assistant \u2014 Ollama Startup Failed",
                message=(
                    f"{msg}\n\n"
                    f"To retry the model download, open the Start Menu and run:\n"
                    f"  \u2192 AI Helpdesk Assistant \u2192 {RETRY_SHORTCUT_NAME}"
                ),
                parent=win.root,
            )
            win.root.destroy()

        win.root.after(0, _ollama_err)
        return

    for idx, model in enumerate(MODELS):
        overall = f"{idx} of {len(MODELS)} models"
        log.info("Starting pull for model: %s (%s)", model, overall)
        win.post(f"Pulling {model}", "Connecting\u2026", None, overall)
        try:
            def on_progress(status: str, pct: "float | None", _m: str = model, _i: int = idx) -> None:
                win.post(f"Pulling {_m}", status, pct, f"{_i} of {len(MODELS)} models")

            def on_retry(attempt: int, exc: Exception, _m: str = model, _i: int = idx) -> None:
                win.post(
                    f"Retrying {_m} (attempt {attempt} of {PULL_MAX_RETRIES})",
                    f"Pull failed: {exc} \u2014 retrying in {PULL_RETRY_DELAY}s\u2026",
                    None,
                    f"{_i} of {len(MODELS)} models",
                )

            pull_model_with_retry(model, on_progress, on_retry)
            log.info("Pull complete for model: %s", model)
        except Exception as exc:
            log.error(
                "All %d attempts exhausted for %s: %s — user directed to '%s' shortcut",
                1 + PULL_MAX_RETRIES, model, exc, RETRY_SHORTCUT_NAME,
            )
            write_chain_log(app_dir, f"FAILED - {model} pull exhausted {1 + PULL_MAX_RETRIES} attempts: {exc}")
            write_chain_log(app_dir, "=== INSTALL CHAIN COMPLETE - FAILED ===")
            win.post_fatal_error(model, exc)
            return

    # Verify all models are actually present via /api/tags
    log.info("Verifying downloaded models via /api/tags")
    win.post("Verifying models\u2026", "Checking downloaded models\u2026", None,
             f"{len(MODELS)} of {len(MODELS)} models")
    missing = [m for m in MODELS if not verify_model_exists(m)]
    if missing:
        missing_str = ", ".join(missing)
        msg = f"Verification failed — missing models: {missing_str}"
        log.error("%s — user directed to '%s' shortcut", msg, RETRY_SHORTCUT_NAME)
        write_chain_log(app_dir, f"FAILED - verification: missing models: {missing_str}")
        write_chain_log(app_dir, "=== INSTALL CHAIN COMPLETE - FAILED ===")

        def _verify_err() -> None:
            win.model_label.config(text="Verification Failed")
            win.bar.stop()
            win.bar.config(mode="determinate")
            win.bar["value"] = 0
            win.status_label.config(
                text=f"Verification failed \u2014 missing: {missing_str}", foreground="#c00"
            )
            messagebox.showerror(
                title="AI Helpdesk Assistant \u2014 Model Verification Failed",
                message=(
                    f"The following model(s) could not be verified after download:\n"
                    f"  {missing_str}\n\n"
                    f"To retry, open the Start Menu and run:\n"
                    f"  \u2192 AI Helpdesk Assistant \u2192 {RETRY_SHORTCUT_NAME}"
                ),
                parent=win.root,
            )
            win.root.destroy()

        win.root.after(0, _verify_err)
        return

    log.info("All %d model(s) downloaded and verified successfully.", len(MODELS))
    write_chain_log(app_dir, f"SUCCESS - all {len(MODELS)} model(s) pulled and verified")
    write_chain_log(app_dir, "=== INSTALL CHAIN COMPLETE - SUCCESS ===")
    win.post_done()


def _blocking_console_dialog(title: str, message: str) -> None:
    """Print a formatted error notice and block until the user presses Enter.

    Equivalent to the tkinter ``messagebox.showerror`` used in the GUI path.
    In headless / piped environments where stdin is not a TTY the ``input()``
    call raises ``EOFError`` or ``OSError``; in that case we wait 5 seconds so
    the installer log has time to flush before the process exits.
    """
    border = "=" * 60
    print(f"\n{border}", file=sys.stderr)
    print(f"  {title}", file=sys.stderr)
    print(border, file=sys.stderr)
    for line in message.splitlines():
        print(f"  {line}", file=sys.stderr)
    print(border, file=sys.stderr)
    try:
        input("\nPress Enter to exit... ")
    except (EOFError, OSError):
        # stdin is closed or not a TTY (headless / piped install); wait briefly
        # so the log file has time to flush before the process terminates.
        print(
            "\n(No interactive console detected — exiting in 5s…)",
            file=sys.stderr,
        )
        time.sleep(5)


def console_pull(app_dir: str, headless: bool = False) -> None:
    """Fallback: pull models with console output when tkinter is unavailable.

    *headless* is ``True`` when the caller detected that the display is
    unavailable (e.g. a ``TclError`` when constructing ``tk.Tk()``).  The flag
    is used only for the startup banner; all other behaviour is identical.
    """
    reason = "no display available" if headless else "tkinter unavailable"
    print("=" * 60)
    print("AI Helpdesk Assistant - Downloading Models")
    print(f"(console mode: {reason})")
    print("=" * 60)

    log.info("console_pull: starting (%s)", reason)
    ollama_exe = find_ollama_exe(app_dir)

    print("Starting Ollama...")
    if not ensure_ollama_running(ollama_exe):
        msg = f"Ollama did not start within {OLLAMA_START_TIMEOUT}s."
        log.error(
            "%s Exe: %s — user directed to '%s' shortcut",
            msg, ollama_exe, RETRY_SHORTCUT_NAME,
        )
        write_chain_log(app_dir, f"FAILED - Ollama did not start within {OLLAMA_START_TIMEOUT}s")
        write_chain_log(app_dir, "=== INSTALL CHAIN COMPLETE - FAILED ===")
        _blocking_console_dialog(
            "AI Helpdesk Assistant — Ollama Startup Failed",
            (
                f"{msg}\n"
                f"Executable: {ollama_exe}\n"
                f"\n"
                f"To retry the model download, open the Start Menu and run:\n"
                f"  -> AI Helpdesk Assistant -> {RETRY_SHORTCUT_NAME}"
            ),
        )
        sys.exit(1)

    for idx, model in enumerate(MODELS):
        log.info("[%d/%d] Pulling %s", idx + 1, len(MODELS), model)
        print(f"\n[{idx + 1}/{len(MODELS)}] Pulling {model}...")
        try:
            last_status = ""

            def on_progress(status: str, pct: "float | None") -> None:
                nonlocal last_status
                if pct is not None:
                    bar_len = 30
                    filled = int(bar_len * pct / 100)
                    bar = "#" * filled + "-" * (bar_len - filled)
                    print(f"\r  [{bar}] {pct:5.1f}%  {status[:60]}", end="", flush=True)
                elif status != last_status:
                    print(f"  {status}")
                last_status = status

            def on_retry(attempt: int, exc: Exception) -> None:
                print(f"\n  Pull failed: {exc}")
                print(f"  Retrying in {PULL_RETRY_DELAY}s (attempt {attempt} of {PULL_MAX_RETRIES})...")

            pull_model_with_retry(model, on_progress, on_retry)
            log.info("Pull complete for %s", model)
            print()  # newline after progress bar
        except Exception as exc:
            log.error(
                "All %d attempts exhausted for %s: %s — user directed to '%s' shortcut",
                1 + PULL_MAX_RETRIES, model, exc, RETRY_SHORTCUT_NAME,
            )
            write_chain_log(app_dir, f"FAILED - {model} pull exhausted {1 + PULL_MAX_RETRIES} attempts: {exc}")
            write_chain_log(app_dir, "=== INSTALL CHAIN COMPLETE - FAILED ===")
            _blocking_console_dialog(
                "AI Helpdesk Assistant — Model Download Failed",
                (
                    f"Model download failed: {model}\n"
                    f"\n"
                    f"All {1 + PULL_MAX_RETRIES} download attempts were exhausted.\n"
                    f"\n"
                    f"To retry, open the Start Menu and run:\n"
                    f"  -> AI Helpdesk Assistant -> {RETRY_SHORTCUT_NAME}\n"
                    f"\n"
                    f"Error detail: {exc}"
                ),
            )
            sys.exit(1)

    # Verify all models are actually present via /api/tags
    log.info("Verifying downloaded models via /api/tags")
    print("\nVerifying downloaded models...")
    missing = [m for m in MODELS if not verify_model_exists(m)]
    if missing:
        missing_str = ", ".join(missing)
        log.error(
            "Verification failed - missing models: %s — user directed to '%s' shortcut",
            missing_str, RETRY_SHORTCUT_NAME,
        )
        write_chain_log(app_dir, f"FAILED - verification: missing models: {missing_str}")
        write_chain_log(app_dir, "=== INSTALL CHAIN COMPLETE - FAILED ===")
        _blocking_console_dialog(
            "AI Helpdesk Assistant — Model Verification Failed",
            (
                f"The following model(s) could not be verified after download:\n"
                f"  {missing_str}\n"
                f"\n"
                f"To retry, open the Start Menu and run:\n"
                f"  -> AI Helpdesk Assistant -> {RETRY_SHORTCUT_NAME}"
            ),
        )
        sys.exit(1)

    log.info("All %d model(s) downloaded and verified successfully.", len(MODELS))
    print(f"\nDone! All {len(MODELS)} models downloaded and verified.")
    write_chain_log(app_dir, f"SUCCESS - all {len(MODELS)} model(s) pulled and verified")
    write_chain_log(app_dir, "=== INSTALL CHAIN COMPLETE - SUCCESS ===")
    time.sleep(2)


def main() -> None:
    args = parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = args.app_dir or os.path.dirname(script_dir)

    setup_logging(app_dir)
    write_chain_log(app_dir, "STARTED")

    # --- Graceful skip for CI / offline environments ----------------------------
    # Honour SKIP_MODEL_PULL env var (any non-empty value) or the --skip flag.
    # Exits 0 with a clear log entry so the installer chain records SKIPPED
    # rather than a silent success or an unexpected failure.
    _skip_env = os.environ.get("SKIP_MODEL_PULL", "").strip()
    if args.skip or _skip_env:
        reason = "--skip flag" if args.skip else f"SKIP_MODEL_PULL={_skip_env!r}"
        log.info(
            "Model pull skipped (%s). "
            "Run 'Setup LLM Models' from the Start Menu when ready to download.",
            reason,
        )
        write_chain_log(app_dir, f"SKIPPED - model pull bypassed ({reason})")
        return  # exit 0; no dialog, no pull attempt
    # ---------------------------------------------------------------------------

    if not HAS_TKINTER:
        log.info("tkinter unavailable — using console fallback")
        console_pull(app_dir)
        return

    # tkinter is importable but may still fail in a headless environment
    # (e.g. no DISPLAY on Linux, or a locked Windows session).  Catch the
    # TclError that tk.Tk() raises in those cases and fall back to console.
    log.info("tkinter available — launching GUI")
    try:
        root = tk.Tk()
    except Exception as exc:
        log.info(
            "tkinter display error (%s: %s) — using console fallback",
            type(exc).__name__, exc,
        )
        console_pull(app_dir, headless=True)
        return

    style = ttk.Style(root)
    style.theme_use("vista")

    win = PullWindow(root, app_dir)
    t = threading.Thread(target=worker, args=(win, app_dir), daemon=True)
    t.start()
    root.mainloop()
    log.info("GUI mainloop exited")


if __name__ == "__main__":
    main()
