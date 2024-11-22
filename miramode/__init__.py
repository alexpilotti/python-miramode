import logging
import struct

import retrying
import simplepyble

logger = logging.getLogger(__name__)

TIMEOUT = 1

UUID_DEVICE_NAME = "00002a00-0000-1000-8000-00805f9b34fb"
UUID_MODEL_NUMBER = "00002a24-0000-1000-8000-00805f9b34fb"
UUID_MANUFACTURER = "00002a29-0000-1000-8000-00805f9b34fb"

UUID_READ = "bccb0003-ca66-11e5-88a4-0002a5d5c51b"
UUID_WRITE = "bccb0002-ca66-11e5-88a4-0002a5d5c51b"

MAGIC_ID = 0x54d2ee63

FAILURE = 0x80
SUCCESS = 1

TIMER_STOPPED = 0
TIMER_RUNNING = 1
TIMER_PAUSED = 3

OUTLET_RUNNING = 0x64
OUTLET_STOPPED = 0


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
    return int(max(0, min(255, round(celsius * 10 - 256))))


def _convert_temperature_reverse(mira_temp):
    return (256 + mira_temp) / 10.0


def _format_bytearray(ba):
    return ",".join(format(b, "02x") for b in ba)


def _bits_to_list(bits, length):
    bits_list = []
    for i in range(0, length):
        if bits >> i & 1:
            bits_list.append(i)
    return bits_list


def _split_chunks(data, chunk_size):
    return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]


def _get_peripherals():
    adapters = simplepyble.Adapter.get_adapters()
    adapter = adapters[0]
    adapter.scan_for(TIMEOUT * 1000)
    return adapter.scan_get_results()


def get_available_devices():
    devices = []
    peripherals = _get_peripherals()
    for p in peripherals:
        if "Mira" in p.identifier():
            devices.append((p.identifier(), p.address()))
    return devices


class NotificationsBase():
    def client_details(self, client_slot, client_name):
        pass

    def controls_operated(
            self, client_slot, change_made, timer_state, target_temperature,
            actual_temperature, outlet_state_1, outlet_state_2,
            remaining_seconds, succesful_update_command_counter):
        pass

    def device_settings(
            self, client_slot, outlet_enabled, default_preset_slot,
            controller_senntings):
        pass

    def device_state(
            self, client_slot, timer_state, target_temperature,
            actual_temperature, outlet_state_1, outlet_state_2,
            remaining_seconds, succesful_update_command_counter):
        pass

    def nickname(self, client_slot, nickname):
        pass

    def outlet_settings(
            self, client_slot, outlet_flag, min_duration_seconds,
            max_temperature, min_temperature,
            succesful_update_command_counter):
        pass

    def preset_details(
            self, client_slot, preset_slot, target_temperature,
            duration_seconds, outlet_enabled, preset_name):
        pass

    def slots(self, client_slot, slots):
        pass

    def success_or_failure(self, client_slot, status):
        pass

    def technical_information(self, client_slot, valve_type, valve_sw_version,
                              ui_type, ui_sw_version, bt_sw_version):
        pass


