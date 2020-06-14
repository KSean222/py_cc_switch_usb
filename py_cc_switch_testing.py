import os
import sys
import py_cc_switch_usb as cc_usb
import py_cold_clear as py_cc
from gen import cc_protobuf_pb2 as cc_pb
from collections import deque

def io(rx):
    def read():
        size = int.from_bytes((rx.pop() for _ in range(4)), "big")
        return bytes(rx.pop() for _ in range(size))

    def command(id, proto):
        data = proto.SerializeToString()
        return id.to_bytes(1, "big") + len(data).to_bytes(4, "big") + data

    handle_args = cc_pb.NewHandleArgs()
    cc_usb.value_to_proto(py_cc.CCOptions.default(), handle_args.options)
    cc_usb.value_to_proto(py_cc.CCWeights.default(), handle_args.weights)
    yield command(0, handle_args)
    handle_result = cc_pb.NewHandleResult()
    handle_result.ParseFromString(read())
    print("Created new handle", handle_result.handle_id)

    terminate_handle_args = cc_pb.TerminateHandleArgs()
    terminate_handle_args.handle_id = handle_result.handle_id
    yield command(1, terminate_handle_args)
    print("Terminated handle")

class ToBytesWrapper:
    def __init__(self, data):
        self.data = data

    def tobytes(self):
        return self.data

class DebugIO:
    _write_buffer = deque()
    _read_buffer = deque()
    _io_iter = io(_write_buffer)

    @staticmethod
    def read(size, **kwargs):
        buffer = []
        while len(buffer) < size:
            if len(DebugIO._read_buffer) == 0:
                DebugIO._read_buffer.extendleft(next(DebugIO._io_iter))
            buffer.append(DebugIO._read_buffer.pop())
        return ToBytesWrapper(bytes(buffer))

    @staticmethod
    def write(data):
        DebugIO._write_buffer.extendleft(data)

py_cc.init("./cold_clear." + ("dll" if os.name == "nt" else "so"))
cc_usb.CCSwitchUsb().handle_commands(DebugIO)