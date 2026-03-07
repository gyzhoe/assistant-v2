"""pull-models-gui.py - Download GGUF model files with a native tkinter progress window.

Falls back to console-based progress if tkinter is unavailable (e.g. embeddable Python).
Usage: python pull-models-gui.py [--app-dir <path>]
"""

import argparse
import logging
import os
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

MODELS = [
    {"name": "nomic-embed-text-v1.5.f16.gguf", "url": "https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.f16.gguf", "desc": "~262 MB"},
    {"name": "Qwen3.5-9B-Q4_K_M.gguf", "url": "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf", "desc": "~5.3 GB"},
]
AUTO_CLOSE_DELAY = 3000  # ms to wait before closing after success
DOWNLOAD_MAX_RETRIES = 3  # retry up to 3 times on failure (4 total attempts)
DOWNLOAD_RETRY_DELAY = 3  # seconds to wait before retrying
RETRY_SHORTCUT_NAME = "Setup LLM Models"  # Start Menu shortcut for manual retry

# Module-level logger; configured by setup_logging() after app_dir is resolved.
log = logging.getLogger("pull-models-gui")


def write_chain_log(app_dir: str, message: str, script_name: str = "pull-models-gui.py") -> None:
    """Append a timestamped chain-level outcome record to logs/install-chain.log."""
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
            "Skip model download and exit 0 cleanly. "
            "Also honoured automatically when the SKIP_MODEL_PULL environment "
            "variable is set to any non-empty value (e.g. in CI builds)."
        ),
    )
    return parser.parse_args()


def fmt_size(n: int) -> str:
    if n >= 1_073_741_824:
        return f"{n / 1_073_741_824:.1f} GB"
    return f"{n / 1_048_576:.1f} MB"


class DownloadError(Exception):
    """Raised when a model file download fails."""


def download_model(
    name: str,
    url: str,
    dest_dir: str,
    on_progress: "callable",
) -> None:
    """Download a GGUF model file with streaming progress.

    Calls on_progress(status, pct) periodically during download.
    Raises DownloadError on failure.
    """
    dest_path = os.path.join(dest_dir, name)
    tmp_path = dest_path + ".tmp"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AIHelpdeskAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1 MB chunks

            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    pct = (downloaded / total * 100) if total > 0 else None
                    size_info = f"{fmt_size(downloaded)} / {fmt_size(total)}" if total > 0 else fmt_size(downloaded)
                    on_progress(f"Downloading {size_info}", pct)

        # Verify non-empty download
        if os.path.getsize(tmp_path) == 0:
            raise DownloadError(f"Downloaded file is empty: {name}")

        # Atomic rename
        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.rename(tmp_path, dest_path)

    except DownloadError:
        raise
    except Exception as exc:
        # Clean up partial download
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise DownloadError(f"Failed to download {name}: {exc}") from exc


def download_model_with_retry(
    name: str,
    url: str,
    dest_dir: str,
    on_progress: "callable",
    on_retry: "callable | None" = None,
) -> None:
    """Download a model, retrying up to DOWNLOAD_MAX_RETRIES times on failure."""
    last_exc: Exception | None = None
    total_attempts = 1 + DOWNLOAD_MAX_RETRIES
    for attempt in range(total_attempts):
        log.info(
            "Download attempt %d of %d started for %s",
            attempt + 1, total_attempts, name,
        )
        try:
            download_model(name, url, dest_dir, on_progress)
            log.info(
                "Download attempt %d of %d succeeded for %s",
                attempt + 1, total_attempts, name,
            )
            return  # success
        except Exception as exc:
            last_exc = exc
            log.warning(
                "Download attempt %d of %d for %s failed [%s]: %s",
                attempt + 1, total_attempts, name, type(exc).__name__, exc,
            )
            if attempt < DOWNLOAD_MAX_RETRIES:
                log.info(
                    "Sleeping %ds before attempt %d of %d for %s...",
                    DOWNLOAD_RETRY_DELAY, attempt + 2, total_attempts, name,
                )
                if on_retry is not None:
                    on_retry(attempt + 1, exc)
                time.sleep(DOWNLOAD_RETRY_DELAY)
    log.error(
        "All %d attempts exhausted for %s. Last error [%s]: %s",
        total_attempts, name, type(last_exc).__name__, last_exc,
    )
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

    def post_fatal_error(self, model_name: str, exc: Exception) -> None:
        """Show the inline error label then a blocking messagebox directing the user to retry."""
        inline_msg = (
            f"Failed to download {model_name} after {1 + DOWNLOAD_MAX_RETRIES} attempts: {exc}"
        )
        dialog_msg = (
            f"Model download failed: {model_name}\n\n"
            f"All {1 + DOWNLOAD_MAX_RETRIES} download attempts were exhausted.\n\n"
            f"To retry, open the Start Menu and run:\n"
            f"  \u2192 AI Helpdesk Assistant \u2192 {RETRY_SHORTCUT_NAME}\n\n"
            f"Error detail: {exc}"
        )

        def _show() -> None:
            self.model_label.config(text="Download Failed")
            self.bar.stop()
            self.bar.config(mode="determinate")
            self.bar["value"] = 0
            self.status_label.config(text=inline_msg, foreground="#c00")
            messagebox.showerror(
                title="AI Helpdesk Assistant \u2014 Model Download Failed",
                message=dialog_msg,
                parent=self.root,
            )
            self.root.destroy()

        self.root.after(0, _show)


