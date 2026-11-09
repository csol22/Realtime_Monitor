# import unittest

# try:
#     from .auto_mode import AutoModeDetector, detect_mode
#     from .monitor_config import (
#         AUTO_MODE_DP_SETPOINT_REGISTER,
#         AUTO_MODE_MANUAL_OVERRIDE_COIL,
#         AUTO_MODE_P31_REGISTER,
#         AUTO_MODE_P41_REGISTER,
#     )
#     from .modbus_core import ModbusCore
#     from .preview_client import PreviewClient
# except ImportError:
#     from auto_mode import AutoModeDetector, detect_mode
#     from monitor_config import (
#         AUTO_MODE_DP_SETPOINT_REGISTER,
#         AUTO_MODE_MANUAL_OVERRIDE_COIL,
#         AUTO_MODE_P31_REGISTER,
#         AUTO_MODE_P41_REGISTER,
#     )
#     from modbus_core import ModbusCore
#     from preview_client import PreviewClient


# class AutoModeDetectionTests(unittest.TestCase):
#     def test_detects_each_test_mode_from_scaled_values(self) -> None:
#         cases = (
#             (True, 100, 0, 0, "P31 100% Pump Test"),
#             (True, 0, 100, 0, "P41 100% Pump Test"),
#             (False, 0, 0, 15, "15DP Test"),
#             (False, 0, 0, 20, "20DP Test"),
#             (False, 0, 0, 25, "25DP Test"),
#             (False, 0, 0, 30, "30DP Test"),
#             (True, 25, 25, 0, "Combine 25% Pump Test"),
#             (True, 50, 50, 0, "Combine 50% Pump Test"),
#             (True, 75, 75, 0, "Combine 75% Pump Test"),
#             (True, 100, 100, 0, "Combine 100% Pump Test"),
#         )
#         for manual_override, p31, p41, dp, expected in cases:
#             with self.subTest(expected=expected):
#                 self.assertEqual(detect_mode(manual_override, p31, p41, dp), expected)

#     def test_requires_matching_override_state_and_exact_values(self) -> None:
#         self.assertIsNone(detect_mode(False, 100, 0, 0))
#         self.assertIsNone(detect_mode(True, 0, 0, 15))
#         self.assertIsNone(detect_mode(True, 99, 0, 0))
#         self.assertIsNone(detect_mode(True, 25, 50, 0))
#         self.assertIsNone(detect_mode(False, 0, 0, 15.1))

#     def test_reads_new_addresses_and_applies_register_scaling(self) -> None:
#         modbus = _FakeModbus()
#         callbacks = []
#         detector = AutoModeDetector(modbus, callbacks.append, _FakeRoot())

#         detector._detect_once()

#         self.assertEqual(modbus.register_reads, [
#             (AUTO_MODE_P31_REGISTER, 1),
#             (AUTO_MODE_P41_REGISTER, 1),
#             (AUTO_MODE_DP_SETPOINT_REGISTER, 1),
#         ])
#         self.assertEqual(modbus.coil_reads, [(AUTO_MODE_MANUAL_OVERRIDE_COIL, 1)])
#         self.assertEqual(callbacks, ["P31 100% Pump Test"])

#     def test_preview_client_still_detects_its_demo_dp_mode(self) -> None:
#         detector = AutoModeDetector(
#             ModbusCore(client=PreviewClient()), lambda mode: self.assertEqual(mode, "15DP Test"),
#             _FakeRoot(),
#         )

#         detector._detect_once()


# class _FakeModbus:
#     register_values = {
#         AUTO_MODE_P31_REGISTER: [10000],
#         AUTO_MODE_P41_REGISTER: [0],
#         AUTO_MODE_DP_SETPOINT_REGISTER: [150],
#     }

#     def __init__(self) -> None:
#         self.register_reads = []
#         self.coil_reads = []

#     def read_registers_raw(self, address: int, count: int) -> list[int]:
#         self.register_reads.append((address, count))
#         return self.register_values[address]

#     def read_coils_raw(self, address: int, count: int) -> list[bool]:
#         self.coil_reads.append((address, count))
#         return [True]

#     @staticmethod
#     def signed(value: int) -> int:
#         return value


# class _FakeRoot:
#     @staticmethod
#     def after(_delay: int, callback, mode: str | None) -> None:
#         callback(mode)


# if __name__ == "__main__":
#     unittest.main()
