import asyncio
import threading
import unittest

from pymodbus.pdu.device import ModbusDeviceIdentification
from pymodbus.simulator.simdata import SimData
from pymodbus.simulator.simdevice import SimDevice
from pymodbus.simulator.simruntime import SimRuntime
from pymodbus.simulator.simutils import DataType

try:
    from .monitor_config import AUTO_MODE_MANUAL_OVERRIDE_COIL, AUTO_MODE_P41_REGISTER
    from .plc_simulator import ModbusPLCSimulator
except ImportError:
    from monitor_config import AUTO_MODE_MANUAL_OVERRIDE_COIL, AUTO_MODE_P41_REGISTER
    from plc_simulator import ModbusPLCSimulator


class PlcSimulatorCoilTests(unittest.TestCase):
    def test_coil_753_reads_manual_override_state(self) -> None:
        simulator = ModbusPLCSimulator.__new__(ModbusPLCSimulator)
        simulator.register_values_lock = threading.Lock()
        simulator._manual_override_enabled = False
        device = SimDevice(
            id=1,
            simdata=(
                [
                    SimData(
                        address=AUTO_MODE_MANUAL_OVERRIDE_COIL,
                        values=[False],
                        datatype=DataType.BITS,
                    )
                ],
                [
                    SimData(address=0, values=[False], datatype=DataType.BITS)
                ],
                [
                    SimData(
                        address=0,
                        values=[0] * (AUTO_MODE_P41_REGISTER + 1),
                        datatype=DataType.REGISTERS,
                    )
                ],
                [
                    SimData(address=0, values=[0], datatype=DataType.REGISTERS)
                ],
            ),
            identity=ModbusDeviceIdentification(),
            action=simulator._update_simulated_registers,
        )
        runtime = SimRuntime(device)

        self.assertEqual(
            asyncio.run(
                runtime.async_getValues(1, AUTO_MODE_MANUAL_OVERRIDE_COIL, 1)
            ),
            [False],
        )
        simulator._manual_override_enabled = True
        self.assertEqual(
            asyncio.run(
                runtime.async_getValues(1, AUTO_MODE_MANUAL_OVERRIDE_COIL, 1)
            ),
            [True],
        )


if __name__ == "__main__":
    unittest.main()