def worker(win: PullWindow, app_dir: str) -> None:
    models_dir = os.path.join(app_dir, "models")
    os.makedirs(models_dir, exist_ok=True)

    log.info("worker: starting model download for %d model(s)", len(MODELS))

    for idx, model in enumerate(MODELS):
        name = model["name"]
        url = model["url"]
        dest_path = os.path.join(models_dir, name)
        overall = f"{idx} of {len(MODELS)} models"

        # Skip if already downloaded
        if os.path.isfile(dest_path) and os.path.getsize(dest_path) > 0:
            log.info("Model %s already exists (%s) - skipping", name, fmt_size(os.path.getsize(dest_path)))
            continue

        log.info("Starting download for model: %s (%s)", name, overall)
        win.post(f"Downloading {name}", "Connecting\u2026", None, overall)
        try:
            def on_progress(status: str, pct: "float | None", _n: str = name, _i: int = idx) -> None:
                win.post(f"Downloading {_n}", status, pct, f"{_i} of {len(MODELS)} models")

            def on_retry(attempt: int, exc: Exception, _n: str = name, _i: int = idx) -> None:
                win.post(
                    f"Retrying {_n} (attempt {attempt} of {DOWNLOAD_MAX_RETRIES})",
                    f"Download failed: {exc} \u2014 retrying in {DOWNLOAD_RETRY_DELAY}s\u2026",
                    None,
                    f"{_i} of {len(MODELS)} models",
                )

            download_model_with_retry(name, url, models_dir, on_progress, on_retry)
            log.info("Download complete for model: %s", name)
        except Exception as exc:
            log.error(
                "All %d attempts exhausted for %s: %s — user directed to '%s' shortcut",
                1 + DOWNLOAD_MAX_RETRIES, name, exc, RETRY_SHORTCUT_NAME,
            )
            write_chain_log(app_dir, f"FAILED - {name} download exhausted {1 + DOWNLOAD_MAX_RETRIES} attempts: {exc}")
            write_chain_log(app_dir, "=== INSTALL CHAIN COMPLETE - FAILED ===")
            win.post_fatal_error(name, exc)
            return

    # Verify all models are present
    log.info("Verifying downloaded models")
    win.post("Verifying models\u2026", "Checking downloaded models\u2026", None,
             f"{len(MODELS)} of {len(MODELS)} models")
    missing = [m["name"] for m in MODELS if not os.path.isfile(os.path.join(models_dir, m["name"])) or os.path.getsize(os.path.join(models_dir, m["name"])) == 0]
    if missing:
        missing_str = ", ".join(missing)
        msg = f"Verification failed \u2014 missing models: {missing_str}"
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
    write_chain_log(app_dir, f"SUCCESS - all {len(MODELS)} model(s) downloaded and verified")
    write_chain_log(app_dir, "=== INSTALL CHAIN COMPLETE - SUCCESS ===")
    win.post_done()


