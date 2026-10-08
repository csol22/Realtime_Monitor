import math
import time

if __package__:
	from .monitor_config import FLOW_SCALE, SPEED_SCALE
else:
	from monitor_config import FLOW_SCALE, SPEED_SCALE


class PreviewResponse:
	def __init__(self, value: int | list[int]) -> None:
		if isinstance(value, list):
			self.registers = value
		else:
			self.registers = [value]

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
			39: round((65 + 20 * math.sin(phase / 2)) * SPEED_SCALE),
			40: round((55 + 25 * math.sin(phase / 2 + 1)) * SPEED_SCALE),
		}
		result = [values.get(address + i, 0) for i in range(count)]
		return PreviewResponse(result)

	def close(self) -> None:
		pass
