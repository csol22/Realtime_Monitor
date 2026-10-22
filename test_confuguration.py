import json
import math
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

if __package__:
    from .monitor_config import TEST_MODES
    from .overlay import OVERLAY_REGISTERS
else:
    from monitor_config import TEST_MODES
    from overlay import OVERLAY_REGISTERS

Criteria = dict[str, dict[str, dict[str, float]]]
ChartSettings = dict[str, Any]

CRITERIA_FILE = Path(__file__).with_name("passing_criteria.json")
SETTINGS_FILE = Path(__file__).with_name("monitor_settings.json")


def update_window_titlebar(window: tk.Misc, is_dark: bool) -> None:
    """Set title bar to exact window background color and proper caption buttons."""
    try:
        import ctypes

        window.update_idletasks()
        hwnd = (
            ctypes.windll.user32.GetAncestor(window.winfo_id(), 2)
            or ctypes.windll.user32.GetParent(window.winfo_id())
            or window.winfo_id()
        )
        if not hwnd:
            return

        dark_val = ctypes.c_int(1 if is_dark else 0)
        for attr in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(dark_val), ctypes.sizeof(dark_val)
            )

        # DWMWA_CAPTION_COLOR = 35 (Windows 11 build 22000+)
        # Match window background color: #202020 for dark, #F3F3F3 for light
        bg_ref = ctypes.c_int(0x00202020 if is_dark else 0x00F3F3F3)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 35, ctypes.byref(bg_ref), ctypes.sizeof(bg_ref)
        )

        # DWMWA_TEXT_COLOR = 36
        text_ref = ctypes.c_int(0x00FFFFFF if is_dark else 0x00111111)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 36, ctypes.byref(text_ref), ctypes.sizeof(text_ref)
        )
    except Exception:
        pass


def default_passing_criteria() -> Criteria:
    return {
        test_name: {
            "primary": {"min": 1000.0, "max": 1500.0},
            "secondary": {"min": 1000.0, "max": 1500.0},
        }
        for test_name in TEST_MODES
    }


def _validate_criteria(data: object) -> Criteria:
    if not isinstance(data, dict):
        raise ValueError("Passing criteria JSON must contain an object.")

    defaults = default_passing_criteria()
    input_modes = {str(name).strip().casefold(): values for name, values in data.items()}

    criteria: Criteria = {}
    for test_name, default in defaults.items():
        mode_data = input_modes.get(test_name.casefold(), default)
        if not isinstance(mode_data, dict):
            raise ValueError(f"Criteria for '{test_name}' must be an object.")

        criteria[test_name] = {}
        for flow_name in ("primary", "secondary"):
            flow_data = mode_data.get(flow_name, default[flow_name])
            if not isinstance(flow_data, dict):
                raise ValueError(f"{flow_name} criteria for '{test_name}' must be an object.")

            bounds: dict[str, float] = {}
            for bound in ("min", "max"):
                value = flow_data.get(bound, default[flow_name][bound])
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{test_name} {flow_name} {bound} must be a number.")
                if not math.isfinite(value):
                    raise ValueError(f"{test_name} {flow_name} {bound} must be finite.")
                bounds[bound] = float(value)

            if bounds["min"] > bounds["max"]:
                raise ValueError(f"{test_name} {flow_name} minimum cannot exceed maximum.")

            criteria[test_name][flow_name] = bounds

    return criteria


