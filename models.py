from dataclasses import dataclass


@dataclass(frozen=True)
class FlowSample:
	timestamp: float
	runtime: float
	primary_flow: float
	secondary_flow: float
	pump31_speed: float
	pump41_speed: float
