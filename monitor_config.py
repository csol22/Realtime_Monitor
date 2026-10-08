MODBUS_PORT = 502
DEFAULT_SLAVE_ID = 1
DEFAULT_REFRESH_MS = 1000
REFRESH_INTERVALS = (50, 100, 250, 500, 1000)
HISTORY_LIMIT = 3600
TIME_WINDOW_SECONDS = 60
MAX_FLOW = 2400.0
FLOW_SCALE = 10.0
SPEED_SCALE = 1.0

TEST_MODES = (
	"P31 100% Pump Test",
	"P41 100% Pump Test",
	"Combine 25% Pump Test",
	"Combine 50% Pump Test",
	"Combine 75% Pump Test",
	"Combine 100% Pump Test",
	"15DP Test",
	"20DP Test",
	"25DP Test",
	"30DP Test",
)
