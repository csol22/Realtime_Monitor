import math
import time

if __package__:
	from .monitor_config import (
		AUTO_MODE_DP_SETPOINT_REGISTER,
		AUTO_MODE_P31_REGISTER,
		AUTO_MODE_PUMP_SPEED_SCALE,
		AUTO_MODE_P41_REGISTER,
		FLOW_SCALE,
		SPEED_SCALE,
	)
else:
	from monitor_config import (
		AUTO_MODE_DP_SETPOINT_REGISTER,
		AUTO_MODE_P31_REGISTER,
		AUTO_MODE_PUMP_SPEED_SCALE,
		AUTO_MODE_P41_REGISTER,
		FLOW_SCALE,
		SPEED_SCALE,
	)


class PreviewResponse:
	def __init__(self, value: int | list[int]) -> None:
		if isinstance(value, list):
			self.registers = value
		else:
			self.registers = [value]

	def isError(self) -> bool:
		return False


class PreviewCoilResponse:
	def __init__(self, value: bool) -> None:
		self.bits = [value]

	def isError(self) -> bool:
		return False


class PreviewClient:
	def connect(self) -> bool:
		return True

	def read_holding_registers(self, address: int, count: int = 1, **_kwargs) -> PreviewResponse:
		del _kwargs
		phase = time.time() / 8
		values = {
			37: round((120 + 30 * math.sin(phase)) * FLOW_SCALE),
			38: round((115 + 40 * math.sin(phase + 1)) * FLOW_SCALE),
			39: round(58 * SPEED_SCALE),
			40: round(58 * SPEED_SCALE),
			AUTO_MODE_P31_REGISTER: round(58 * AUTO_MODE_PUMP_SPEED_SCALE),
			AUTO_MODE_P41_REGISTER: round(58 * AUTO_MODE_PUMP_SPEED_SCALE),
			35: round(14.5 * 10),   # Actual Secondary DP ~14.5 psi
			AUTO_MODE_DP_SETPOINT_REGISTER: round(15.0 * 10),
		}
		result = [values.get(address + i, 0) for i in range(count)]
		return PreviewResponse(result)

	def read_coils(self, address: int, count: int = 1, **_kwargs) -> PreviewCoilResponse:
		del address, count, _kwargs
		return PreviewCoilResponse(False)

	def close(self) -> None:
		pass
