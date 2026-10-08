import sys
import threading
import time
import tkinter as tk
from collections import deque
from tkinter import messagebox, ttk

if __package__:
	from .chart_view import FlowChart
	from .models import FlowSample
	from .modbus_core import ModbusCore
	from .monitor_config import (
		DEFAULT_REFRESH_MS,
		HISTORY_LIMIT,
		REFRESH_INTERVALS,
		TEST_MODES,
	)
	from .network_utils import get_default_modbus_ip
	from .preview_client import PreviewClient
	from .test_confuguration import (
		ChartSettings,
		Criteria,
		AdvancedSettingsWindow,
		load_chart_settings,
		load_passing_criteria,
		update_window_titlebar,
	)
else:
	from chart_view import FlowChart
	from models import FlowSample
	from modbus_core import ModbusCore
	from monitor_config import (
		DEFAULT_REFRESH_MS,
		HISTORY_LIMIT,
		REFRESH_INTERVALS,
		TEST_MODES,
	)
	from network_utils import get_default_modbus_ip
	from preview_client import PreviewClient
	from test_confuguration import (
		ChartSettings,
		Criteria,
		AdvancedSettingsWindow,
		load_chart_settings,
		load_passing_criteria,
		update_window_titlebar,
	)


def apply_theme(root: tk.Tk, is_dark: bool) -> None:
	"""Apply modern Windows-inspired theme (Light by default, or Dark) with unified titlebar."""
	if is_dark:
		bg = "#202020"
		panel_bg = "#292929"
		input_bg = "#2d2d2d"
		text_primary = "#f3f3f3"
		border_color = "#3d3d3d"
		accent = "#0078d4"
	else:
		bg = "#f3f3f3"
		panel_bg = "#ffffff"
		input_bg = "#ffffff"
		text_primary = "#1f2937"
		border_color = "#d1d5db"
		accent = "#0078d4"

	root.configure(background=bg)
	style = ttk.Style(root)
	style.theme_use("clam")

	style.configure(".", background=bg, foreground=text_primary, font=("Segoe UI", 9))
	style.configure("TFrame", background=bg)
	style.configure("TLabelframe", background=bg, foreground=text_primary, bordercolor=border_color)
	style.configure("TLabelframe.Label", background=bg, foreground=text_primary, font=("Segoe UI", 9, "bold"))
	style.configure("TLabel", background=bg, foreground=text_primary)

	style.configure(
		"TButton",
		background=panel_bg,
		foreground=text_primary,
		bordercolor=border_color,
		lightcolor=border_color,
		darkcolor=border_color,
		focuscolor="none",
		padding=(6, 2),
	)
	style.map(
		"TButton",
		background=[
			("pressed", "#1c1c1c" if is_dark else "#e5e7eb"),
			("active", "#383838" if is_dark else "#f3f4f6"),
			("disabled", "#252525" if is_dark else "#e5e7eb"),
		],
		foreground=[
			("disabled", "#666666" if is_dark else "#9ca3af"),
			("active", "#ffffff" if is_dark else "#111827"),
		],
	)

	style.configure(
		"TCombobox",
		fieldbackground=input_bg,
		background=panel_bg,
		foreground=text_primary,
		selectbackground=accent,
		selectforeground="#ffffff",
		bordercolor=border_color,
		arrowcolor=text_primary,
		padding=2,
	)
	style.map(
		"TCombobox",
		fieldbackground=[
			("readonly", input_bg),
			("active", "#353535" if is_dark else "#f9fafb"),
		],
		selectbackground=[("readonly", accent)],
		foreground=[("readonly", text_primary)],
	)

	style.configure(
		"TEntry",
		fieldbackground=input_bg,
		foreground=text_primary,
		bordercolor=border_color,
		insertcolor=text_primary,
		padding=2,
	)

	style.configure(
		"TNotebook",
		background=bg,
		bordercolor=border_color,
	)
	style.configure(
		"TNotebook.Tab",
		background=panel_bg,
		foreground=text_primary,
		padding=(10, 4),
		bordercolor=border_color,
	)
	style.map(
		"TNotebook.Tab",
		background=[("selected", bg)],
		foreground=[("selected", text_primary)],
	)

	style.configure("TRadiobutton", background=bg, foreground=text_primary)
	style.configure("TCheckbutton", background=bg, foreground=text_primary)

	update_window_titlebar(root, is_dark)


