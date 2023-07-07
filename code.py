import usb.core
import time
import struct
import usb_host
import board

import intellikeys_firmware

# There are three interfaces
# No subclass 0x81, 0x02
# Keyboard 0x83, 0x03
# Mouse 0x84

# USB defines
DIR_SHIFT = 7
DIR_OUT = 0 << DIR_SHIFT
DIR_IN = 1 << DIR_SHIFT

DESC_DEVICE = 0x01
DESC_CONFIGURATION = 0x02
DESC_STRING = 0x03
DESC_INTERFACE = 0x04

# No shift
REQ_RCPT_DEVICE = 0
REQ_RCPT_INTERFACE = 1
REQ_RCPT_ENDPOINT = 2
REQ_RCPT_OTHER = 3

REQ_TYPE_SHIFT = 5
REQ_TYPE_STANDARD = 0 << REQ_TYPE_SHIFT
REQ_TYPE_CLASS = 1 << REQ_TYPE_SHIFT
REQ_TYPE_VENDOR = 2 << REQ_TYPE_SHIFT
REQ_TYPE_INVALID = 3 << REQ_TYPE_SHIFT

REQ_GET_DESCRIPTOR = 6
REQ_SET_INTERFACE = 11

# EZUSB values
ANCHOR_LOAD_INTERNAL = 0xA0
ANCHOR_LOAD_EXTERNAL = 0xA3

# IntelliKeys values
CMD_BASE = 0
IK_CMD_GET_VERSION = (CMD_BASE + 1)
IK_CMD_LED = (CMD_BASE + 2)
IK_CMD_SCAN = (CMD_BASE + 3)
IK_CMD_TONE = (CMD_BASE + 4)
IK_CMD_GET_EVENT = (CMD_BASE + 5)
IK_CMD_INIT = (CMD_BASE + 6)
IK_CMD_EEPROM_READ = (CMD_BASE + 7)
IK_CMD_EEPROM_WRITE = (CMD_BASE + 8)
IK_CMD_ONOFFSWITCH = (CMD_BASE + 9)
IK_CMD_CORRECT = (CMD_BASE + 10)
IK_CMD_EEPROM_READBYTE = (CMD_BASE + 11)
IK_CMD_RESET_DEVICE = (CMD_BASE + 12)
IK_CMD_START_AUTO = (CMD_BASE + 13)
IK_CMD_STOP_AUTO = (CMD_BASE + 14)
IK_CMD_ALL_LEDS = (CMD_BASE + 15)
IK_CMD_START_OUTPUT = (CMD_BASE + 16)
IK_CMD_STOP_OUTPUT = (CMD_BASE + 17)
IK_CMD_ALL_SENSORS = (CMD_BASE + 18)

CPUCS_REG = 0x7F92

def ezusb_load_xfer(bRequest: int, addr: int, buf: ReadableBuffer):
    device.ctrl_transfer(REQ_RCPT_DEVICE | REQ_TYPE_VENDOR | DIR_OUT, bRequest, wValue=addr, wIndex=0, data_or_wLength=buf)


def ezusb_8051_reset(reset: bool):
    buf = b"\x01" if reset else b"\x00"
    ezusb_load_xfer(ANCHOR_LOAD_INTERNAL, CPUCS_REG, buf)

def is_ram_address(address) -> bool:
    return address <= 0x1b3f

def download_hex(buffer):
    offset = 0
    buffer = memoryview(buffer)
    for internal_ram in (True, False):
        bRequest = ANCHOR_LOAD_INTERNAL if internal_ram else ANCHOR_LOAD_EXTERNAL
        while offset < len(buffer):
            length, address, record_type = struct.unpack_from(">BHB", buffer, offset=offset)
            if record_type != 0:
                break
            if is_ram_address(address) != internal_ram:
                continue
            offset += 4
            ezusb_load_xfer(bRequest, address, buffer[offset: offset + length])
            offset += length
        if internal_ram:
            ezusb_8051_reset(True)

def get_descriptor_into(dtype, index, language_id, buffer: ReadableBuffer):
    wValue = dtype << 8 | index
    wIndex = language_id
    device.ctrl_transfer(REQ_RCPT_DEVICE | REQ_TYPE_STANDARD | DIR_IN, REQ_GET_DESCRIPTOR, wValue=wValue, wIndex=wIndex, data_or_wLength=buffer)

def hid_send_report(index, buffer, report_id = 0):
    endpoint = 0x02 if index == 0 else 0x03
    if report_id > 0:
        report = bytearray(len(buffer) + 1)
        report[0] = report_id
        report[1:] = buffer
    else:
        report = buffer
    device.write(endpoint, report)

def post_command(command, data=0):
    buf = bytearray(8)
    buf[0] = command
    buf[1] = data
    print("command", command, data)
    hid_send_report(0, buf)
    print("sent")
    device.read(0x82, buf, timeout=2)
    print("read", buf)

usb_host_port = usb_host.Port(board.D11, board.D12)
print('hello')
device = None
while True:
    while device is None:
        for d in usb.core.find(True):
            print(hex(d.idVendor), hex(d.idProduct))
            if d.idVendor == 0x095e:
                device = d
                break

    if device.idProduct == 0x0100:
        device.ctrl_transfer(REQ_RCPT_DEVICE | REQ_TYPE_STANDARD | DIR_OUT, REQ_SET_INTERFACE, 0, 0)

        print("Loading loader")
        ezusb_8051_reset(True)
        # Load the loader
        download_hex(intellikeys_firmware.LOADER)
        ezusb_8051_reset(False)

        # Load the external firmware
        print("Loading firmware")
        download_hex(intellikeys_firmware.FIRMWARE)
        ezusb_8051_reset(True)
        ezusb_8051_reset(False)

        print("firmware loaded")
        device = None
        time.sleep(2)
    elif device.idProduct == 0x0101:
        print("Re-enumerated with loaded firmware")
        b = bytearray(38)
        get_descriptor_into(DESC_STRING, 1, 0, b)
        print(struct.unpack_from("<B", b, offset=0))
        print(b[2:].decode("utf-8"))
        get_descriptor_into(DESC_STRING, 2, 0, b)
        print(struct.unpack_from("<B", b, offset=0))
        print(b[2:32].decode("utf-8"))
        get_descriptor_into(DESC_DEVICE, 0, 0, b)
        print("device descriptor", b[:b[0]])
        config_buf = bytearray(98)
        get_descriptor_into(DESC_CONFIGURATION, 0, 0, config_buf)
        print("configuration descriptor", config_buf)

        mv = memoryview(bytearray(55))
        print("(")
        for i, l in enumerate((28, 55, 44)):
            get_descriptor_into(0x22, i, 0, mv[:l])
            print(bytes(mv[:l]), " + ")

        post_command(IK_CMD_INIT, 0)
        post_command(IK_CMD_SCAN, 1)
        time.sleep(0.25)
        post_command(IK_CMD_ALL_SENSORS)
        post_command(IK_CMD_GET_VERSION)

        while True:
            pass