def _blocking_console_dialog(title: str, message: str) -> None:
    """Print a formatted error notice and block until the user presses Enter."""
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
        print(
            "\n(No interactive console detected — exiting in 5s...)",
            file=sys.stderr,
        )
        time.sleep(5)


def console_pull(app_dir: str, headless: bool = False) -> None:
    """Fallback: download models with console output when tkinter is unavailable."""
    reason = "no display available" if headless else "tkinter unavailable"
    print("=" * 60)
    print("AI Helpdesk Assistant - Downloading Models")
    print(f"(console mode: {reason})")
    print("=" * 60)

    log.info("console_pull: starting (%s)", reason)
    models_dir = os.path.join(app_dir, "models")
    os.makedirs(models_dir, exist_ok=True)

    for idx, model in enumerate(MODELS):
        name = model["name"]
        url = model["url"]
        dest_path = os.path.join(models_dir, name)

        # Skip if already downloaded
        if os.path.isfile(dest_path) and os.path.getsize(dest_path) > 0:
            size = fmt_size(os.path.getsize(dest_path))
            log.info("[%d/%d] %s already exists (%s) - skipping", idx + 1, len(MODELS), name, size)
            print(f"\n[{idx + 1}/{len(MODELS)}] {name} already exists ({size}) - skipping")
            continue

        log.info("[%d/%d] Downloading %s", idx + 1, len(MODELS), name)
        print(f"\n[{idx + 1}/{len(MODELS)}] Downloading {name} ({model['desc']})...")
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
                print(f"\n  Download failed: {exc}")
                print(f"  Retrying in {DOWNLOAD_RETRY_DELAY}s (attempt {attempt} of {DOWNLOAD_MAX_RETRIES})...")

            download_model_with_retry(name, url, models_dir, on_progress, on_retry)
            log.info("Download complete for %s", name)
            print()  # newline after progress bar
        except Exception as exc:
            log.error(
                "All %d attempts exhausted for %s: %s — user directed to '%s' shortcut",
                1 + DOWNLOAD_MAX_RETRIES, name, exc, RETRY_SHORTCUT_NAME,
            )
            write_chain_log(app_dir, f"FAILED - {name} download exhausted {1 + DOWNLOAD_MAX_RETRIES} attempts: {exc}")
            write_chain_log(app_dir, "=== INSTALL CHAIN COMPLETE - FAILED ===")
            _blocking_console_dialog(
                "AI Helpdesk Assistant — Model Download Failed",
                (
                    f"Model download failed: {name}\n"
                    f"\n"
                    f"All {1 + DOWNLOAD_MAX_RETRIES} download attempts were exhausted.\n"
                    f"\n"
                    f"To retry, open the Start Menu and run:\n"
                    f"  -> AI Helpdesk Assistant -> {RETRY_SHORTCUT_NAME}\n"
                    f"\n"
                    f"Error detail: {exc}"
                ),
            )
            sys.exit(1)

    # Verify all models are present
    log.info("Verifying downloaded models")
    print("\nVerifying downloaded models...")
    missing = [m["name"] for m in MODELS if not os.path.isfile(os.path.join(models_dir, m["name"])) or os.path.getsize(os.path.join(models_dir, m["name"])) == 0]
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
    write_chain_log(app_dir, f"SUCCESS - all {len(MODELS)} model(s) downloaded and verified")
    write_chain_log(app_dir, "=== INSTALL CHAIN COMPLETE - SUCCESS ===")
    time.sleep(2)


def main() -> None:
    args = parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = args.app_dir or os.path.dirname(script_dir)

    setup_logging(app_dir)
    write_chain_log(app_dir, "STARTED")

    # --- Graceful skip for CI / offline environments ---
    _skip_env = os.environ.get("SKIP_MODEL_PULL", "").strip()
    if args.skip or _skip_env:
        reason = "--skip flag" if args.skip else f"SKIP_MODEL_PULL={_skip_env!r}"
        log.info(
            "Model download skipped (%s). "
            "Run 'Setup LLM Models' from the Start Menu when ready to download.",
            reason,
        )
        write_chain_log(app_dir, f"SKIPPED - model download bypassed ({reason})")
        return  # exit 0

    if not HAS_TKINTER:
        log.info("tkinter unavailable — using console fallback")
        console_pull(app_dir)
        return

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