def load_passing_criteria() -> Criteria:
    if not CRITERIA_FILE.exists():
        return default_passing_criteria()

    try:
        data = json.loads(CRITERIA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not load passing criteria from {CRITERIA_FILE}: {error}") from error

    return _validate_criteria(data)


def default_chart_settings() -> ChartSettings:
    return {
        "show_primary_chart": True,
        "show_secondary_chart": True,
        "center_latest_curve": False,
        "dark_theme": False,
        "flow_poll_interval_ms": 50,
        "pump_poll_interval_ms": 1000,
        "contiguous_batch_read": True,
        "tcp_nodelay": True,
        "modbus_timeout_s": 1.0,
        "modbus_retries": 0,
        "modbus_slave_id": 1,
        "modbus_port": 502,
        "sync_chart_with_flow": True,
        "overlay_enabled": False,
        "overlay_registers": [address for address, _, _, _ in OVERLAY_REGISTERS],
    }


def _validate_chart_settings(data: object) -> ChartSettings:
    if not isinstance(data, dict):
        raise ValueError("Chart settings JSON must contain an object.")

    defaults = default_chart_settings()
    settings: ChartSettings = {}

    # Booleans
    for key in (
        "show_primary_chart",
        "show_secondary_chart",
        "center_latest_curve",
        "dark_theme",
        "contiguous_batch_read",
        "tcp_nodelay",
        "sync_chart_with_flow",
        "overlay_enabled",
    ):
        value = data.get(key, defaults[key])
        if not isinstance(value, bool):
            raise ValueError(f"Chart setting '{key}' must be true or false.")
        settings[key] = value

    raw_registers = data.get("overlay_registers", defaults["overlay_registers"])
    valid_registers = {address for address, _, _, _ in OVERLAY_REGISTERS}
    if not isinstance(raw_registers, list):
        raise ValueError("Chart setting 'overlay_registers' must be a list of addresses.")
    if any(
        isinstance(address, bool) or not isinstance(address, int) or address not in valid_registers
        for address in raw_registers
    ):
        raise ValueError("Overlay registers must contain valid addresses from 37 to 40.")
    if len(set(raw_registers)) != len(raw_registers):
        raise ValueError("Overlay registers cannot contain duplicate addresses.")
    settings["overlay_registers"] = list(raw_registers)

    # Integers
    int_ranges = {
        "flow_poll_interval_ms": (10, 10000),
        "pump_poll_interval_ms": (50, 60000),
        "modbus_retries": (0, 10),
        "modbus_slave_id": (1, 247),
        "modbus_port": (1, 65535),
    }

    for key, (min_val, max_val) in int_ranges.items():
        raw = data.get(key, defaults[key])
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"Chart setting '{key}' must be an integer.")
        val = int(raw)
        if not (min_val <= val <= max_val):
            raise ValueError(f"Chart setting '{key}' must be between {min_val} and {max_val}.")
        settings[key] = val

    # Timeout (float)
    raw_timeout = data.get("modbus_timeout_s", defaults["modbus_timeout_s"])
    if isinstance(raw_timeout, bool) or not isinstance(raw_timeout, (int, float)):
        raise ValueError("Chart setting 'modbus_timeout_s' must be a number.")
    timeout = float(raw_timeout)
    if not (0.05 <= timeout <= 30.0):
        raise ValueError("Chart setting 'modbus_timeout_s' must be between 0.05 and 30.0.")
    settings["modbus_timeout_s"] = timeout

    return settings


def load_chart_settings() -> ChartSettings:
    if not SETTINGS_FILE.exists():
        settings = default_chart_settings()
        save_chart_settings(settings)
        return settings

    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not load chart settings from {SETTINGS_FILE}: {error}") from error

    return _validate_chart_settings(data)


def save_chart_settings(settings: ChartSettings) -> None:
    validated = _validate_chart_settings(settings)
    SETTINGS_FILE.write_text(
        json.dumps(validated, indent=2) + "\n",
        encoding="utf-8",
    )


