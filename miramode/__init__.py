import pygatt
import retrying
import struct


def _crc(data):
    i = 0
    i2 = 0xFFFF
    while i < len(data):
        b = data[i]
        i3 = i2
        for i2 in range(8):
            i4 = 1
            i5 = 1 if ((b >> (7 - i2)) & 1) == 1 else 0
            if ((i3 >> 15) & 1) != 1:
                i4 = 0
            i3 = i3 << 1
            if (i5 ^ i4) != 0:
                i3 = i3 ^ 0x1021
        i += 1
        i2 = i3
    return i2 & 0xFFFF


def _get_payload_with_crc(payload, client_id):
    crc = _crc(payload + struct.pack(">I", client_id))
    return payload + struct.pack(">H", crc)


def _convert_temperature(celsius):
    return int(max(0, min(255, round(celsius * 10.4 - 268))))


@retrying.retry(stop_max_attempt_number=10)
def _send(address, payload):
    adapter = pygatt.GATTToolBackend()
    adapter.start()
    device = adapter.connect(
        address, address_type=pygatt.BLEAddressType.random)
    device.char_write_handle(0x11, payload)


def control_outlets(address, device_id, client_id, outlet1, outlet2,
                    temperature):
    payload = bytearray([
        device_id,
        0x87, 0x05,
        1 if outlet1 or outlet2 else 3,
        0x01,
        _convert_temperature(temperature),
        0x64 if outlet1 else 0,
        0x64 if outlet2 else 0])
    _send(address, _get_payload_with_crc(payload, client_id))


def turn_on_bathfill(address, device_id, client_id):
    payload = bytearray([device_id, 0xb1, 0x01, 0x00])
    _send(address, _get_payload_with_crc(payload, client_id))
