import os
import sys
import py_cc_switch_usb as cc_usb
import py_cold_clear as py_cc
from gen import cc_protobuf_pb2 as cc_pb
from collections import deque
import random
import time

def io(rx):
    def read():
        size = int.from_bytes((rx.pop() for _ in range(4)), "big")
        return bytes(rx.pop() for _ in range(size))

    def command(id, proto):
        data = proto.SerializeToString()
        return id.to_bytes(1, "big") + len(data).to_bytes(4, "big") + data

    result = None

    def new_handle(options, weights):
        nonlocal result
        handle_args = cc_pb.NewHandleArgs()
        cc_usb.value_to_proto(py_cc.CCOptions.default(), handle_args.options)
        cc_usb.value_to_proto(py_cc.CCWeights.default(), handle_args.weights)
        yield command(0, handle_args)
        result = cc_pb.NewHandleResult()
        result.ParseFromString(read())
        result = result.handle_id

    def terminate_handle(bot):
        nonlocal result
        args = cc_pb.TerminateHandleArgs()
        args.handle_id = bot
        yield command(1, args)
        result = cc_pb.TerminateHandleResult()
        result.ParseFromString(read())
        result = None

    def request_next_move(bot, incoming):
        nonlocal result
        args = cc_pb.RequestNextMoveArgs()
        args.handle_id = bot
        args.incoming = incoming
        yield command(4, args)
        result = cc_pb.RequestNextMoveResult()
        result.ParseFromString(read())
        result = None

    def add_next_piece(bot, piece):
        nonlocal result
        args = cc_pb.AddNextPieceArgs()
        args.handle_id = bot
        args.piece = piece
        yield command(3, args)
        result = cc_pb.AddNextPieceResult()
        result.ParseFromString(read())
        result = None

    def block_next_move(bot, plan_length = 0):
        nonlocal result
        args = cc_pb.BlockNextMoveArgs()
        args.handle_id = bot
        args.plan_length = plan_length
        yield command(6, args)
        result = cc_pb.BlockNextMoveResult()
        result.ParseFromString(read())
        result = (result.status, result.move, result.plan)

    yield from new_handle(py_cc.CCOptions.default(), py_cc.CCOptions.default())
    bot = result
    field = [[False for x in range(10)] for y in range(40)]
    queue = deque()
    bag = list(py_cc.CCPiece)
    random.shuffle(bag)
    while len(queue) < 5:
        piece = bag.pop()
        queue.append(piece)
        yield from add_next_piece(bot, piece)
    hold = None
    while True:
        time.sleep(0.5)
        yield from request_next_move(bot, 0)

        yield from block_next_move(bot, 0)
        status, move, plan = result
        if status == py_cc.CCBotPollStatus.DEAD:
            print("Oh no! Cold Clear died.")
            break

        if move.hold:
            prev_hold = hold
            hold = queue.popleft()
            if prev_hold == None:
                queue.popleft()
        else:
            queue.popleft()

        while len(queue) < 5:
            if len(bag) == 0:
                bag = list(py_cc.CCPiece)
                random.shuffle(bag)
            piece = bag.pop()
            queue.append(piece)
            yield from add_next_piece(bot, piece)

        for i in range(4):
            field[move.expected_y[i]][move.expected_x[i]] = True

        field = [row for row in field if not all(row)]
        while len(field) < 40:
            field.append([False for x in range(10)])

        for y in reversed(range(20)):
            for cell in field[y]:
                print("[]" if cell else "..", end="")
            print()
            
        hold_char = " "
        if hold != None:
            hold_char = hold.name
        print(f"H: [{hold_char}] Q: [", end="")
        for i, piece in enumerate(queue):
            if i < 5:
                if i > 0:
                    print(", ", end="")
                print(piece.name, end="")
            else:
                break
        print("]")
        print()
    yield from terminate_handle(bot)
    

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