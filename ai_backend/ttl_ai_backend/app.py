from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .autostart import set_autostart
from .config import BackendSettings, SettingsStore
from .hardware import HardwareProfile, detect_hardware
from .models import CATALOG, CatalogModel, download_model, installed_models
from .runtime import (
    PINNED_LLAMA_CPP_RELEASE,
    describe_process_exit,
    find_server,
    install_runtime,
    release_runtime_assets,
    runtime_backend_matches,
)
from .server import ServerProcess, is_healthy, local_addresses, port_is_available


class BackendManagerApp:
    def __init__(self, root: tk.Tk, start_server: bool = False) -> None:
        self.root = root
        self.root.title("Tabletop Librarian AI Backend")
        self.root.minsize(680, 500)
        self.store = SettingsStore()
        self.settings = self.store.load()
        self.profile: HardwareProfile = detect_hardware()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.server = ServerProcess(
            on_line=lambda line: self.events.put(("log", line)),
            on_exit=lambda code: self.events.put(("server_exit", code)),
        )
        self.download_cancel = threading.Event()
        self.start_after_runtime_install = False

        self._apply_detected_defaults()
        self._build_ui()
        self._refresh_models()
        self._refresh_status()
        self.root.after(150, self._pump_events)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        if start_server:
            self.root.after(400, self.start_server)

    def _apply_detected_defaults(self) -> None:
        # Migrate early prototype defaults that could persist OpenVINO even after
        # hardware policy changed. OpenVINO is no longer an automatic choice.
        if self.settings.backend in {"auto", "openvino"}:
            self.settings.backend = self.profile.recommendation
        if not self.settings.server_path:
            found = find_server(Path(self.settings.runtime_dir))
            if found:
                self.settings.server_path = str(found)
        self.settings.ensure_api_key()
        self.store.save(self.settings)

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 7}
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)

        ttk.Label(outer, text="TTL AI Backend", font=("TkDefaultFont", 16, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        hardware = self.profile.recommendation_label
        if self.profile.gpus:
            hardware += " • " + "; ".join(self.profile.gpus[:2])
        ttk.Label(outer, text=f"Detected: {hardware}").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))

        ttk.Label(outer, text="Model").grid(row=2, column=0, sticky="w", **pad)
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(outer, textvariable=self.model_var, state="readonly")
        self.model_combo.grid(row=2, column=1, sticky="ew", **pad)
        self.model_combo.bind("<<ComboboxSelected>>", lambda _e: self._model_selected())
        ttk.Button(outer, text="Browse…", command=self.browse_model).grid(row=2, column=2, **pad)

        self.catalog_var = tk.StringVar(value=CATALOG[0].name)
        self.catalog_combo = ttk.Combobox(outer, textvariable=self.catalog_var, state="readonly", values=[m.name for m in CATALOG])
        self.catalog_combo.grid(row=3, column=1, sticky="ew", **pad)
        ttk.Button(outer, text="Download Model", command=self.download_selected_model).grid(row=3, column=2, **pad)

        self.download_progress = ttk.Progressbar(outer, mode="determinate", maximum=100)
        self.download_progress.grid(row=4, column=1, sticky="ew", **pad)
        self.download_label = ttk.Label(outer, text="")
        self.download_label.grid(row=4, column=2, sticky="w", **pad)

        ttk.Label(outer, text="Status").grid(row=5, column=0, sticky="w", **pad)
        self.status_var = tk.StringVar(value="Stopped")
        ttk.Label(outer, textvariable=self.status_var, font=("TkDefaultFont", 10, "bold")).grid(row=5, column=1, sticky="w", **pad)
        self.start_button = ttk.Button(outer, text="Start Server", command=self.toggle_server)
        self.start_button.grid(row=5, column=2, **pad)

        ttk.Label(outer, text="llama.cpp runtime").grid(row=6, column=0, sticky="w", **pad)
        self.runtime_var = tk.StringVar(value="Checking…")
        ttk.Label(outer, textvariable=self.runtime_var).grid(row=6, column=1, sticky="w", **pad)
        self.runtime_button = ttk.Button(outer, text="Install Runtime", command=self.install_llama)
        self.runtime_button.grid(row=6, column=2, **pad)

        ttk.Label(outer, text="Server address").grid(row=7, column=0, sticky="w", **pad)
        self.address_var = tk.StringVar()
        ttk.Entry(outer, textvariable=self.address_var, state="readonly").grid(row=7, column=1, sticky="ew", **pad)
        ttk.Button(outer, text="Copy", command=lambda: self._copy(self.address_var.get())).grid(row=7, column=2, **pad)

        ttk.Label(outer, text="API key").grid(row=8, column=0, sticky="w", **pad)
        self.api_var = tk.StringVar(value=self.settings.api_key)
        ttk.Entry(outer, textvariable=self.api_var, state="readonly", show="•").grid(row=8, column=1, sticky="ew", **pad)
        ttk.Button(outer, text="Copy", command=lambda: self._copy(self.settings.api_key)).grid(row=8, column=2, **pad)

        self.advanced_visible = tk.BooleanVar(value=self.settings.advanced_open)
        ttk.Checkbutton(outer, text="Advanced", variable=self.advanced_visible, command=self._toggle_advanced).grid(row=9, column=0, sticky="w", **pad)

        self.advanced = ttk.LabelFrame(outer, text="Advanced settings", padding=10)
        self.advanced.columnconfigure(1, weight=1)
        self._build_advanced()
        if self.advanced_visible.get():
            self.advanced.grid(row=10, column=0, columnspan=3, sticky="nsew", pady=8)

        self.log_frame = ttk.LabelFrame(outer, text="Backend log", padding=6)
        self.log_text = tk.Text(self.log_frame, height=9, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True)
        if self.advanced_visible.get():
            self.log_frame.grid(row=11, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
            outer.rowconfigure(11, weight=1)

    def _build_advanced(self) -> None:
        rows = [
            ("Backend", "backend", ["cuda", "vulkan", "cpu"]),
            ("Context size", "context", None),
            ("Parallel slots", "parallel", None),
            ("Prompt cache RAM (MiB)", "cache_ram", None),
            ("GPU layers", "gpu", None),
            ("Flash attention", "flash", ["auto", "on", "off"]),
            ("Reasoning", "reasoning", ["off", "auto", "on"]),
            ("Host", "host", None),
            ("Port", "port", None),
        ]
        self.backend_var = tk.StringVar(value=self.settings.backend)
        self.context_var = tk.StringVar(value=str(self.settings.context_size))
        self.parallel_var = tk.StringVar(value=str(self.settings.parallel_slots))
        self.cache_ram_var = tk.StringVar(value=str(self.settings.prompt_cache_ram_mb))
        self.gpu_var = tk.StringVar(value=self.settings.gpu_layers)
        self.flash_var = tk.StringVar(value=self.settings.flash_attention)
        self.reasoning_var = tk.StringVar(value=self.settings.reasoning)
        self.host_var = tk.StringVar(value=self.settings.host)
        self.port_var = tk.StringVar(value=str(self.settings.port))
        variables = {
            "backend": self.backend_var,
            "context": self.context_var,
            "parallel": self.parallel_var,
            "cache_ram": self.cache_ram_var,
            "gpu": self.gpu_var,
            "flash": self.flash_var,
            "reasoning": self.reasoning_var,
            "host": self.host_var,
            "port": self.port_var,
        }
        for row, (label, key, values) in enumerate(rows):
            ttk.Label(self.advanced, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
            if values:
                widget = ttk.Combobox(self.advanced, textvariable=variables[key], state="readonly", values=values)
            else:
                widget = ttk.Entry(self.advanced, textvariable=variables[key])
            widget.grid(row=row, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(
            self.advanced,
            text="NVIDIA uses CUDA. AMD and Intel Arc use Vulkan. CPU is a compatibility fallback.",
            wraplength=520,
        ).grid(row=9, column=0, columnspan=3, sticky="w", padx=6, pady=(2, 6))

        ttk.Label(self.advanced, text="llama-server").grid(row=10, column=0, sticky="w", padx=6, pady=4)
        self.server_path_var = tk.StringVar(value=self.settings.server_path)
        ttk.Entry(self.advanced, textvariable=self.server_path_var).grid(row=10, column=1, sticky="ew", padx=6, pady=4)
        ttk.Button(self.advanced, text="Browse…", command=self.browse_server).grid(row=10, column=2, padx=6, pady=4)
        ttk.Button(self.advanced, text="Reinstall / Update Runtime", command=self.install_llama).grid(row=11, column=1, sticky="w", padx=6, pady=6)

        self.autostart_var = tk.BooleanVar(value=self.settings.start_with_os)
        ttk.Checkbutton(self.advanced, text="Start backend automatically when I sign in", variable=self.autostart_var).grid(row=12, column=0, columnspan=2, sticky="w", padx=6, pady=6)
        ttk.Button(self.advanced, text="Save Advanced Settings", command=self.save_advanced).grid(row=13, column=1, sticky="e", padx=6, pady=6)

    def _toggle_advanced(self) -> None:
        self.settings.advanced_open = self.advanced_visible.get()
        if self.advanced_visible.get():
            self.advanced.grid(row=10, column=0, columnspan=3, sticky="nsew", pady=8)
            self.log_frame.grid(row=11, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        else:
            self.advanced.grid_remove()
            self.log_frame.grid_remove()
        self.store.save(self.settings)

    def _copy(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update_idletasks()

    def _append_log(self, line: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _refresh_models(self) -> None:
        models_dir = Path(self.settings.models_dir)
        items = installed_models(models_dir)
        values = [str(p) for p in items]
        if self.settings.model_path and self.settings.model_path not in values and Path(self.settings.model_path).is_file():
            values.append(self.settings.model_path)
        self.model_combo["values"] = values
        if self.settings.model_path in values:
            self.model_var.set(self.settings.model_path)
        elif values:
            self.model_var.set(values[0])
            self.settings.model_path = values[0]
            self.store.save(self.settings)
        else:
            self.model_var.set("")

    def _model_selected(self) -> None:
        self.settings.model_path = self.model_var.get()
        selected_name = Path(self.settings.model_path).name
        self.settings.alias = next((m.alias for m in CATALOG if m.filename == selected_name), "")
        self.store.save(self.settings)

    def browse_model(self) -> None:
        path = filedialog.askopenfilename(title="Select GGUF model", filetypes=[("GGUF model", "*.gguf"), ("All files", "*")])
        if path:
            self.settings.model_path = path
            self.store.save(self.settings)
            self._refresh_models()

    def browse_server(self) -> None:
        path = filedialog.askopenfilename(title="Select llama-server")
        if path:
            self.server_path_var.set(path)

    def _selected_catalog_model(self) -> CatalogModel:
        name = self.catalog_var.get()
        return next((m for m in CATALOG if m.name == name), CATALOG[0])

    def download_selected_model(self) -> None:
        model = self._selected_catalog_model()
        self.download_cancel.clear()
        self.download_progress["value"] = 0
        self.download_label.configure(text="Starting…")

        def worker() -> None:
            try:
                path = download_model(
                    model,
                    Path(self.settings.models_dir),
                    progress=lambda done, total: self.events.put(("download_progress", (done, total))),
                    cancel=self.download_cancel.is_set,
                )
                self.events.put(("download_done", path))
            except Exception as exc:
                self.events.put(("error", f"Model download failed: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def install_llama(self, start_after: bool = False) -> None:
        try:
            self.save_advanced(show_message=False)
        except ValueError:
            return
        self.start_after_runtime_install = start_after
        self.download_label.configure(text="Finding llama.cpp…")
        self.runtime_var.set(f"Installing {self.settings.backend.upper()} runtime…")
        self.runtime_button.configure(state="disabled")

        def worker() -> None:
            try:
                assets = release_runtime_assets(self.profile, self.settings.backend)
                self.events.put(("log", f"Installing pinned llama.cpp {PINNED_LLAMA_CPP_RELEASE}: " + ", ".join(a.name for a in assets)))
                server = install_runtime(
                    assets,
                    Path(self.settings.runtime_dir),
                    progress=lambda done, total: self.events.put(("download_progress", (done, total))),
                )
                self.events.put(("runtime_done", (server, assets[0].backend)))
            except Exception as exc:
                self.events.put(("error", f"llama.cpp installation failed: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def save_advanced(self, show_message: bool = True) -> None:
        try:
            context = int(self.context_var.get())
            port = int(self.port_var.get())
            parallel = int(self.parallel_var.get())
            cache_ram = int(self.cache_ram_var.get())
            if context < 1024:
                raise ValueError("Context size must be at least 1024.")
            if not 1 <= port <= 65535:
                raise ValueError("Port must be between 1 and 65535.")
            if not 1 <= parallel <= 16:
                raise ValueError("Parallel slots must be between 1 and 16.")
            if cache_ram < 0:
                raise ValueError("Prompt cache RAM must be 0 or greater.")
        except ValueError as exc:
            if show_message:
                messagebox.showerror("Invalid setting", str(exc))
            raise
        self.settings.backend = self.backend_var.get()
        self.settings.context_size = context
        self.settings.parallel_slots = parallel
        self.settings.prompt_cache_ram_mb = cache_ram
        self.settings.gpu_layers = self.gpu_var.get().strip() or "auto"
        self.settings.flash_attention = self.flash_var.get()
        self.settings.reasoning = self.reasoning_var.get()
        self.settings.host = self.host_var.get().strip() or "0.0.0.0"
        self.settings.port = port
        self.settings.server_path = self.server_path_var.get().strip()
        self.settings.start_with_os = self.autostart_var.get()
        self.store.save(self.settings)
        try:
            set_autostart(self.settings.start_with_os)
        except Exception as exc:
            self._append_log(f"Autostart setting could not be applied: {exc}")
        self._refresh_status()
        if show_message:
            self._append_log("Advanced settings saved.")

    def toggle_server(self) -> None:
        if self.server.running:
            self.server.stop()
            self._refresh_status()
        else:
            self.start_server()

    def start_server(self) -> None:
        if self.server.running:
            return
        if self.model_var.get():
            self.settings.model_path = self.model_var.get()
        try:
            self.save_advanced(show_message=False)
        except ValueError as exc:
            messagebox.showerror("Cannot start backend", str(exc))
            return
        if not self.settings.server_path:
            found = find_server(Path(self.settings.runtime_dir))
            if found:
                self.settings.server_path = str(found)
                self.server_path_var.set(str(found))
        server_path = Path(self.settings.server_path) if self.settings.server_path else None
        runtime_matches = runtime_backend_matches(
            self.profile.system, self.settings.backend, self.settings.runtime_backend
        )
        if not server_path or not server_path.is_file() or not runtime_matches:
            backend_label = self.settings.backend.upper()
            reason = "not installed" if not server_path or not server_path.is_file() else "installed for a different backend"
            if messagebox.askyesno(
                "Install llama.cpp runtime",
                f"The llama.cpp runtime is {reason}. Install the {backend_label} runtime now?",
            ):
                self.install_llama(start_after=True)
            return
        if not port_is_available(self.settings.host, self.settings.port):
            messagebox.showerror(
                "Cannot start backend",
                f"Port {self.settings.port} is already in use.\n\n"
                "Tabletop Librarian Server uses port 8080 by default. "
                "Choose a different backend port under Advanced settings.",
            )
            return
        try:
            self.server.start(self.settings)
        except Exception as exc:
            messagebox.showerror("Cannot start backend", str(exc))
            return
        self.store.save(self.settings)
        self._append_log("Starting llama.cpp server…")
        self._refresh_status()

    def _refresh_status(self) -> None:
        if self.server.running:
            healthy = is_healthy(self.settings, timeout=0.25)
            self.status_var.set("Running" if healthy else "Starting…")
            self.start_button.configure(text="Stop Server")
        else:
            self.status_var.set("Stopped")
            self.start_button.configure(text="Start Server")
        found_runtime = find_server(Path(self.settings.runtime_dir))
        configured_runtime = Path(self.settings.server_path) if self.settings.server_path else None
        runtime = configured_runtime if configured_runtime and configured_runtime.is_file() else found_runtime
        if runtime and runtime_backend_matches(self.profile.system, self.settings.backend, self.settings.runtime_backend):
            shown_backend = self.settings.runtime_backend or self.settings.backend
            self.runtime_var.set(f"Installed ({shown_backend.upper()})")
            self.runtime_button.configure(text="Update Runtime", state="normal")
        elif runtime:
            shown_backend = self.settings.runtime_backend or "unknown"
            self.runtime_var.set(f"Installed for {shown_backend.upper()}; {self.settings.backend.upper()} required")
            self.runtime_button.configure(text="Install Runtime", state="normal")
        else:
            self.runtime_var.set(f"Not installed ({self.settings.backend.upper()})")
            self.runtime_button.configure(text="Install Runtime", state="normal")
        addresses = local_addresses(self.settings.port)
        self.address_var.set(next((x for x in addresses if "127.0.0.1" not in x), addresses[0]))
        self.root.after(1500, self._refresh_status)

    def _pump_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "download_progress":
                    done, total = payload  # type: ignore[misc]
                    if total:
                        percent = min(100.0, (done / total) * 100)
                        self.download_progress["value"] = percent
                        self.download_label.configure(text=f"{percent:.0f}%")
                    else:
                        self.download_progress["value"] = 0
                        self.download_label.configure(text=f"{done / (1024**2):.0f} MB")
                elif kind == "download_done":
                    path = Path(payload)  # type: ignore[arg-type]
                    self.settings.model_path = str(path)
                    selected = next((m for m in CATALOG if m.filename == path.name), None)
                    if selected:
                        self.settings.alias = selected.alias
                    self.store.save(self.settings)
                    self.download_progress["value"] = 100
                    self.download_label.configure(text="Complete")
                    self._refresh_models()
                    self._append_log(f"Model ready: {path.name}")
                elif kind == "server_exit":
                    code = int(payload)
                    if code != 0:
                        explanation = describe_process_exit(code, self.settings.backend)
                        self._append_log(f"llama.cpp exited unexpectedly with code {code}.")
                        if explanation:
                            self._append_log(explanation)
                            detail = explanation
                        else:
                            detail = (
                                f"llama.cpp stopped unexpectedly (exit code {code}).\n\n"
                                "Open Advanced to review the backend log. If the log is empty, "
                                "check/update the GPU driver because Windows may be failing before llama.cpp can initialize."
                            )
                        messagebox.showerror("TTL AI Backend", detail)
                    self._refresh_status()
                elif kind == "runtime_done":
                    server, actual_backend = payload  # type: ignore[misc]
                    self.settings.server_path = str(server)
                    self.settings.runtime_backend = str(actual_backend)
                    self.server_path_var.set(str(server))
                    if self.settings.backend == "cuda" and actual_backend == "vulkan":
                        self._append_log("Official Linux CUDA binaries are not currently published; installed Vulkan runtime as a portable fallback.")
                    self.store.save(self.settings)
                    self.download_progress["value"] = 100
                    self.download_label.configure(text="Runtime ready")
                    self.runtime_var.set(f"Installed ({actual_backend.upper()})")
                    self.runtime_button.configure(text="Update Runtime", state="normal")
                    self._append_log(f"llama.cpp ready: {server}")
                    if self.start_after_runtime_install:
                        self.start_after_runtime_install = False
                        self.root.after(100, self.start_server)
                elif kind == "error":
                    self.start_after_runtime_install = False
                    self.runtime_button.configure(state="normal")
                    self.download_label.configure(text="Error")
                    messagebox.showerror("TTL AI Backend", str(payload))
        except queue.Empty:
            pass
        self.root.after(150, self._pump_events)

    def _on_close(self) -> None:
        # Closing the manager does not leave an unmonitored child process behind.
        self.server.stop()
        self.store.save(self.settings)
        self.root.destroy()


def run(start_server: bool = False) -> None:
    root = tk.Tk()
    BackendManagerApp(root, start_server=start_server)
    root.mainloop()
