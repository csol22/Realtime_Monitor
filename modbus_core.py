import socket
import threading
import time

if __package__:
	from .models import FlowSample
	from .monitor_config import (
		DEFAULT_SLAVE_ID,
		FLOW_SCALE,
		MODBUS_PORT,
		SPEED_SCALE,
	)
else:
	from models import FlowSample
	from monitor_config import DEFAULT_SLAVE_ID, FLOW_SCALE, MODBUS_PORT, SPEED_SCALE

try:
	from pymodbus.client import ModbusTcpClient
except ImportError:
	ModbusTcpClient = None


class ModbusCore:
	"""Thread-safe Modbus client with prioritized batch register reads for fast 50ms refresh."""

	def __init__(self, client=None) -> None:
		self._client = client
		self._client_lock = threading.Lock()
		self._supports_batch = True

	@property
	def available(self) -> bool:
		return ModbusTcpClient is not None

	@property
	def connected(self) -> bool:
		with self._client_lock:
			return self._client is not None

	def connect(self, ip_address: str) -> None:
		if ModbusTcpClient is None:
			raise RuntimeError("Install pymodbus before connecting.")

		client = ModbusTcpClient(ip_address, port=MODBUS_PORT, timeout=1.5)
		try:
			if not client.connect():
				raise ConnectionError(f"Could not connect to {ip_address}:{MODBUS_PORT}")
			if hasattr(client, "socket") and client.socket is not None:
				try:
					client.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
				except (OSError, AttributeError):
					pass
		except Exception:
			client.close()
			raise

		with self._client_lock:
			previous_client = self._client
			self._client = client
			self._supports_batch = True
			if previous_client is not None and previous_client is not client:
				previous_client.close()

	def disconnect(self) -> None:
		with self._client_lock:
			client = self._client
			self._client = None
			if client is not None:
				client.close()

	def read_sample(self, start_time: float | None) -> FlowSample | None:
		with self._client_lock:
			if self._client is None:
				return None

			# 1. 优先发送流量寄存器读取请求 (37: FT01, 38: FT61)
			flow_registers = self._read_registers(37, 2)
			# 2. 随后发送泵转速寄存器读取请求 (39: P31, 40: P41)
			pump_registers = self._read_registers(39, 2)

		now = time.time()
		runtime = now - start_time if start_time is not None else 0.0

		reg_ft01, reg_ft61 = flow_registers[0], flow_registers[1]
		reg_p31, reg_p41 = pump_registers[0], pump_registers[1]

		return FlowSample(
			timestamp=now,
			runtime=runtime,
			# Register 38: FT61 (Primary Flow), Register 37: FT01 (Secondary Flow)
			primary_flow=self._signed_value(reg_ft61) / FLOW_SCALE,
			secondary_flow=self._signed_value(reg_ft01) / FLOW_SCALE,
			pump31_speed=self._signed_value(reg_p31) / SPEED_SCALE,
			pump41_speed=self._signed_value(reg_p41) / SPEED_SCALE,
		)

	def _read_registers(self, start_address: int, count: int) -> list[int]:
		if self._supports_batch:
			try:
				try:
					response = self._client.read_holding_registers(
						address=start_address, count=count, slave=DEFAULT_SLAVE_ID
					)
				except TypeError:
					response = self._client.read_holding_registers(
						address=start_address, count=count, device_id=DEFAULT_SLAVE_ID
					)

				if not response.isError() and response.registers and len(response.registers) >= count:
					return response.registers[:count]
			except Exception:
				self._supports_batch = False

		# Fallback to reading registers individually if batch read fails
		results: list[int] = []
		for address in range(start_address, start_address + count):
			results.append(self._read_single_register(address))
		return results

	def _read_single_register(self, address: int) -> int:
		try:
			response = self._client.read_holding_registers(
				address=address, count=1, slave=DEFAULT_SLAVE_ID
			)
		except TypeError:
			response = self._client.read_holding_registers(
				address=address, count=1, device_id=DEFAULT_SLAVE_ID
			)

		if response.isError() or not response.registers:
			raise RuntimeError(f"Read error at register {address}")
		return response.registers[0]

	@staticmethod
	def _signed_value(raw_value: int) -> int:
		return raw_value - 65536 if raw_value > 32767 else raw_value
