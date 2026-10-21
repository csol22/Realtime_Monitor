import math
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

try:
    from pymodbus.pdu.device import ModbusDeviceIdentification
    from pymodbus.server import StartTcpServer
    from pymodbus.simulator.simdata import SimData
    from pymodbus.simulator.simdevice import SimDevice
    from pymodbus.simulator.simutils import DataType
except ImportError as e:
    print(f"错误: pymodbus 缺失或版本不兼容（需要 >=3.15,<4）: {e}")
    exit(1)

# 放大倍率（需与 Monitor 主程序中的比例保持一致）
FLOW_SCALE = 100.0
SPEED_SCALE = 1.0
FLOW_SINE_PERIOD_S = 10.0

class ModbusPLCSimulator:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Modbus TCP PLC Simulator (Signal Generator)")
        self.root.geometry("540x620")

        self.register_values = [0] * 202
        self.register_values_lock = threading.Lock()
        self._sine_start_time = time.monotonic()
        self._control_entries: list[tuple[ttk.Entry, tk.StringVar, tk.DoubleVar]] = []
        identity = ModbusDeviceIdentification()
        identity.VendorName = "MockPLC"
        identity.ProductCode = "SIM01"
        identity.ModelName = "PLC Simulator"
        self.device = SimDevice(
            id=1,
            simdata=[
                SimData(
                    address=0,
                    values=[0] * 202,
                    datatype=DataType.REGISTERS,
                )
            ],
            identity=identity,
            action=self._update_simulated_registers,
        )
        
        # 初始默认值
        self.primary_flow_var = tk.DoubleVar(value=150.0)
        self.secondary_flow_var = tk.DoubleVar(value=150.0)
        self.pump31_var = tk.DoubleVar(value=0.0)
        self.pump41_var = tk.DoubleVar(value=0.0)
        self.actual_dp_var = tk.DoubleVar(value=14.5)
        self.dp_setpoint_var = tk.DoubleVar(value=15.0)
        self.flow_sine_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._sync_values_to_modbus()
        self._start_server_thread()
        self._start_update_loop()

    def _build_ui(self):
        frame = ttk.LabelFrame(
            self.root,
            text="Manual Control Panel (Holding Registers 35, 37-40, 201)",
            padding=15,
        )
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Checkbutton(
            frame,
            text=f"Enable sine-wave flow (0–set value, {FLOW_SINE_PERIOD_S:g}s period)",
            variable=self.flow_sine_var,
            command=self._on_flow_sine_toggled,
        ).pack(anchor="w", pady=(0, 8))

        self.primary_label = self._add_numeric_control(
            frame, "Primary Flow (FT61) target/peak [g/m]", self.primary_flow_var, 0, 200
        )
        self.secondary_label = self._add_numeric_control(
            frame, "Secondary Flow (FT01) target/peak [g/m]", self.secondary_flow_var, 0, 200
        )
        self.p31_label = self._add_numeric_control(
            frame, "Pump 31 Speed (Register 39)", self.pump31_var, 0, 100
        )
        self.p41_label = self._add_numeric_control(
            frame, "Pump 41 Speed (Register 40)", self.pump41_var, 0, 100
        )
        self.actual_dp_label = self._add_numeric_control(
            frame, "Actual Secondary DP (Register 35)", self.actual_dp_var, 0, 35
        )
        self.dp_setpoint_label = self._add_numeric_control(
            frame, "Secondary DP Setpoint (Register 201)", self.dp_setpoint_var, 0, 35
        )

        status_lbl = ttk.Label(self.root, text="Server Running on 127.0.0.1:502", foreground="green")
        status_lbl.pack(pady=5)

    def _add_numeric_control(
        self,
        parent: ttk.Labelframe,
        title: str,
        value: tk.DoubleVar,
        minimum: float,
        maximum: float,
    ) -> ttk.Label:
        ttk.Label(parent, text=title).pack(anchor="w")
        value_label = ttk.Label(parent, text="", font=("Consolas", 10, "bold"))
        value_label.pack(anchor="e")

        control_row = ttk.Frame(parent)
        control_row.pack(fill="x", pady=(0, 9))
        scale = ttk.Scale(
            control_row,
            from_=minimum,
            to=maximum,
            variable=value,
            command=self._on_slider_changed,
        )
        scale.pack(side="left", fill="x", expand=True)

        entry_var = tk.StringVar(value=f"{value.get():g}")
        entry = ttk.Entry(control_row, textvariable=entry_var, width=10)
        entry.pack(side="left", padx=(8, 0))
        entry.bind(
            "<Return>",
            lambda _event, var=value, text=entry_var, low=minimum, high=maximum, name=title:
                self._commit_entry(var, text, low, high, name),
        )
        self._control_entries.append((entry, entry_var, value))
        return value_label

    def _on_slider_changed(self, _value: str) -> None:
        self._update_labels()
        self._sync_values_to_modbus()

    def _commit_entry(
        self,
        value: tk.DoubleVar,
        entry_var: tk.StringVar,
        minimum: float,
        maximum: float,
        title: str,
    ) -> str:
        raw_value = entry_var.get().strip()
        try:
            number = float(raw_value)
        except ValueError:
            self._show_entry_error(title, f"Enter a number between {minimum:g} and {maximum:g}.")
            return "break"

        if not math.isfinite(number) or not minimum <= number <= maximum:
            self._show_entry_error(title, f"Value must be between {minimum:g} and {maximum:g}.")
            return "break"

        value.set(number)
        self._update_labels()
        self._sync_values_to_modbus()
        return "break"

    def _show_entry_error(self, title: str, detail: str) -> None:
        messagebox.showerror("Invalid value", f"{title}: {detail}", parent=self.root)

    def _on_flow_sine_toggled(self) -> None:
        self._update_labels()
        self._sync_values_to_modbus()

    def _flow_values(self) -> tuple[float, float]:
        primary = self.primary_flow_var.get()
        secondary = self.secondary_flow_var.get()
        if not self.flow_sine_var.get():
            return primary, secondary

        phase = 2 * math.pi * (time.monotonic() - self._sine_start_time) / FLOW_SINE_PERIOD_S
        factor = (1 + math.sin(phase)) / 2
        return primary * factor, secondary * factor

    def _update_labels(self):
        primary_flow, secondary_flow = self._flow_values()
        self.primary_label.config(text=f"{primary_flow:.1f} g/m")
        self.secondary_label.config(text=f"{secondary_flow:.1f} g/m")
        self.p31_label.config(text=f"{self.pump31_var.get():.1f} %")
        self.p41_label.config(text=f"{self.pump41_var.get():.1f} %")
        self.actual_dp_label.config(text=f"{self.actual_dp_var.get():.1f} psi")
        self.dp_setpoint_label.config(text=f"{self.dp_setpoint_var.get():.1f} psi")
        for entry, entry_var, value in self._control_entries:
            if self.root.focus_get() is not entry:
                entry_var.set(f"{value.get():g}")

    def _sync_values_to_modbus(self):
        """Convert GUI values to Modbus registers used by the monitor."""
        primary_flow, secondary_flow = self._flow_values()
        values = [
            round(secondary_flow * FLOW_SCALE),
            round(primary_flow * FLOW_SCALE),
            int(self.pump31_var.get() * SPEED_SCALE),
            int(self.pump41_var.get() * SPEED_SCALE),
        ]
        with self.register_values_lock:
            self.register_values[35] = round(self.actual_dp_var.get() * FLOW_SCALE)
            self.register_values[37:41] = values
            self.register_values[201] = round(self.dp_setpoint_var.get() * FLOW_SCALE)

    def _start_update_loop(self):
        self._sync_values_to_modbus()
        self._update_labels()
        self.root.after(100, self._start_update_loop)

    async def _update_simulated_registers(
        self,
        function_code: int,
        start_address: int,
        address: int,
        count: int,
        current_registers: list[int],
        set_values: list[int] | list[bool] | None,
    ) -> None:
        if function_code not in (3, 23) or (
            set_values is not None and function_code != 23
        ):
            return
        with self.register_values_lock:
            for register in (35, 37, 38, 39, 40, 201):
                offset = register - start_address
                if address <= register < address + count and 0 <= offset < len(current_registers):
                    current_registers[offset] = self.register_values[register]

    def _start_server_thread(self):
        def run_server():
            # 启动本地 502 端口的 Modbus TCP 服务
            # 如果报 Permission Error，说明 502 端口需要管理员权限，可以改用 5020 端口测试
            try:
                StartTcpServer(
                    context=self.device,
                    address=("127.0.0.1", 502)
                )
            except Exception as e:
                print(f"Modbus Server 启动失败: {e}")

        threading.Thread(target=run_server, daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = ModbusPLCSimulator(root)
    root.mainloop()