class AdvancedSettingsWindow:
    def __init__(
        self,
        parent: tk.Misc,
        settings: ChartSettings,
        on_save: Callable[[ChartSettings], None],
        on_reload_criteria: Callable[[], None],
    ) -> None:
        self.window = tk.Toplevel(parent)
        self.window.title("Advanced Settings")
        
        # FIX: Increased window height slightly so buttons fit perfectly
        self.window.geometry("600x580")
        self.window.minsize(540, 520)

        self.settings = settings
        self.on_save = on_save
        self.on_reload_criteria = on_reload_criteria

        self.is_dark = self.settings.get("dark_theme", False)
        bg = "#202020" if self.is_dark else "#f3f3f3"
        self.window.configure(background=bg)

        update_window_titlebar(self.window, self.is_dark)

        # FIX: Pack the actions frame FIRST with side="bottom" so it docks safely.
        actions = ttk.Frame(self.window, padding=(10, 8))
        actions.pack(side="bottom", fill="x")

        ttk.Button(actions, text="Save", command=self._save).pack(side="right", padx=(6, 0))
        ttk.Button(actions, text="Close", command=self.window.destroy).pack(side="right")

        # FIX: Pack notebook AFTER actions with side="top" so it takes the remaining space
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(side="top", fill="both", expand=True, padx=10, pady=(10, 0))

        self.modbus_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.modbus_tab, text="Modbus")
        self._build_modbus_tab()

        self.chart_style_tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(self.chart_style_tab, text="Chart Style")
        self._build_chart_style_tab()

        self.ui_config_tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(self.ui_config_tab, text="UI Configuration")
        self._build_ui_config_tab()

        self.overlay_tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(self.overlay_tab, text="Overlay")
        self._build_overlay_tab()

    def _build_overlay_tab(self) -> None:
        self.overlay_tab.columnconfigure(0, weight=1)

        self.overlay_enabled_var = tk.BooleanVar(
            value=self.settings.get("overlay_enabled", False)
        )
        ttk.Checkbutton(
            self.overlay_tab,
            text="Enable always-on-top overlay (top-right corner)",
            variable=self.overlay_enabled_var,
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        ttk.Label(
            self.overlay_tab,
            text="Select the live Modbus registers to show. Select a row and use the arrows to change its display order.",
            wraplength=500,
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))

        table_frame = ttk.Frame(self.overlay_tab)
        table_frame.grid(row=2, column=0, sticky="ew")
        self.overlay_tree = ttk.Treeview(
            table_frame,
            columns=("include", "address", "name"),
            show="headings",
            height=len(OVERLAY_REGISTERS),
            selectmode="browse",
        )
        self.overlay_tree.heading("include", text="Show")
        self.overlay_tree.heading("address", text="Address")
        self.overlay_tree.heading("name", text="Register")
        self.overlay_tree.column("include", width=70, anchor="center", stretch=False)
        self.overlay_tree.column("address", width=90, anchor="center", stretch=False)
        self.overlay_tree.column("name", width=180, anchor="w")
        self.overlay_tree.grid(row=0, column=0, sticky="ew")
        table_frame.columnconfigure(0, weight=1)
        self.overlay_tree.bind("<Button-1>", self._toggle_overlay_row)

        controls = ttk.Frame(self.overlay_tab)
        controls.grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Button(
            controls, text="Toggle selection", command=self._toggle_selected_overlay_row
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            controls, text="Move up", command=lambda: self._move_overlay_row(-1)
        ).pack(side="left", padx=3)
        ttk.Button(
            controls, text="Move down", command=lambda: self._move_overlay_row(1)
        ).pack(side="left", padx=3)

        selected = self.settings.get(
            "overlay_registers",
            [address for address, _, _, _ in OVERLAY_REGISTERS],
        )
        ordered = list(selected) + [
            address for address, _, _, _ in OVERLAY_REGISTERS if address not in selected
        ]
        names = {address: name for address, name, _, _ in OVERLAY_REGISTERS}
        for address in ordered:
            self.overlay_tree.insert(
                "",
                "end",
                iid=str(address),
                values=("☑" if address in selected else "☐", address, names[address]),
            )

    def _toggle_overlay_row(self, event: tk.Event) -> str | None:
        row = self.overlay_tree.identify_row(event.y)
        column = self.overlay_tree.identify_column(event.x)
        if row and column == "#1":
            self.overlay_tree.selection_set(row)
            self._toggle_overlay_item(row)
            return "break"
        return None

    def _toggle_selected_overlay_row(self) -> None:
        selection = self.overlay_tree.selection()
        if selection:
            self._toggle_overlay_item(selection[0])

    def _toggle_overlay_item(self, item: str) -> None:
        values = list(self.overlay_tree.item(item, "values"))
        values[0] = "☐" if values[0] == "☑" else "☑"
        self.overlay_tree.item(item, values=values)

    def _move_overlay_row(self, offset: int) -> None:
        selection = self.overlay_tree.selection()
        if not selection:
            return
        item = selection[0]
        items = self.overlay_tree.get_children("")
        target = items.index(item) + offset
        if 0 <= target < len(items):
            self.overlay_tree.move(item, "", target)
            self.overlay_tree.selection_set(item)

    def _build_modbus_tab(self) -> None:
        self.modbus_tab.columnconfigure(0, weight=1)

        # --- Scan Rates ---
        scan_frame = ttk.LabelFrame(self.modbus_tab, text="Register Scan Rates", padding=10)
        scan_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        scan_frame.columnconfigure(1, weight=1)

        ttk.Label(scan_frame, text="Flow meter registers (FT01/FT61 - 37/38):").grid(row=0, column=0, sticky="w", pady=3)
        self.flow_interval_var = tk.StringVar(
            value=f"{self.settings.get('flow_poll_interval_ms', 50)} ms"
        )
        flow_cb = ttk.Combobox(
            scan_frame, textvariable=self.flow_interval_var,
            values=["20 ms", "50 ms", "100 ms", "200 ms", "500 ms", "1000 ms"], width=12,
        )
        flow_cb.grid(row=0, column=1, sticky="w", padx=(10, 0), pady=3)

        ttk.Label(scan_frame, text="Pump / other registers (P31/P41 - 39/40):").grid(row=1, column=0, sticky="w", pady=3)
        self.pump_interval_var = tk.StringVar(
            value=f"{self.settings.get('pump_poll_interval_ms', 1000)} ms"
        )
        pump_cb = ttk.Combobox(
            scan_frame, textvariable=self.pump_interval_var,
            values=["200 ms", "500 ms", "1000 ms", "2000 ms", "5000 ms"], width=12,
        )
        pump_cb.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=3)

        muted_fg = "#888888" if self.is_dark else "#555555"
        ttk.Label(
            scan_frame,
            text="Tip: 50 ms for flow keeps the chart smooth; 1000 ms for pump/other reduces bus load significantly.",
            font=("Segoe UI", 8), foreground=muted_fg,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # --- Optimization & Sync ---
        opt_frame = ttk.LabelFrame(self.modbus_tab, text="Optimization & Sync", padding=10)
        opt_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        opt_frame.columnconfigure(0, weight=1)

        self.sync_chart_var = tk.BooleanVar(value=self.settings.get("sync_chart_with_flow", True))
        ttk.Checkbutton(
            opt_frame, text="Lockstep UI Refresh (sync chart and value display on every sample)",
            variable=self.sync_chart_var,
        ).grid(row=0, column=0, sticky="w", pady=1)
        ttk.Label(
            opt_frame, text="Redraws the chart and numeric values in the same frame as each incoming sample, eliminating visible lag.",
            font=("Segoe UI", 8), foreground=muted_fg, wraplength=480,
        ).grid(row=1, column=0, sticky="w", padx=(20, 0), pady=(0, 4))

        self.contiguous_batch_var = tk.BooleanVar(value=self.settings.get("contiguous_batch_read", True))
        ttk.Checkbutton(
            opt_frame, text="Contiguous Batch Read (merge registers 37-40 into one request)",
            variable=self.contiguous_batch_var,
        ).grid(row=2, column=0, sticky="w", pady=1)
        ttk.Label(
            opt_frame, text="When flow and pump share the same scan tick, reads all four registers in a single Modbus request, halving RTT.",
            font=("Segoe UI", 8), foreground=muted_fg, wraplength=480,
        ).grid(row=3, column=0, sticky="w", padx=(20, 0), pady=(0, 4))

        self.tcp_nodelay_var = tk.BooleanVar(value=self.settings.get("tcp_nodelay", True))
        ttk.Checkbutton(
            opt_frame, text="Enable TCP_NODELAY (low-latency socket mode)", variable=self.tcp_nodelay_var,
        ).grid(row=4, column=0, sticky="w", pady=1)
        ttk.Label(
            opt_frame, text="Disables Nagle's algorithm so small Modbus packets are sent immediately, critical for 50 ms polling.",
            font=("Segoe UI", 8), foreground=muted_fg, wraplength=480,
        ).grid(row=5, column=0, sticky="w", padx=(20, 0), pady=(0, 2))

        # --- Connection Parameters ---
        comm_frame = ttk.LabelFrame(self.modbus_tab, text="Connection Parameters", padding=10)
        comm_frame.grid(row=2, column=0, sticky="ew")
        comm_frame.columnconfigure(1, weight=1)
        comm_frame.columnconfigure(3, weight=1)

        ttk.Label(comm_frame, text="Timeout:").grid(row=0, column=0, sticky="w", pady=3)
        self.timeout_var = tk.StringVar(value=f"{self.settings.get('modbus_timeout_s', 1.0)} s")
        ttk.Combobox(
            comm_frame, textvariable=self.timeout_var,
            values=["0.2 s", "0.5 s", "1.0 s", "1.5 s", "2.0 s"], width=8,
        ).grid(row=0, column=1, sticky="w", padx=(6, 14), pady=3)

        ttk.Label(comm_frame, text="Retries:").grid(row=0, column=2, sticky="w", pady=3)
        self.retries_var = tk.StringVar(value=str(self.settings.get("modbus_retries", 0)))
        ttk.Combobox(
            comm_frame, textvariable=self.retries_var,
            values=["0", "1", "2", "3"], width=6,
        ).grid(row=0, column=3, sticky="w", padx=(6, 0), pady=3)

        ttk.Label(comm_frame, text="Slave ID:").grid(row=1, column=0, sticky="w", pady=3)
        self.slave_id_entry = ttk.Entry(comm_frame, width=8)
        self.slave_id_entry.insert(0, str(self.settings.get("modbus_slave_id", 1)))
        self.slave_id_entry.grid(row=1, column=1, sticky="w", padx=(6, 14), pady=3)

        ttk.Label(comm_frame, text="Port:").grid(row=1, column=2, sticky="w", pady=3)
        self.port_entry = ttk.Entry(comm_frame, width=8)
        self.port_entry.insert(0, str(self.settings.get("modbus_port", 502)))
        self.port_entry.grid(row=1, column=3, sticky="w", padx=(6, 0), pady=3)

    def _build_chart_style_tab(self) -> None:
        self.chart_style_tab.columnconfigure(0, weight=1)

        ttk.Label(
            self.chart_style_tab, text="Choose which flow charts are displayed.",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        self.show_primary_var = tk.BooleanVar(
            value=self.settings["show_primary_chart"]
        )
        self.show_secondary_var = tk.BooleanVar(
            value=self.settings["show_secondary_chart"]
        )
        self.center_curve_var = tk.BooleanVar(value=self.settings["center_latest_curve"])

        ttk.Checkbutton(
            self.chart_style_tab, text="Show Primary (FT61) flow chart", variable=self.show_primary_var,
        ).grid(row=1, column=0, sticky="w", pady=4)

        ttk.Checkbutton(
            self.chart_style_tab, text="Show Secondary (FT01) flow chart", variable=self.show_secondary_var,
        ).grid(row=2, column=0, sticky="w", pady=4)

        ttk.Checkbutton(
            self.chart_style_tab, text="Keep the latest curve centered horizontally", variable=self.center_curve_var,
        ).grid(row=3, column=0, sticky="w", pady=4)

        criteria_frame = ttk.LabelFrame(
            self.chart_style_tab, text="Passing Criteria (JSON)", padding=10
        )
        criteria_frame.grid(row=4, column=0, sticky="ew", pady=(16, 4))
        criteria_frame.columnconfigure(0, weight=1)

        ttk.Label(
            criteria_frame,
            text="Edit passing_criteria.json directly, then reload it without restarting.",
            wraplength=470,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        ttk.Button(
            criteria_frame, text="Open JSON", command=self._open_criteria_json
        ).grid(row=1, column=0, sticky="w")
        ttk.Button(
            criteria_frame, text="Reload JSON", command=self.on_reload_criteria
        ).grid(row=1, column=1, sticky="e")

    def _build_ui_config_tab(self) -> None:
        self.ui_config_tab.columnconfigure(0, weight=1)

        theme_frame = ttk.LabelFrame(
            self.ui_config_tab, text="Theme", padding=14
        )
        theme_frame.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        theme_frame.columnconfigure(0, weight=1)

        ttk.Label(
            theme_frame,
            text="Choose the user interface appearance:",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.dark_theme_var = tk.BooleanVar(
            value=self.settings.get("dark_theme", False)
        )

        ttk.Radiobutton(
            theme_frame,
            text="Light Theme (Default)",
            variable=self.dark_theme_var,
            value=False,
        ).grid(row=1, column=0, sticky="w", pady=6)

        ttk.Radiobutton(
            theme_frame,
            text="Dark Theme (Windows Dark Style)",
            variable=self.dark_theme_var,
            value=True,
        ).grid(row=2, column=0, sticky="w", pady=6)

    def _open_criteria_json(self) -> None:
        try:
            if not CRITERIA_FILE.exists():
                CRITERIA_FILE.write_text(
                    json.dumps(default_passing_criteria(), indent=2) + "\n",
                    encoding="utf-8",
                )
            subprocess.Popen(["notepad.exe", str(CRITERIA_FILE)])
        except OSError as error:
            messagebox.showerror("Could Not Open JSON", str(error), parent=self.window)

    def _save(self) -> None:
        try:
            flow_ms = int(self.flow_interval_var.get().replace("ms", "").strip())
            if not (10 <= flow_ms <= 10000):
                raise ValueError("Flow scan interval must be between 10 and 10000 ms.")
        except ValueError as err:
            messagebox.showerror("Invalid Input", f"Flow scan interval: {err}", parent=self.window)
            return

        try:
            pump_ms = int(self.pump_interval_var.get().replace("ms", "").strip())
            if not (50 <= pump_ms <= 60000):
                raise ValueError("Pump/other scan interval must be between 50 and 60000 ms.")
        except ValueError as err:
            messagebox.showerror("Invalid Input", f"Pump/other scan interval: {err}", parent=self.window)
            return

        try:
            timeout_s = float(self.timeout_var.get().replace("s", "").strip())
            if not (0.05 <= timeout_s <= 30.0):
                raise ValueError("Timeout must be between 0.05 and 30.0 s.")
        except ValueError as err:
            messagebox.showerror("Invalid Input", f"Timeout: {err}", parent=self.window)
            return

        try:
            retries = int(self.retries_var.get().strip().split()[0])
            if not (0 <= retries <= 10):
                raise ValueError("Retries must be between 0 and 10.")
        except ValueError as err:
            messagebox.showerror("Invalid Input", f"Retries: {err}", parent=self.window)
            return

        try:
            slave_id = int(self.slave_id_entry.get().strip())
            if not (1 <= slave_id <= 247):
                raise ValueError("Slave ID must be between 1 and 247.")
        except ValueError as err:
            messagebox.showerror("Invalid Input", f"Slave ID: {err}", parent=self.window)
            return

        try:
            port = int(self.port_entry.get().strip())
            if not (1 <= port <= 65535):
                raise ValueError("Port must be between 1 and 65535.")
        except ValueError as err:
            messagebox.showerror("Invalid Input", f"Port: {err}", parent=self.window)
            return

        settings = {
            "show_primary_chart": self.show_primary_var.get(),
            "show_secondary_chart": self.show_secondary_var.get(),
            "center_latest_curve": self.center_curve_var.get(),
            "dark_theme": self.dark_theme_var.get(),
            "flow_poll_interval_ms": flow_ms,
            "pump_poll_interval_ms": pump_ms,
            "contiguous_batch_read": self.contiguous_batch_var.get(),
            "tcp_nodelay": self.tcp_nodelay_var.get(),
            "sync_chart_with_flow": self.sync_chart_var.get(),
            "modbus_timeout_s": timeout_s,
            "modbus_retries": retries,
            "modbus_slave_id": slave_id,
            "modbus_port": port,
            "overlay_enabled": self.overlay_enabled_var.get(),
            "overlay_registers": [
                int(item)
                for item in self.overlay_tree.get_children("")
                if self.overlay_tree.item(item, "values")[0] == "☑"
            ],
        }

        try:
            save_chart_settings(settings)
        except (OSError, ValueError) as error:
            messagebox.showerror("Could Not Save Settings", str(error), parent=self.window)
            return

        self.settings = settings
        self.is_dark = settings["dark_theme"]
        bg = "#202020" if self.is_dark else "#f3f3f3"
        self.window.configure(background=bg)
        update_window_titlebar(self.window, self.is_dark)

        self.on_save(settings)
        messagebox.showinfo("Settings Saved", "Settings have been saved.", parent=self.window)