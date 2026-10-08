import tkinter as tk
from collections.abc import Callable

if __package__:
	from .models import FlowSample
	from .monitor_config import MAX_FLOW, TIME_WINDOW_SECONDS
else:
	from models import FlowSample
	from monitor_config import MAX_FLOW, TIME_WINDOW_SECONDS

Criteria = dict[str, dict[str, dict[str, float]]]


class FlowChart:
	def __init__(
		self,
		parent: tk.Misc,
		title: str,
		flow_name: str,
		color: str,
		dash: tuple[int, ...],
		is_dark: bool = False,
	) -> None:
		self.title = title
		self.flow_name = flow_name
		self.criteria_name = flow_name.removesuffix("_flow")
		self.color = color
		self.dash = dash
		self.is_dark = is_dark

		self.frame = tk.Frame(parent, highlightthickness=0)

		# Neutral title label: NO blue or orange text
		self.title_label = tk.Label(
			self.frame,
			text=title,
			font=("Segoe UI", 9, "bold"),
			anchor="w",
		)
		self.title_label.pack(fill="x", padx=4, pady=(2, 4))

		self.canvas = tk.Canvas(
			self.frame,
			highlightthickness=1,
			height=180,
		)
		self.canvas.pack(fill="both", expand=True)

		self.set_theme(is_dark)

	def set_theme(self, is_dark: bool) -> None:
		self.is_dark = is_dark
		bg = "#202020" if is_dark else "#f3f3f3"
		canvas_bg = "#161616" if is_dark else "#ffffff"
		border = "#383838" if is_dark else "#d1d5db"
		title_fg = "#e0e0e0" if is_dark else "#1f2937"

		self.frame.configure(background=bg)
		self.title_label.configure(background=bg, foreground=title_fg)
		self.canvas.configure(background=canvas_bg, highlightbackground=border)

	@staticmethod
	def _chart_flow(flow: float | None) -> float:
		if flow is None:
			return 0.0
		return min(MAX_FLOW, max(0.0, flow))

	def redraw(
		self,
		samples: list[FlowSample],
		test_name: str,
		criteria: Criteria,
		center_latest_curve: bool,
	) -> bool:
		canvas = self.canvas
		canvas.delete("all")
		width = canvas.winfo_width()
		height = canvas.winfo_height()
		if width < 100 or height < 80:
			return False

		left, right, top, bottom = 44, width - 10, 10, height - 24
		if right <= left or bottom <= top:
			return False

		latest_runtime = max(0.0, samples[-1].runtime) if samples else 0.0
		if center_latest_curve:
			min_x = max(0.0, latest_runtime - TIME_WINDOW_SECONDS / 2)
		else:
			min_x = max(0.0, latest_runtime - TIME_WINDOW_SECONDS)
		max_x = min_x + TIME_WINDOW_SECONDS
		visible_samples = [
			sample for sample in samples if min_x <= max(0.0, sample.runtime) <= max_x
		]
		flow_criteria = criteria.get(test_name, {}).get(self.criteria_name, {})

		def point(runtime_val: float, flow_val: float | None) -> tuple[float, float]:
			x = left + (runtime_val - min_x) / TIME_WINDOW_SECONDS * (right - left)
			y = bottom - self._chart_flow(flow_val) / MAX_FLOW * (bottom - top)
			return x, y

		# Theme-specific color parameters
		if self.is_dark:
			grid_color = "#272727"
			border_color = "#383838"
			text_muted = "#8e8e8e"
			criteria_fill = "#122818"
			criteria_border = "#255c2f"
			criteria_text = "#3fb950"
		else:
			grid_color = "#ececec"
			border_color = "#d1d5db"
			text_muted = "#6b7280"
			criteria_fill = "#dcfce7"
			criteria_border = "#86efac"
			criteria_text = "#15803d"

		# Draw passing region behind grid
		self._draw_passing_region(
			left, right, top, bottom, flow_criteria, criteria_fill, criteria_border, criteria_text
		)

		# Dense grid - Windows Task Manager style (8 horizontal divisions, 12 vertical divisions)
		num_y_ticks = 8
		for tick in range(num_y_ticks + 1):
			y = top + tick * (bottom - top) / num_y_ticks
			canvas.create_line(left, y, right, y, fill=grid_color)

		num_x_ticks = 12
		for tick in range(num_x_ticks + 1):
			x = left + tick * (right - left) / num_x_ticks
			canvas.create_line(x, top, x, bottom, fill=grid_color)

		# Outer border of chart area
		canvas.create_rectangle(left, top, right, bottom, outline=border_color)

		# Y-axis labels (Neutral text: NO blue or orange)
		canvas.create_text(left - 6, top, text=f"{int(MAX_FLOW)}", anchor="e", fill=text_muted, font=("Segoe UI", 8))
		canvas.create_text(left - 6, bottom, text="0", anchor="e", fill=text_muted, font=("Segoe UI", 8))

		# X-axis time labels (Neutral text: NO blue or orange)
		canvas.create_text(left, bottom + 12, text=f"{int(min_x)}s", anchor="w", fill=text_muted, font=("Segoe UI", 8))
		canvas.create_text(right, bottom + 12, text=f"{int(max_x)}s", anchor="e", fill=text_muted, font=("Segoe UI", 8))

		self._draw_series(visible_samples, point)
		return True

	def _draw_passing_region(
		self,
		left: float,
		right: float,
		top: float,
		bottom: float,
		flow_criteria: dict[str, float],
		fill_color: str,
		outline_color: str,
		text_color: str,
	) -> None:
		minimum = self._chart_flow(flow_criteria.get("min", 0.0))
		maximum = self._chart_flow(flow_criteria.get("max", 0.0))
		if maximum <= minimum:
			return

		y_top = bottom - maximum / MAX_FLOW * (bottom - top)
		y_bottom = bottom - minimum / MAX_FLOW * (bottom - top)
		self.canvas.create_rectangle(
			left, y_top, right, y_bottom, fill=fill_color, stipple="gray25", outline=outline_color, dash=(2, 2)
		)
		self.canvas.create_text(
			left - 6,
			y_top,
			text=f"{flow_criteria.get('max', 0.0):g}",
			anchor="e",
			fill=text_color,
			font=("Segoe UI", 8, "bold"),
		)
		self.canvas.create_text(
			left - 6,
			y_bottom,
			text=f"{flow_criteria.get('min', 0.0):g}",
			anchor="e",
			fill=text_color,
			font=("Segoe UI", 8, "bold"),
		)

	def _draw_series(
		self,
		samples: list[FlowSample],
		point: Callable[[float, float | None], tuple[float, float]],
	) -> None:
		for index in range(1, len(samples)):
			previous, current = samples[index - 1], samples[index]
			self.canvas.create_line(
				*point(max(0.0, previous.runtime), getattr(previous, self.flow_name)),
				*point(max(0.0, current.runtime), getattr(current, self.flow_name)),
				fill=self.color,
				width=2,
				dash=self.dash,
			)

		if samples:
			last_sample = samples[-1]
			coordinates = point(
				max(0.0, last_sample.runtime), getattr(last_sample, self.flow_name)
			)
			self.canvas.create_oval(
				coordinates[0] - 2,
				coordinates[1] - 2,
				coordinates[0] + 2,
				coordinates[1] + 2,
				fill=self.color,
				outline="",
			)