class RealtimeFlowMonitor:
	def __init__(
		self,
		root: tk.Tk,
		client=None,
		criteria: Criteria | None = None,
		chart_settings: ChartSettings | None = None,
	) -> None:
		self.root = root
		self.modbus = ModbusCore(client)
		self.stop_event = threading.Event()
		self.refresh_ms = DEFAULT_REFRESH_MS
		self.samples: deque[FlowSample] = deque(maxlen=HISTORY_LIMIT)
		self.criteria = criteria if criteria is not None else load_passing_criteria()
		self.chart_settings = (
			chart_settings if chart_settings is not None else load_chart_settings()
		)
		self.is_dark = self.chart_settings.get("dark_theme", False)
		self.settings_window: AdvancedSettingsWindow | None = None
		self.default_ip = get_default_modbus_ip()
		self.start_time: float | None = None

		root.title("CHx2000 Realtime Flow Monitor")
		root.minsize(700, 320)
		root.geometry("860x440")
		root.protocol("WM_DELETE_WINDOW", self.close)

		apply_theme(root, self.is_dark)

		self._build_ui()
		self._start_worker()
		self.root.after(200, self._redraw_chart)

	def _status_color(self, status: str) -> str:
		if status == "connected":
			return "#3fb950" if self.is_dark else "#16a34a"
		if status in ("offline", "failed", "error"):
			return "#f85149" if self.is_dark else "#dc2626"
		return "#8e8e8e" if self.is_dark else "#6b7280"

	def _build_ui(self) -> None:
		connection_frame = ttk.LabelFrame(self.root, text="Modbus TCP", padding=6)
		connection_frame.pack(fill="x", padx=8, pady=(6, 3))

		ttk.Label(connection_frame, text="IP:").pack(side="left", padx=(0, 4))
		self.ip_entry = ttk.Entry(connection_frame, width=16)
		self.ip_entry.insert(0, self.default_ip)
		self.ip_entry.pack(side="left", padx=4)
		self.connect_button = ttk.Button(connection_frame, text="Connect", command=self.connect)
		self.connect_button.pack(side="left", padx=4)
		ttk.Button(connection_frame, text="Obtain IP Address", command=self.obtain_ip_address).pack(
			side="left", padx=4
		)
		ttk.Label(connection_frame, text="Refresh:").pack(side="left", padx=(14, 4))
		self.refresh_selector = ttk.Combobox(
			connection_frame,
			width=8,
			state="readonly",
			values=[f"{interval} ms" for interval in REFRESH_INTERVALS],
		)
		self.refresh_selector.set(f"{DEFAULT_REFRESH_MS} ms")
		self.refresh_selector.bind("<<ComboboxSelected>>", self._refresh_interval_changed)
		self.refresh_selector.pack(side="left", padx=4)
		ttk.Button(connection_frame, text="Settings", command=self.open_settings).pack(
			side="left", padx=4
		)
		self.connection_status = ttk.Label(
			connection_frame, text="Offline", foreground=self._status_color("offline")
		)
		self.connection_status.pack(side="left", padx=12)

		criteria_frame = ttk.LabelFrame(self.root, text="Test Mode Selection", padding=6)
		criteria_frame.pack(fill="x", padx=8, pady=3)
		ttk.Label(criteria_frame, text="Select Test Mode:").pack(side="left", padx=(0, 4))
		self.test_selector = ttk.Combobox(
			criteria_frame,
			width=35,
			state="readonly",
			values=TEST_MODES,
		)
		self.test_selector.set(TEST_MODES[0])
		self.test_selector.bind("<<ComboboxSelected>>", self._on_test_selected)
		self.test_selector.pack(side="left", padx=4)

		values_frame = ttk.Frame(self.root, padding=(10, 4))
		values_frame.pack(fill="x")
		self.primary_value = ttk.Label(
			values_frame, text="Primary (FT61): -- g/m", font=("Segoe UI", 11, "bold")
		)
		self.primary_value.pack(side="left", padx=(0, 24))
		self.secondary_value = ttk.Label(
			values_frame, text="Secondary (FT01): -- g/m", font=("Segoe UI", 11, "bold")
		)
		self.secondary_value.pack(side="left", padx=(0, 24))
		self.pump_value = ttk.Label(
			values_frame, text="P31: --%   P41: --%", font=("Segoe UI", 10)
		)
		self.pump_value.pack(side="left")

		chart_frame = ttk.Frame(self.root, padding=(6, 2, 6, 6))
		self.chart_area = chart_frame
		self.chart_area.columnconfigure(0, weight=1)
		self.chart_area.columnconfigure(1, weight=1)
		self.chart_area.rowconfigure(0, weight=1)

		primary_curve_color = "#38bdf8" if self.is_dark else "#0284c7"
		secondary_curve_color = "#fb923c" if self.is_dark else "#d97706"

		self.primary_chart = FlowChart(
			self.chart_area,
			"Primary Flow (FT61)",
			"primary_flow",
			primary_curve_color,
			(),
			is_dark=self.is_dark,
		)
		self.secondary_chart = FlowChart(
			self.chart_area,
			"Secondary Flow (FT01)",
			"secondary_flow",
			secondary_curve_color,
			(4, 2),
			is_dark=self.is_dark,
		)
		self._apply_chart_settings()

	def _on_test_selected(self, _event=None) -> None:
		if self.samples:
			self._accept_sample(self.samples[-1])

	def open_settings(self) -> None:
		if self.settings_window is not None:
			try:
				if self.settings_window.window.winfo_exists():
					self.settings_window.window.lift()
					return
			except tk.TclError:
				pass
		self.settings_window = AdvancedSettingsWindow(
			self.root,
			self.chart_settings,
			self._chart_settings_updated,
			self._reload_passing_criteria,
		)

	def _chart_settings_updated(self, settings: ChartSettings) -> None:
		self.chart_settings = settings
		self.is_dark = settings.get("dark_theme", False)
		apply_theme(self.root, self.is_dark)

		primary_curve_color = "#38bdf8" if self.is_dark else "#0284c7"
		secondary_curve_color = "#fb923c" if self.is_dark else "#d97706"
		self.primary_chart.color = primary_curve_color
		self.secondary_chart.color = secondary_curve_color

		self.primary_chart.set_theme(self.is_dark)
		self.secondary_chart.set_theme(self.is_dark)
		self._apply_chart_settings()
		if self.samples:
			self._accept_sample(self.samples[-1])

	def _apply_chart_settings(self) -> None:
		self.primary_chart.frame.grid_remove()
		self.secondary_chart.frame.grid_remove()
		visible_charts = []
		if self.chart_settings["show_primary_chart"]:
			visible_charts.append(self.primary_chart)
		if self.chart_settings["show_secondary_chart"]:
			visible_charts.append(self.secondary_chart)

		for column, chart in enumerate(visible_charts):
			chart.frame.grid(row=0, column=column, sticky="nsew", padx=4, pady=2)

		if visible_charts:
			if not self.chart_area.winfo_manager():
				self.chart_area.pack(fill="both", expand=True)
			self.root.minsize(700, 320)
		else:
			self.chart_area.pack_forget()
			self.root.minsize(700, 180)

	def _reload_passing_criteria(self) -> None:
		try:
			criteria = load_passing_criteria()
		except (OSError, ValueError) as error:
			messagebox.showerror(
				"Passing Criteria Error", str(error), parent=self.settings_window.window
			)
			return

		self.criteria = criteria
		if self.samples:
			self._accept_sample(self.samples[-1])

	def _refresh_interval_changed(self, _event) -> None:
		del _event
		self.refresh_ms = int(self.refresh_selector.get().split()[0])

	def obtain_ip_address(self) -> None:
		self.default_ip = get_default_modbus_ip()
		self.ip_entry.delete(0, "end")
		self.ip_entry.insert(0, self.default_ip)

	def connect(self) -> None:
		if not self.modbus.available:
			messagebox.showerror("Missing dependency", "Install pymodbus before connecting.")
			return
		ip_address = self.ip_entry.get().strip()
		if not ip_address:
			self.connection_status.config(
				text="Enter an IP address", foreground=self._status_color("error")
			)
			return
		self.connect_button.config(state="disabled")
		self.connection_status.config(text="Connecting...", foreground=self._status_color("pending"))
		threading.Thread(
			target=self._connect_in_background, args=(ip_address,), daemon=True
		).start()

	def _connect_in_background(self, ip_address: str) -> None:
		try:
			self.modbus.connect(ip_address)
			self.root.after(0, self._connected, ip_address)
		except Exception as error:
			self.root.after(0, self._connection_failed, str(error))

	def _connected(self, ip_address: str) -> None:
		self.start_time = time.time()
		self.samples.clear()
		self.connect_button.config(text="Disconnect", command=self.disconnect, state="normal")
		self.connection_status.config(
			text=f"Connected to {ip_address}", foreground=self._status_color("connected")
		)

	def _connection_failed(self, error: str) -> None:
		self.connect_button.config(text="Connect", command=self.connect, state="normal")
		self.connection_status.config(
			text=f"Connection failed: {error}", foreground=self._status_color("failed")
		)

	def disconnect(self) -> None:
		self.connect_button.config(state="disabled")
		self.connection_status.config(text="Disconnecting...", foreground=self._status_color("pending"))
		threading.Thread(target=self._disconnect_in_background, daemon=True).start()

	def _disconnect_in_background(self) -> None:
		try:
			self.modbus.disconnect()
			self.root.after(0, self._disconnected)
		except Exception as error:
			self.root.after(0, self._disconnection_failed, str(error))

	def _disconnected(self) -> None:
		self.connect_button.config(text="Connect", command=self.connect, state="normal")
		self.connection_status.config(text="Disconnected", foreground=self._status_color("disconnected"))

	def _disconnection_failed(self, error: str) -> None:
		self.connect_button.config(text="Connect", command=self.connect, state="normal")
		self.connection_status.config(
			text=f"Disconnection failed: {error}", foreground=self._status_color("failed")
		)

	def _start_worker(self) -> None:
		threading.Thread(target=self._poll_loop, daemon=True).start()

	def _poll_loop(self) -> None:
		while not self.stop_event.is_set():
			t_start = time.perf_counter()
			try:
				sample = self.modbus.read_sample(self.start_time)
				if sample is not None:
					self.root.after(0, self._accept_sample, sample)
					self.root.after(
						0,
						self.connection_status.config,
						{"text": "Connected", "foreground": self._status_color("connected")},
					)
				else:
					self.root.after(
						0,
						self.connection_status.config,
						{"text": "Offline", "foreground": self._status_color("offline")},
					)
			except Exception as error:
				self.root.after(
					0,
					self.connection_status.config,
					{"text": f"Modbus error: {error}", "foreground": self._status_color("error")},
				)

			target_s = self.refresh_ms / 1000.0
			elapsed = time.perf_counter() - t_start
			sleep_time = max(0.001, target_s - elapsed)
			self.stop_event.wait(sleep_time)

	def _accept_sample(self, sample: FlowSample) -> None:
		self.samples.append(sample)
		self.primary_value.config(text=f"Primary (FT61): {sample.primary_flow:.1f} g/m")
		self.secondary_value.config(text=f"Secondary (FT01): {sample.secondary_flow:.1f} g/m")
		self.pump_value.config(
			text=f"P31: {sample.pump31_speed:.1f}%   P41: {sample.pump41_speed:.1f}%"
		)

		test_name = self.test_selector.get()
		mode_criteria = self.criteria[test_name]
		self.primary_value.config(
			foreground=self._flow_color(
				sample.primary_flow,
				mode_criteria["primary"]["min"],
				mode_criteria["primary"]["max"],
			)
		)
		self.secondary_value.config(
			foreground=self._flow_color(
				sample.secondary_flow,
				mode_criteria["secondary"]["min"],
				mode_criteria["secondary"]["max"],
			)
		)

	def _flow_color(self, flow: float, min_flow: float, max_flow: float) -> str:
		if self.is_dark:
			return "#3fb950" if min_flow <= flow <= max_flow else "#f85149"
		return "#16a34a" if min_flow <= flow <= max_flow else "#dc2626"

	def _redraw_chart(self) -> None:
		if self.stop_event.is_set():
			return
		samples = list(self.samples)
		test_name = self.test_selector.get()
		center_curve = self.chart_settings["center_latest_curve"]
		redraw_results = []
		if self.chart_settings["show_primary_chart"]:
			redraw_results.append(
				self.primary_chart.redraw(
					samples, test_name, self.criteria, center_curve
				)
			)
		if self.chart_settings["show_secondary_chart"]:
			redraw_results.append(
				self.secondary_chart.redraw(
					samples, test_name, self.criteria, center_curve
				)
			)

		redraw_interval = min(100, max(40, self.refresh_ms))
		if redraw_results and not all(redraw_results):
			self.root.after(max(30, redraw_interval // 2), self._redraw_chart)
			return
		self.root.after(redraw_interval, self._redraw_chart)

	def close(self) -> None:
		self.stop_event.set()
		self.modbus.disconnect()
		self.root.destroy()


def main() -> None:
	root = tk.Tk()
	try:
		criteria = load_passing_criteria()
		chart_settings = load_chart_settings()
	except (OSError, ValueError) as error:
		messagebox.showerror("Configuration Error", str(error), parent=root)
		root.destroy()
		return
	client = PreviewClient() if "--preview" in sys.argv else None
	monitor = RealtimeFlowMonitor(root, client, criteria, chart_settings)
	if client is not None:
		monitor._connected("Preview")
	root.mainloop()


if __name__ == "__main__":
	main()
	