import socket

import psutil


def get_ethernet_details() -> tuple[str | None, bool]:
	ethernet_found = False
	ethernet_connected = False

	try:
		stats = psutil.net_if_stats()
		addrs = psutil.net_if_addrs()

		for nic_name, nic_addrs in addrs.items():
			if "ethernet" not in nic_name.casefold() and "以太网" not in nic_name.casefold():
				continue

			ethernet_found = True
			nic_stat = stats.get(nic_name)
			if not nic_stat or not nic_stat.isup:
				continue
			ethernet_connected = True

			for addr in nic_addrs:
				if addr.family == socket.AF_INET:
					return addr.address, False
	except (OSError, psutil.Error):
		return None, ethernet_found and not ethernet_connected

	return None, ethernet_found and not ethernet_connected


def get_default_modbus_ip() -> str:
	ethernet_ip = get_ethernet_details()[0]
	if ethernet_ip is None:
		try:
			ethernet_ip = socket.gethostbyname(socket.gethostname())
		except socket.error:
			return "..."

	address_parts = ethernet_ip.split(".")
	if len(address_parts) == 4:
		address_parts[-1] = "2"
		return ".".join(address_parts)
	return "..."
