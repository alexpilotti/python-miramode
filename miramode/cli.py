import argparse
import logging
import random
import sys
import threading

import miramode

CMD_LIST_DEVICES = "devices-list"
CMD_LIST_CLIENTS = "client-list"
CMD_PAIR_CLIENT = "client-pair"
CMD_UNPAIR_CLIENT = "client-unpair"
CMD_CONTROL_OUTLETS = "outlets-control"


def _valid_outlet_status(value):
    if value.lower() == "on":
        return True
    elif value.lower() == "off":
        return False
    else:
        raise argparse.ArgumentTypeError(
            f'"{value}" is not a valid outlet status. Valid values are "on" '
            'or "off"')


def _valid_temperature(value):
    try:
        float_val = float(value)
        if float_val < 0 or float_val >= 100:
            raise argparse.ArgumentTypeError(f"{value} is out of range")
        return float_val
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value} is not a valid number.")


def _valid_client_id(value):
    try:
        int_val = int(value)
        if int_val < 1 or int_val >= (1 << 32) or int_val == miramode.MAGIC_ID:
            raise argparse.ArgumentTypeError(f"{value} is out of range")
        return int_val
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value} is not a valid number.")


def _add_common_args(parser):
    parser.add_argument(
        '--debug', required=False,
        action='store_true',
        help="Set debug logging level")


def _add_address_args(parser):
    _add_common_args(parser)
    parser.add_argument(
        "-a", "--address", required=True,
        type=str,
        help="The BLE address of the device")


def _add_client_args(parser):
    _add_address_args(parser)
    parser.add_argument(
        "-c", "--client-id", required=True,
        type=_valid_client_id,
        help="A previously paired client id")
    parser.add_argument(
        "-s", "--client-slot", required=True,
        type=int,
        help="The client slot corresponding to the client id")


def _add_pair_client_args(parser):
    parser.add_argument(
        "-c", "--client-id", required=False,
        type=_valid_client_id,
        help="The new client id, leave empty to generate a random value")
    parser.add_argument(
        "-n", "--client-name", required=True,
        help="The name to assign to the new client")


def _add_unpair_client_args(parser):
    parser.add_argument(
        "-u", "--client-slot-to-unpair", required=True,
        type=int,
        help="The client slot to unpair")


def _add_control_outlets_args(parser):
    parser.add_argument(
        "-o1", "--outlet1", required=False,
        type=_valid_outlet_status, default=False,
        help="Turn on or off the first outlet")
    parser.add_argument(
        "-o2", "--outlet2", required=False,
        type=_valid_outlet_status, default=False,
        help="Turn on or off the second outlet")
    parser.add_argument(
        "-t", "--temperature", required=True,
        type=_valid_temperature,
        help="The target temperature")


def _parse_args():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(
        dest='command', required=True, help="Available commands")

    list_devices_parser = subparsers.add_parser(
        CMD_LIST_DEVICES, help="List devices",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    _add_common_args(list_devices_parser)

    list_clients_parser = subparsers.add_parser(
        CMD_LIST_CLIENTS, help="List clients",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    _add_client_args(list_clients_parser)

    pair_client_parser = subparsers.add_parser(
        CMD_PAIR_CLIENT, help="Pair a new client",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    _add_address_args(pair_client_parser)
    _add_pair_client_args(pair_client_parser)

    unpair_client_parser = subparsers.add_parser(
        CMD_UNPAIR_CLIENT, help="Unpair an existing client",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    _add_client_args(unpair_client_parser)
    _add_unpair_client_args(unpair_client_parser)

    control_outlets_parser = subparsers.add_parser(
        CMD_CONTROL_OUTLETS, help="Turn on or off the outlets",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    _add_client_args(control_outlets_parser)
    _add_control_outlets_args(control_outlets_parser)

    # If no arguments are provided, print help
    if len(sys.argv) == 1:
        parser.print_help()
        for choice in subparsers.choices:
            print(f"\n{choice}\n")
            subparsers.choices[choice].print_help()
    else:
        return parser.parse_args()


class Notifications(miramode.NotificationsBase):
    def __init__(self, event, is_pairing=False):
        self._event = event
        self._is_pairing = is_pairing

    def client_details(self, client_slot, client_name):
        print(f"{client_name}")
        self._event.set()

    def controls_operated(
            self, client_slot, change_made, timer_state, target_temperature,
            actual_temperature, outlet_state_1, outlet_state_2,
            remaining_seconds, succesful_update_command_counter):
        print(f"The command completed successfully")
        self._event.set()

    def slots(self, client_slot, slots):
        self.slots = slots
        self._event.set()

    def success_or_failure(self, client_slot, status):
        if status == miramode.FAILURE:
            print(f"The command failed")
        elif self._is_pairing:
            print(f"Assigned client slot: {status}")
        elif status == miramode.SUCCESS:
            print(f"The command completed successfully")
        else:
            raise Exception(f"Unrecognized status: {status}")
        self._event.set()


def _process_list_devices_command(args):
    for name, address in miramode.get_available_devices():
        print(f"{name}: {address}")


def _process_list_clients_command(args):
    with miramode.Connnection(
            args.address, args.client_id, args.client_slot) as conn:

        event = threading.Event()
        notifications = Notifications(event)
        conn.subscribe(notifications)

        conn.request_client_slots()
        event.wait()
        event.clear()

        for slot in notifications.slots:
            print(f"Requesting details for client slot: {slot}")
            conn.request_client_details(slot)
            event.wait()
            event.clear()


def _process_pair_client_command(args):
    with miramode.Connnection(args.address) as conn:

        event = threading.Event()
        notifications = Notifications(event, is_pairing=True)
        conn.subscribe(notifications)

        new_client_id = args.client_id
        if not new_client_id:
            max_client_id = (1 << 16) - 1
            new_client_id = random.randint(10000, max_client_id)

        print(f"Pairing new client id: {new_client_id}, "
              f"name: {args.client_name}")

        conn.pair_client(new_client_id, args.client_name)
        event.wait()
        event.clear()


def _process_unpair_client_command(args):
    with miramode.Connnection(
            args.address, args.client_id, args.client_slot) as conn:

        event = threading.Event()
        notifications = Notifications(event)
        conn.subscribe(notifications)

        conn.unpair_client(args.client_slot_to_unpair)
        event.wait()
        event.clear()


def _process_control_outlets_command(args):
    with miramode.Connnection(
            args.address, args.client_id, args.client_slot) as conn:

        event = threading.Event()
        notifications = Notifications(event)
        conn.subscribe(notifications)

        conn.control_outlets(args.outlet1, args.outlet2, args.temperature)
        event.wait()
        event.clear()


def _setup_logging(debug):
    level = logging.DEBUG if debug else logging.WARN
    logging.basicConfig(stream=sys.stdout, level=level)


def main():
    args = _parse_args()
    if not args:
        sys.exit(0)

    _setup_logging(args.debug)

    if args.command == CMD_LIST_DEVICES:
        _process_list_devices_command(args)
    elif args.command == CMD_LIST_CLIENTS:
        _process_list_clients_command(args)
    elif args.command == CMD_PAIR_CLIENT:
        _process_pair_client_command(args)
    elif args.command == CMD_UNPAIR_CLIENT:
        _process_unpair_client_command(args)
    elif args.command == CMD_CONTROL_OUTLETS:
        _process_control_outlets_command(args)


if __name__ == '__main__':
    main()
