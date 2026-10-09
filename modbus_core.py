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
	"""Thread-safe Modbus client with prioritized batch register reads and multi-rate scanning."""

	def __init__(
		self,
		client=None,
		slave_id: int = DEFAULT_SLAVE_ID,
		port: int = MODBUS_PORT,
		timeout: float = 1.0,
		retries: int = 0,
		tcp_nodelay: bool = True,
		contiguous_batch_read: bool = True,
	) -> None:
		self._client = client
		self._client_lock = threading.Lock()
		self._supports_batch = True
		self.slave_id = slave_id
		self.port = port
		self.timeout = timeout
		self.retries = retries
		self.tcp_nodelay = tcp_nodelay
		self.contiguous_batch_read = contiguous_batch_read

		# Cached readings so that when only flow or pump is read, latest values persist
		self._cached_primary_flow = 0.0
		self._cached_secondary_flow = 0.0
		self._cached_pump31_speed = 0.0
		self._cached_pump41_speed = 0.0
		self._has_sample = False

	def configure(
		self,
		slave_id: int | None = None,
		port: int | None = None,
		timeout: float | None = None,
		retries: int | None = None,
		tcp_nodelay: bool | None = None,
		contiguous_batch_read: bool | None = None,
	) -> None:
		with self._client_lock:
			if slave_id is not None:
				self.slave_id = slave_id
			if port is not None:
				self.port = port
			if timeout is not None:
				self.timeout = timeout
			if retries is not None:
				self.retries = retries
			if tcp_nodelay is not None:
				self.tcp_nodelay = tcp_nodelay
			if contiguous_batch_read is not None:
				self.contiguous_batch_read = contiguous_batch_read

			if self._client is not None:
				if hasattr(self._client, "comm_params") and timeout is not None:
					self._client.comm_params.timeout_connect = timeout
				if hasattr(self._client, "retries") and retries is not None:
					self._client.retries = retries

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

		try:
			client = ModbusTcpClient(
				ip_address,
				port=self.port,
				timeout=self.timeout,
				retries=self.retries,
			)
		except TypeError:
			client = ModbusTcpClient(
				ip_address,
				port=self.port,
				timeout=self.timeout,
			)

		try:
			if not client.connect():
				raise ConnectionError(f"Could not connect to {ip_address}:{self.port}")
			if self.tcp_nodelay and hasattr(client, "socket") and client.socket is not None:
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

	def read_sample(
		self,
		start_time: float | None,
		read_flow: bool = True,
		read_pump: bool = True,
	) -> FlowSample | None:
		with self._client_lock:
			if self._client is None:
				return None

			# If both flow and pump are needed and contiguous batch read is enabled,
			# attempt to read registers 37-40 (FT01, FT61, P31, P41) in one request.
			if read_flow and read_pump and self.contiguous_batch_read:
				try:
					# 37: FT01, 38: FT61, 39: P31, 40: P41 (4 contiguous registers)
					all_regs = self._read_registers(37, 4)
					reg_ft01, reg_ft61 = all_regs[0], all_regs[1]
					reg_p31, reg_p41 = all_regs[2], all_regs[3]
					self._cached_secondary_flow = self._signed_value(reg_ft01) / FLOW_SCALE
					self._cached_primary_flow = self._signed_value(reg_ft61) / FLOW_SCALE
					self._cached_pump31_speed = self._signed_value(reg_p31) / SPEED_SCALE
					self._cached_pump41_speed = self._signed_value(reg_p41) / SPEED_SCALE
					self._has_sample = True
				except Exception:
					# Batch failed: fall back to separate reads
					if read_flow:
						flow_regs = self._read_registers(37, 2)
						self._cached_secondary_flow = self._signed_value(flow_regs[0]) / FLOW_SCALE
						self._cached_primary_flow = self._signed_value(flow_regs[1]) / FLOW_SCALE
					if read_pump:
						pump_regs = self._read_registers(39, 2)
						self._cached_pump31_speed = self._signed_value(pump_regs[0]) / SPEED_SCALE
						self._cached_pump41_speed = self._signed_value(pump_regs[1]) / SPEED_SCALE
					self._has_sample = True
			else:
				if read_flow:
					flow_regs = self._read_registers(37, 2)
					self._cached_secondary_flow = self._signed_value(flow_regs[0]) / FLOW_SCALE
					self._cached_primary_flow = self._signed_value(flow_regs[1]) / FLOW_SCALE
					self._has_sample = True
				if read_pump:
					pump_regs = self._read_registers(39, 2)
					self._cached_pump31_speed = self._signed_value(pump_regs[0]) / SPEED_SCALE
					self._cached_pump41_speed = self._signed_value(pump_regs[1]) / SPEED_SCALE
					self._has_sample = True

		if not self._has_sample:
			return None

		now = time.time()
		runtime = now - start_time if start_time is not None else 0.0

		return FlowSample(
			timestamp=now,
			runtime=runtime,
			primary_flow=self._cached_primary_flow,
			secondary_flow=self._cached_secondary_flow,
			pump31_speed=self._cached_pump31_speed,
			pump41_speed=self._cached_pump41_speed,
		)

	def _read_registers(self, start_address: int, count: int) -> list[int]:
		if self._supports_batch:
			try:
				try:
					response = self._client.read_holding_registers(
						address=start_address, count=count, slave=self.slave_id
					)
				except TypeError:
					response = self._client.read_holding_registers(
						address=start_address, count=count, device_id=self.slave_id
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
				address=address, count=1, slave=self.slave_id
			)
		except TypeError:
			response = self._client.read_holding_registers(
				address=address, count=1, device_id=self.slave_id
			)

		if response.isError() or not response.registers:
			raise RuntimeError(f"Read error at register {address}")
		return response.registers[0]

	@staticmethod
	def _signed_value(raw_value: int) -> int:
		return raw_value - 65536 if raw_value > 32767 else raw_value
