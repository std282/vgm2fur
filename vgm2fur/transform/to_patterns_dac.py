from typing import NamedTuple
from math import ceil
from .tabulate import DataBlock
from vgm2fur import AppError as Vgm2FurError
from vgm2fur import bitfield, furnace

class YM2612DAC:
    def __init__(self, data):
        self.data = data
    def cut(self, play):
        return self.data[play.begin : play.begin + play.length]

class UnknownBlock(NamedTuple):
    type: int
    payload: bytes

class InvalidCompParams(Vgm2FurError):
    def __init__(self, n, tt, st):
        super().__init__(n, tt, st)
        self.n = n
        self.tt = tt
        self.st = st
    def __str__(self):
        return f'invalid compression params on block #{self.n}: tt={self.tt}, st={self.st}'

class NoDictionary(Vgm2FurError):
    def __init__(self, n, tt, st):
        super().__init__(n, tt, st)
        self.n = n
        self.tt = tt
        self.st = st
    def __str__(self):
        return f'no dictionary for block #{self.n}: tt={self.tt}, st={self.st}'

def collect_stuff(dac, datablocks, instr_start):
    sample_bank = None
    for block in _resolve(datablocks):
        match block:
            case YM2612DAC():
                sample_bank = block
    if sample_bank is None:
        return None, None, None
    instr_no = instr_start
    note = furnace.notes.C0
    MAP_CAPACITY = 120
    mapping = {}
    samples = []
    instrs = []
    for play in dac:
        pos = (play.begin, play.length)
        if pos not in mapping:
            mapping[pos] = (note, instr_no)
            if note < furnace.notes.B9:
                note += 1
            else:
                note = furnace.notes.C0
                instr_no += 1
                instrs.append(_sample_map(sample_start, MAP_CAPACITY))
                sample_start += MAP_CAPACITY
            samples.append((sample_bank.cut(play), play.rate))
    if len(mapping) != 0:
        instrs.append(_sample_map(sample_start, note - furnace.notes.C0))
    return mapping, samples, instrs

def prepare(dac):
    for play in dac:
        yield (play.keyid, play.begin, play.length)

def to_patterns(dac, /, *, mapping, rowdur):
    keyid_c = -1
    left = -1
    for keyid, begin, length in dac:
        if keyid != keyid_c:
            note, ins = mapping[begin, length]
            left = (length + rowdur - 1) // rowdur
            yield furnace.Entry(note=note, ins=ins)
        else:
            if left > 0:
                yield furnace.Entry()
                left -= 1
            elif left == 0:
                yield furnace.Entry(note=furnace.notes.Off)
                left = -1
            else:
                yield furnace.Entry()

def _sample_map(first_sample, note_count):
    return range(first_sample, first_sample + note_count)

def _resolve(datablocks):
    maps = dict()
    for (n, datablock) in enumerate(datablocks):
        (type, payload) = datablock
        if 0x40 <= type and type <= 0x7E:
            tt = payload[0]
            bd = payload[5]
            bc = payload[6]
            st = payload[7]
            offset_start = int.from_bytes(payload[8:10], 'little')
            match (tt, st):
                case (0, 0):
                    payload = _decode_bitpack_low(payload[10:], bc, bd, offset_start)
                    yield _typed_data_block(type - 0x40, payload)
                case (0, 1):
                    payload = _decode_bitpack_high(payload[10:], bc, bd, offset_start)
                    yield _typed_data_block(type - 0x40, payload)
                case (0, 2):
                    try:
                        payload = _decode_bitpack_map(payload[10:], bc, bd, maps[tt, st])
                        yield _typed_data_block(type - 0x40, payload)
                    except KeyError:
                        raise NoDictionary(n, type, tt, st)
                case (1, 0):
                    try:
                        payload = _decode_dpcm(payload[10:], bc, bd, offset_start, maps[tt, st])
                        yield _typed_data_block(type - 0x40, payload)
                    except KeyError:
                        raise NoDictionary(n)
                case _:
                    raise InvalidCompParams(n, tt, st)
        elif type == 0x7F:
            tt = payload[0]
            st = payload[1]
            bd = payload[2]
            count = int.from_bytes(payload[4:6], 'little')
            size = (bd + 7) // 8
            payload = payload[6:]
            maps[tt, st] = [
                int.from_bytes(payload[i : i+size], 'little')
                for i in range(0, count * size, size)
            ]
        else:
            yield _typed_data_block(type, payload)

def _typed_data_block(type, payload):
    match type:
        case 0x00:
            return YM2612DAC(payload)
        case _:
            return UnknownBlock(type, payload)

def _decode_bitpack_low(enc, bc, bd, offset):
    dec = []
    for x in _bitstream(enc, bc):
        dec.append(x + offset)
    return dec

def _decode_bitpack_high(enc, bc, bd, offset):
    dec = []
    shift = bd - bc
    for x in _bitstream(enc, bc):
        dec.append((x << shift) + offset)
    return dec

def _decode_bitpack_map(enc, bc, bd, map):
    dec = []
    for x in _bitstream(enc, bc):
        dec.append(map[x])
    return dec

def _decode_dpcm(enc, bc, bd, start, map):
    dec = []
    x = start
    for dx in _bitstream(enc, bc):
        x += map[dx]
        dec.append(x)
    return dec

def _bitstream(enc, bc):
    n = bitfield.make(0)
    bits = 0
    for x in enc:
        n.all = (n.all << 8) + x
        bits += 8
        while bits >= bc:
            yield n[bits : bits-bc+1]
            bits -= bc
            n.all = n[bits : 0]