class Connnection:
    def __init__(self, address, client_id=None, client_slot=None):
        self._address = address
        self._peripheral = None
        self._client_id = client_id
        self._client_slot = client_slot

    def set_client_data(self, client_id, client_slot):
        self._client_id = client_id
        self._client_slot = client_slot

    @retrying.retry(stop_max_attempt_number=10)
    def connect(self):
        peripherals = _get_peripherals()
        pl = [p for p in peripherals if
              p.address().lower() == self._address.lower()]
        if not len(pl):
            raise Exception(f"Address not found: {self._address}")

        peripheral = pl[0]
        peripheral.connect()

        self._peripheral = peripheral

    def disconnect(self):
        self._peripheral = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, type, value, traceback):
        self.disconnect()

    def _read(self, characteristic):
        service = self._get_service_for_characteristic(characteristic)
        return self._peripheral.read(service, characteristic)

    def _write_chunks(self, data, chunk_size=20):
        for chunk in _split_chunks(data, chunk_size):
            self._write(chunk)

    def _write(self, data):
        logger.debug(f"Writing data: {_format_bytearray(data)}")
        service = self._get_service_for_characteristic(UUID_WRITE)
        self._peripheral.write_command(service, UUID_WRITE, bytes(data))

    def _get_service_for_characteristic(self, characteristic):
        services = self._peripheral.services()
        for service in services:
            for c in service.characteristics():
                if c.uuid() == characteristic:
                    return service.uuid()
        raise Exception(f"Characteristic not found: {characteristic}")

    def subscribe(self, notifications):
        notifications.partial_payload = bytearray()
        notifications.client_slot = None
        notifications.expected_payload_length = None

        service = self._get_service_for_characteristic(UUID_READ)

        self._peripheral.notify(
            service, UUID_READ, lambda value: self._handle_data(
                value, notifications))

    def _handle_data(self, value, notifications):
        if len(notifications.partial_payload) > 0:
            notifications.partial_payload.extend(value)
            client_slot = notifications.client_slot
            payload = notifications.partial_payload
            payload_length = notifications.expected_payload_length

            notifications.partial_payload = bytearray()
            notifications.client_slot = None
            notifications.expected_payload_length = None
        else:
            if len(value) < 2:
                logger.warning(
                    f"Packet length is too short, skipping: {len(value)}")
                return

            client_slot = value[0] - 0x40
            payload_length = value[2]
            payload = value[3:]

        if len(payload) < payload_length:
            notifications.client_slot = client_slot
            notifications.expected_payload_length = payload_length
            notifications.partial_payload.extend(payload)
            return

        if len(payload) != payload_length:
            logger.warning(
                "Inconsistent payload length, skipping: "
                f"{payload_length}, {len(payload)}")
            return

        logger.debug(
            f"Payload length: {payload_length}, "
            f"payload : {_format_bytearray(payload)}")

        if payload_length == 1:
            notifications.success_or_failure(client_slot, payload[0])

        elif payload_length == 2:
            slots = []
            slot_bits = struct.unpack(">H", payload)[0]
            slots = _bits_to_list(slot_bits, 16)

            notifications.slots(client_slot, slots)

        elif payload_length == 4:
            outlet_enabled = _bits_to_list(payload[1], 8)
            default_preset_slot = payload[2]
            controller_senntings = _bits_to_list(payload[3], 8)

            notifications.device_settings(
                client_slot, outlet_enabled, default_preset_slot,
                controller_senntings)

        elif payload_length == 10:
            timer_state = payload[0]
            target_temperature = _convert_temperature_reverse(payload[2])
            actual_temperature = _convert_temperature_reverse(payload[4])
            outlet_state_1 = payload[5] == OUTLET_RUNNING
            outlet_state_2 = payload[6] == OUTLET_RUNNING
            remaining_seconds = struct.unpack(">H", payload[7:9])[0]
            succesful_update_command_counter = payload[9]

            notifications.device_state(
                client_slot, timer_state, target_temperature,
                actual_temperature, outlet_state_1, outlet_state_2,
                remaining_seconds, succesful_update_command_counter)

        elif payload_length == 11 and payload[0] in [1, 0x80]:
            change_made = payload[0] == 1
            timer_state = payload[1]
            target_temperature = _convert_temperature_reverse(payload[3])
            actual_temperature = _convert_temperature_reverse(payload[5])
            outlet_state_1 = payload[6] == OUTLET_RUNNING
            outlet_state_2 = payload[7] == OUTLET_RUNNING
            remaining_seconds = struct.unpack(">H", payload[8:10])[0]
            succesful_update_command_counter = payload[10]

            notifications.controls_operated(
                client_slot, change_made, timer_state, target_temperature,
                actual_temperature, outlet_state_1, outlet_state_2,
                remaining_seconds, succesful_update_command_counter)

        elif payload_length == 11 and payload[0] in [0, 0x4, 0x8]:
            outlet_flag = payload[0]
            min_duration_seconds = payload[4]
            max_temperature = _convert_temperature_reverse(payload[6])
            min_temperature = _convert_temperature_reverse(payload[8])
            succesful_update_command_counter = payload[10]

            notifications.outlet_settings(
                client_slot, outlet_flag, min_duration_seconds,
                max_temperature, min_temperature,
                succesful_update_command_counter)

        elif payload_length == 16 and payload[0] == 0:
            valve_type = payload[1]
            valve_sw_version = payload[3]
            ui_type = payload[5]
            ui_sw_version = payload[7]
            bt_sw_version = payload[15]

            notifications.technical_information(
                client_slot, valve_type, valve_sw_version, ui_type,
                ui_sw_version, bt_sw_version)

        elif payload_length == 16 and payload[0] != 0:
            nickname = payload.decode('UTF-8')
            notifications.nickname(client_slot, nickname)

        elif payload_length == 20:
            client_name = payload.decode('UTF-8')
            notifications.client_details(client_slot, client_name)

        elif payload_length == 24:
            preset_slot = payload[0]
            target_temperature = _convert_temperature_reverse(payload[2])
            duration_seconds = payload[4]
            outlet_enabled = _bits_to_list(payload[5], 8)
            preset_name = payload[8:].decode('UTF-8')

            notifications.preset_details(
                client_slot, preset_slot, target_temperature, duration_seconds,
                outlet_enabled, preset_name)

    def get_device_info(self):
        device_name = self._read(UUID_DEVICE_NAME).decode('UTF-8')
        manufacturer = self._read(UUID_MANUFACTURER).decode('UTF-8')
        model_number = self._read(UUID_MODEL_NUMBER).decode('UTF-8')

        return (device_name, manufacturer, model_number)

    def request_client_details(self, client_slot):
        payload = bytearray([self._client_slot, 0x6b, 1, 0x10 + client_slot])
        self._write(_get_payload_with_crc(payload, self._client_id))

    def request_client_slots(self):
        payload = bytearray([self._client_slot, 0x6b, 1, 0])
        self._write(_get_payload_with_crc(payload, self._client_id))

    def request_device_settings(self):
        payload = bytearray([self._client_slot, 0x3e, 0])
        self._write(_get_payload_with_crc(payload, self._client_id))

    def request_device_state(self):
        payload = bytearray([self._client_slot, 0x7, 0])
        self._write(_get_payload_with_crc(payload, self._client_id))

    def request_nickname(self):
        payload = bytearray([self._client_slot, 0x44, 0])
        self._write(_get_payload_with_crc(payload, self._client_id))

    def request_outlet_settings(self):
        payload = bytearray([self._client_slot, 0x10, 0])
        self._write(_get_payload_with_crc(payload, self._client_id))

    def request_preset_details(self, preset_slot):
        payload = bytearray([self._client_slot, 0x30, 1, 0x40 + preset_slot])
        self._write(_get_payload_with_crc(payload, self._client_id))

    def request_preset_slots(self):
        payload = bytearray([self._client_slot, 0x30, 1, 0x80])
        self._write(_get_payload_with_crc(payload, self._client_id))

    def request_technical_info(self):
        payload = bytearray([self._client_slot, 0x32, 1, 1])
        self._write(_get_payload_with_crc(payload, self._client_id))

    def pair_client(self, new_client_id, client_name):
        new_client_id_bytes = struct.pack(">I", new_client_id)
        client_name_bytes = client_name.encode("UTF-8")

        if len(client_name_bytes) > 20:
            raise Exception("The client name is too long")

        client_name_bytes += bytearray([0] * (20 - len(client_name_bytes)))

        payload = (bytearray([0, 0xeb, 24]) + new_client_id_bytes +
                   client_name_bytes)
        self._write_chunks(_get_payload_with_crc(payload, MAGIC_ID))

    def unpair_client(self, client_slot_to_unpair):
        payload = bytearray(
            [self._client_slot, 0xeb, 1, client_slot_to_unpair])
        self._write(_get_payload_with_crc(payload, self._client_id))

    def control_outlets(self, outlet1, outlet2, temperature):
        payload = bytearray([
            self._client_slot,
            0x87, 0x05,
            TIMER_RUNNING if outlet1 or outlet2 else TIMER_PAUSED,
            1,
            _convert_temperature(temperature),
            OUTLET_RUNNING if outlet1 else OUTLET_STOPPED,
            OUTLET_RUNNING if outlet2 else OUTLET_STOPPED])
        self._write(_get_payload_with_crc(payload, self._client_id))

    def start_preset(self, preset_slot):
        payload = bytearray([self._client_slot, 0xb1, 1, preset_slot])
        self._write(_get_payload_with_crc(payload, self._client_id))
