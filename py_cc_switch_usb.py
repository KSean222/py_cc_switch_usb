import os
import time
import usb.core
import usb.util
import py_cold_clear as py_cc
from gen import cc_protobuf_pb2 as cc_pb
import ctypes

def proto_to_value(proto, value) -> None:
    value_type = type(value)
    if issubclass(value_type, ctypes.Array):
        for i, element in enumerate(proto):
            value[i] = proto_to_value(element, value[i])
        return value
    elif issubclass(value_type, ctypes.Structure):
        for name, _ in value_type._fields_:
            source = getattr(proto, name)
            dest = getattr(value, name)
            setattr(value, name, proto_to_value(source, dest))
        return value
    else:
        return proto

def value_to_proto(value, proto) -> None:
    value_type = type(value)
    if issubclass(value_type, ctypes.Array):
        if hasattr(proto, "add"):
            for element in value:
                value_to_proto(element, proto.add())
        else:
            proto.extend(value)
        return None
    elif issubclass(value_type, ctypes.Structure):
        for name, _ in value_type._fields_:
            source = getattr(value, name)
            dest = getattr(proto, name)
            result = value_to_proto(source, dest)
            if result != None:
                setattr(proto, name, result)
        return None
    else:
        return value

class CCSwitchUsb:
    def __init__(self):
        self._dev = None
        self._out = None
        self._in = None
        self._handles = {}

    def try_connect(self, vendor_id = 0x057E, product_id = 0x3000):
        self._dev = usb.core.find(idVendor=vendor_id, idProduct=product_id)
        if self._dev is not None:
            try:
                self._dev.set_configuration()
                intf = self._dev.get_active_configuration()[(0, 0)]
                self._out = usb.util.find_descriptor(intf, custom_match=lambda e:usb.util.endpoint_direction(e.bEndpointAddress)==usb.util.ENDPOINT_OUT)
                self._in = usb.util.find_descriptor(intf, custom_match=lambda e:usb.util.endpoint_direction(e.bEndpointAddress)==usb.util.ENDPOINT_IN)
                return True
            except:
                return False
        else:
            return False

    def new_handle(self, buf):
        args = cc_pb.NewHandleArgs()
        args.ParseFromString(buf)
        
        options = py_cc.CCOptions()
        proto_to_value(args.options, options)

        weights = py_cc.CCWeights()
        proto_to_value(args.weights, weights)

        handle = py_cc.CCHandle.launch(options, weights)
        handle_id = id(handle)
        self._handles[handle_id] = handle
        return cc_pb.NewHandleResult(handle_id = handle_id)

    def terminate_handle(self, buf):
        args = cc_pb.TerminateHandleArgs()
        args.ParseFromString(buf)

        self._handles.pop(args.handle_id).terminate()
        return cc_pb.TerminateHandleResult()

    def reset(self, buf):
        args = cc_pb.ResetArgs()
        args.ParseFromString(buf)

        field = (args.field[x:x+10] for x in range(0, 40, 10))
        self._handles[args.handle_id].reset(field, args.b2b, args.combo)
        return cc_pb.ResetResult()

    def add_next_piece(self, buf):
        args = cc_pb.AddNextPieceArgs()
        args.ParseFromString(buf)

        self._handles[args.handle_id].add_next_piece(args.piece)
        return cc_pb.AddNextPieceResult()

    def request_next_move(self, buf):
        args = cc_pb.RequestNextMoveArgs()
        args.ParseFromString(buf)

        self._handles[args.handle_id].request_next_move(args.incoming)
        return cc_pb.RequestNextMoveResult()

    def poll_next_move(self, buf):
        args = cc_pb.PollNextMoveArgs()
        args.ParseFromString(buf)

        status, move, plan = self._handles[args.handle_id].poll_next_move(args.plan_length)

        result = cc_pb.PollNextMoveResult(status = status)
        if status == py_cc.CCBotPollStatus.MOVE_PROVIDED:
            value_to_proto(move, result.move)
            for placement in plan:
                value_to_proto(placement, result.plan.add())
        return result

    def block_next_move(self, buf):
        args = cc_pb.BlockNextMoveArgs()
        args.ParseFromString(buf)

        status, move, plan = self._handles[args.handle_id].block_next_move(args.plan_length)

        result = cc_pb.BlockNextMoveResult(status = status)
        if status == py_cc.CCBotPollStatus.MOVE_PROVIDED:
            value_to_proto(move, result.move)
            for placement in plan:
                value_to_proto(placement, result.plan.add())
        return result

    def handle_commands(self, dbg = None):
        if dbg == None:
            while not self.try_connect():
                print("Failed to connect.")
                print("Attempting to reconnect in 5 seconds...")
                time.sleep(5)
                print("Connected to Switch Successfully!")
        else:
            self._in = dbg
            self._out = dbg

        py_cc.init("./cold_clear." + ("dll" if os.name == "nt" else "so"))
        
        commands = [
            self.new_handle,
            self.terminate_handle,
            self.reset,
            self.add_next_piece,
            self.request_next_move,
            self.poll_next_move,
            self.block_next_move
        ]

        while True:
            command = self._in.read(1, timeout=0).tobytes()[0]
            size = int.from_bytes(self._in.read(4, timeout=0).tobytes(), byteorder="big")
            data = commands[command](self._in.read(size, timeout=0).tobytes()).SerializeToString()
            self._out.write(len(data).to_bytes(4, "big"))
            self._out.write(data)

if __name__ == "__main__":
    CCSwitchUsb().handle_commands()