import tkinter as tk

if __package__:
    from .models import FlowSample
else:
    from models import FlowSample


OVERLAY_REGISTERS = (
    (37, "Secondary", "l/m", "secondary_flow"),
    (38, "Primary", "l/m", "primary_flow"),
    (39, "P31", "%", None),
    (40, "P41", "%", None),
)
OVERLAY_REGISTER_INFO = {
    address: (name, unit, attribute)
    for address, name, unit, attribute in OVERLAY_REGISTERS
}


class FlowOverlay:
    """Compact, always-on-top display for selected live Modbus registers."""

    def __init__(self, parent: tk.Misc, is_dark: bool) -> None:
        self.window = tk.Toplevel(parent)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)

        self.is_dark = is_dark
        # 将 padx 和 pady 减小到 2 或 0，去除四周宽泛的边距
        self.container = tk.Frame(self.window, padx=2, pady=2)
        self.container.pack(fill="both", expand=True)

        # 彻底删除 self.title 和 self.separator 的相关代码
        
        self.rows_frame = tk.Frame(self.container)
        self.rows_frame.pack(fill="x")
        # 修改字典结构，改为存储 (数值Label, 单位Label) 以便后续更新
        self.rows: dict[int, tuple[tk.Label, tk.Label]] = {}
        self._apply_theme()

    def configure_display(
        self, enabled: bool, registers: list[int], is_dark: bool
    ) -> None:
        self.is_dark = is_dark
        self._apply_theme()

        for child in self.rows_frame.winfo_children():
            child.destroy()
        self.rows.clear()

        # 为不同类型的监控项分配颜色 (类似 GPU用绿色, CPU用蓝色)
        # 这里假设 37, 38 是流量(绿)，39, 40 是水泵转速(蓝)
        label_colors = {37: "#048042", 38: "#048042", 39: "#0081BF", 40: "#0081BF"}

        for row, address in enumerate(registers):
            name, unit, _ = OVERLAY_REGISTER_INFO[address]
            line = tk.Frame(self.rows_frame, background=self.background)
            line.grid(row=row, column=0, sticky="ew", pady=0) # 减小行间距
            
            # 第一列：名称 (绿色或蓝色，等宽字体)
            name_color = label_colors.get(address, "#FFFFFF")
            name_label = tk.Label(
                line, text=name, width=10, anchor="w",
                font=("Consolas", 12, "bold"), background=self.background,
                foreground=name_color,
            )
            name_label.grid(row=0, column=0, sticky="w")
            
            # 第二列：实时数值 (Afterburner标志性的亮橙色，字体加大)
            value_label = tk.Label(
                line, text="--", width=5, anchor="e",
                font=("Consolas", 14, "bold"), background=self.background,
                foreground="#FF8C00", # 亮橙色
            )
            value_label.grid(row=0, column=1, sticky="e", padx=(4, 2))
            
            # 第三列：单位 (小一号字体，浅色)
            unit_label = tk.Label(
                line, text=unit, width=3, anchor="w",
                font=("Consolas", 9, "bold"), background=self.background,
                foreground="#FF8C00", # 亮橙色
            )
            unit_label.grid(row=0, column=2, sticky="w")
            
            self.rows[address] = (value_label, unit_label)

        self.container.configure(
            background=self.background,
            highlightthickness=0, # 移除外边框
        )
        self.rows_frame.configure(background=self.background)

        if enabled:
            self.window.deiconify()
            self._position()
        else:
            self.window.withdraw()

    def update_readings(
        self,
        sample: FlowSample,
        flow_pass: dict[int, bool],
    ) -> None:
        for address, (value_label, unit_label) in self.rows.items():
            _, _, attribute = OVERLAY_REGISTER_INFO[address]
            
            # 提取数值
            value = getattr(sample, attribute) if attribute is not None else (
                sample.pump31_speed if address == 39 else sample.pump41_speed
            )
            
            # 只更新数值部分，单位部分保持不变，模拟出数字跳动的感觉
            # 如果是整数可以直接用 f"{int(value)}"
            value_label.configure(text=f"{value:.1f}")

    def _position(self) -> None:
        self.window.update_idletasks()
        width = self.window.winfo_reqwidth()
        x = max(0, self.window.winfo_screenwidth() - width - 16)
        self.window.geometry(f"+{x}+16")

    def _apply_theme(self) -> None:
        if self.is_dark:
            self.background = "#000000"
            self.foreground = "#f3f4f6"
            self.muted = "#aab2bd"
            self.accent = "#f59e0b"
            self.green = "#048042"
            self.red = "#f85149"
        else:
            self.background = "#000000"
            self.foreground = "#f3f4f6"
            self.muted = "#c3c9d1"
            self.accent = "#f59e0b"
            self.green = "#048042"
            self.red = "#f85149"

        self.window.configure(background=self.background)
        self.container.configure(background=self.background)
        try:
                    self.window.attributes("-transparentcolor", self.background)
        except tk.TclError:
            pass