import pygatt
import retrying
import struct

TIMEOUT = 1

UUID_DEVICE_NAME = "00002a00-0000-1000-8000-00805f9b34fb"
UUID_MODEL_NUMBER = "00002a24-0000-1000-8000-00805f9b34fb"
UUID_MANUFACTURER = "00002a29-0000-1000-8000-00805f9b34fb"

UUID_READ = "bccb0003-ca66-11e5-88a4-0002a5d5c51b"
UUID_WRITE = "bccb0002-ca66-11e5-88a4-0002a5d5c51b"


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


def _convert_temperature_reverse(mira_temp):
    return round((mira_temp + 268) / 10.4, 2)


@retrying.retry(stop_max_attempt_number=10)
def _connect(address):
    adapter = pygatt.GATTToolBackend()
    adapter.start()
    device = adapter.connect(
        address,
        timeout=TIMEOUT,
        address_type=pygatt.BLEAddressType.random)
    return device


def _read(address):
    device = _connect(address)
    return device.char_read(UUID_READ)


def _write(address, payload):
    device = _connect(address)
    device.char_write(UUID_WRITE, payload)


def get_device_info(address):
    device = _connect(address)
    device_name = device.char_read(UUID_DEVICE_NAME).decode('UTF-8')
    manufacturer = device.char_read(UUID_MANUFACTURER).decode('UTF-8')
    model_number = device.char_read(UUID_MODEL_NUMBER).decode('UTF-8')

    return (device_name, manufacturer, model_number)


def get_state(address):
    data = _read(address)
    # TODO: In some case it returns different data, without outlet values
    if len(data) == 19:
        return

    if len(data) != 14:
        raise Exception("Unexpected data length")

    temperature = _convert_temperature_reverse(data[6])
    # Bytes at 7 and 8 are related to the temperature set on the shower
    # controller.
    outlet1 = data[9] == 0x64
    outlet2 = data[10] == 0x64

    return (outlet1, outlet2, temperature)


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
    _write(address, _get_payload_with_crc(payload, client_id))


def turn_on_bathfill(address, device_id, client_id):
    payload = bytearray([device_id, 0xb1, 0x01, 0x00])
    _write(address, _get_payload_with_crc(payload, client_id))
