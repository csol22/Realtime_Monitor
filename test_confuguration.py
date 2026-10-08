import json
import math
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

if __package__:
	from .monitor_config import TEST_MODES
else:
	from monitor_config import TEST_MODES

Criteria = dict[str, dict[str, dict[str, float]]]
ChartSettings = dict[str, bool]
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
	}


def _validate_chart_settings(data: object) -> ChartSettings:
	if not isinstance(data, dict):
		raise ValueError("Chart settings JSON must contain an object.")
	defaults = default_chart_settings()
	settings: ChartSettings = {}
	for key, default in defaults.items():
		value = data.get(key, default)
		if not isinstance(value, bool):
			raise ValueError(f"Chart setting '{key}' must be true or false.")
		settings[key] = value
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
		self.window.geometry("560x360")
		self.window.minsize(480, 300)

		self.settings = settings
		self.on_save = on_save
		self.on_reload_criteria = on_reload_criteria

		is_dark = self.settings.get("dark_theme", False)
		bg = "#202020" if is_dark else "#f3f3f3"
		self.window.configure(background=bg)
		update_window_titlebar(self.window, is_dark)

		self.notebook = ttk.Notebook(self.window)
		self.notebook.pack(fill="both", expand=True, padx=10, pady=(10, 0))

		self.chart_style_tab = ttk.Frame(self.notebook, padding=14)
		self.notebook.add(self.chart_style_tab, text="Chart Style")
		self._build_chart_style_tab()

		self.ui_config_tab = ttk.Frame(self.notebook, padding=14)
		self.notebook.add(self.ui_config_tab, text="UI Configuration")
		self._build_ui_config_tab()

		actions = ttk.Frame(self.window, padding=(10, 8))
		actions.pack(fill="x")
		ttk.Button(actions, text="Save", command=self._save).pack(side="right", padx=(6, 0))
		ttk.Button(actions, text="Close", command=self.window.destroy).pack(side="right")

	def _build_chart_style_tab(self) -> None:
		self.chart_style_tab.columnconfigure(0, weight=1)
		ttk.Label(
			self.chart_style_tab,
			text="Choose which flow charts are displayed.",
		).grid(row=0, column=0, sticky="w", pady=(0, 12))

		self.show_primary_var = tk.BooleanVar(
			value=self.settings["show_primary_chart"]
		)
		self.show_secondary_var = tk.BooleanVar(
			value=self.settings["show_secondary_chart"]
		)
		self.center_curve_var = tk.BooleanVar(value=self.settings["center_latest_curve"])

		ttk.Checkbutton(
			self.chart_style_tab,
			text="Show Primary (FT61) flow chart",
			variable=self.show_primary_var,
		).grid(row=1, column=0, sticky="w", pady=4)
		ttk.Checkbutton(
			self.chart_style_tab,
			text="Show Secondary (FT01) flow chart",
			variable=self.show_secondary_var,
		).grid(row=2, column=0, sticky="w", pady=4)
		ttk.Checkbutton(
			self.chart_style_tab,
			text="Keep the latest curve centered horizontally",
			variable=self.center_curve_var,
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
			self.ui_config_tab, text="Theme / 界面主题", padding=14
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
			text="Light Theme / 白色主题 (Default)",
			variable=self.dark_theme_var,
			value=False,
		).grid(row=1, column=0, sticky="w", pady=6)

		ttk.Radiobutton(
			theme_frame,
			text="Dark Theme / 深色主题 (Windows Dark Style)",
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
		settings = {
			"show_primary_chart": self.show_primary_var.get(),
			"show_secondary_chart": self.show_secondary_var.get(),
			"center_latest_curve": self.center_curve_var.get(),
			"dark_theme": self.dark_theme_var.get(),
		}
		try:
			save_chart_settings(settings)
		except (OSError, ValueError) as error:
			messagebox.showerror("Could Not Save Settings", str(error), parent=self.window)
			return

		self.settings = settings
		is_dark = settings["dark_theme"]
		bg = "#202020" if is_dark else "#f3f3f3"
		self.window.configure(background=bg)
		update_window_titlebar(self.window, is_dark)

		self.on_save(settings)
		messagebox.showinfo("Settings Saved", "Settings have been saved.", parent=self.window)
