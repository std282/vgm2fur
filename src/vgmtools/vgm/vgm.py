"""VGM module interface.

Classes:
    VGM - interface to VGM file content

Exceptions:
    BadVgmFile - not a VGM file
    UnexpectedEOF - when attempting to read more than there is

Functions:
    load - load VGM file content from actual file
"""

from typing import Iterable
from functools import cached_property
import struct
import warnings
import gzip
import bitfield

Command = tuple[int, ...]
DataBlock = tuple[int, bytes]

class VGM:
    """Provides interface to VGM file content.

    Variables:
        data - VGM file content as bytes

    Properties:
        commands - VGM commands as a list of tuples
        datablocks - VGM data blocks as a list of tuples
        version - VGM file format version
        rate - playback rate in Hz
        csv - CSV representation as a set of lines
    """

    def __init__(self, data: bytes, /):
        """Initialize the module object.
        
        Positional arguments:
            data - entire VGM file data, not compressed

        Exceptions:
            PreambleMismatch - when data has no VGM preamble
        """
        self.data = data
        self.__commands = None
        self.__datablocks = None
        if self.__preamble != b'Vgm ':
            raise PreambleMismatch()

    @property
    def __preamble(self) -> bytes:
        """VGM format preamble."""
        return self.data[0:4]

    @property
    def version(self) -> int:
        """VGM format version."""
        return int.from_bytes(self.data[0x08:0x0C], 'little')

    @property
    def __data_offset(self) -> int:
        """VGM data offset, where all the commands are stored."""
        reloff = int.from_bytes(self.data[0x34:0x38], 'little')
        if reloff == 0:
            return 0x40
        else:
            return 0x34 + reloff

    @property
    def commands(self) -> list[Command]:
        """Returns list of VGM commands.

        Each command is a tuple. First element of a command is a command number,
        which determines the length of a tuple and its content.
        """
        if self.__commands is not None:
            return self.__commands
        self.__commands = []
        self.__datablocks = []
        walker = ByteWalker(self.data, self.__data_offset)
        datablock_dicts = {}
        while not (done := False):
            cmd = walker.byte()
            match COMMAND_ARGS_SPEC.get(cmd):
                case Fixed(''):
                    self.__commands.append((cmd,))
                case Fixed(fmt):
                    self.__commands.append((cmd,) + walker.unpack(fmt))
                case Special(x) if 0x41 <= x and x <= 0x4E:
                    if self.version >= 0x160:
                        self.__commands.append((cmd,) + walker.unpack('<BB'))
                    else:
                        self.__commands.append((cmd, walker.byte()))
                case Special(0x66):
                    done = True
                case Special(0x67):
                    if (x := walker.byte()) != 0x66:
                        warnings.warn(f'expected byte 0x66 after 0x67, got 0x{x:02X}')
                    type, length = walker.unpack('<BL')
                    data = walker.bytes(length)
                    datablock = handle_data_block(type, data, datablock_dicts)
                    if datablock is not None:
                        type, data = datablock
                        self.__datablocks.append(type, data)
                case Special(0x68):
                    if (x := walker.byte()) != 0x66:
                        warnings.warn(f'expected byte 0x66 after 0x68, got 0x{x:02X}')
                    type = walker.byte()
                    readoff = int.from_bytes(walker.bytes(3), 'little')
                    writeoff = int.from_bytes(walker.bytes(3), 'little')
                    size = int.from_bytes(walker.bytes(3), 'little')
                    if size == 0:
                        size = 0x0100_0000
                    self.__commands.append((cmd, type, readoff, writeoff, size))
                case _:
                    warnings.warn(f'unknown VGM command: 0x{cmd:02X}')

    @property
    def datablocks(self) -> list[DataBlock]:
        """List of data blocks.

        Each data block is a tuple. First element of a tuple is a data block
        type, second element is data itself.
        """
        if self.__datablocks is None:
            _ = self.commands
        return self.__datablocks

    @property
    def csv(self) -> Iterable[str]:
        """Returns sequence of CSV lines that represent VGM commands."""
        def ym2612_ch(port: int, addr: int):
            """Decodes YM2612 channel number from port and address."""
            addr = bitfield.make(addr)
            if addr[1:0] == 0b11:
                return '?'
            else:
                return 1 + addr[1:0] + port * 3
        def ym2612_op(addr: int):
            """Decodes YM2612 channel operator number from address."""
            addr = bitfield.make(addr)
            return [1, 3, 2, 4][addr[3:2]]
        def ym2612_ch3_op(addr: int):
            """Decodes YM2612 channel 3 operator number from address."""
            addr = bitfield.make(addr)
            if addr[1:0] == 0b11:
                return '?'
            return [3, 1, 2][addr[1:0]]
        t = 0
        sn76489_lastch = 0
        yield 'Time,Chip,Channel,Data,Description'
        for com in self.commands:
            raw = com[0].to_bytes(1, 'little')
            match COMMAND_ARGS_SPEC.get(com[0]):
                case Fixed(fmt):
                    raw += struct.pack(fmt, *com[1:])
                case Special(x) if 0x41 <= x and x <= 0x4E:
                    if self.version >= 0x160:
                        raw += struct.pack('<BB', *com[1:])
                    else:
                        raw += struct.pack('<B', *com[1:])
                case Special(0x68):
                    raw += struct.pack('<BB', 0x66, cmd[1])
                    raw += cmd[2].to_bytes(3, 'little')
                    raw += cmd[3].to_bytes(3, 'little')
                    raw += (cmd[4] & 0xFFFFFF).to_bytes(3, 'little')
            raw = ' '.join(f'{x:02X}' for x in raw)
            wait = 0
            match cmd:
                case (0x52, addr, data) | (0x53, addr, data):
                    port = event[0] & 1
                    chip = 'YM2612'
                    d = bitfield.make(data)
                    match (port, addr):
                        case (0, 0x22):
                            channel = ''
                            if d[3]:
                                descr = f'LFO on ({d[2:0]})'
                            else:
                                descr = f'LFO off'
                        case (0, 0x27):
                            channel = 'FM3'
                            fm3mode = ['normal', 'special', 'CSM', '?']
                            descr = f'mode: {fm3mode[d[7:6]]}'
                        case (0, 0x28):
                            if d[1:0] == 3:
                                ch = '?'
                            else:
                                ch = 1 + d[1:0] % 4 + d[2] * 3
                            channel = f'FM{ch}'
                            opmask = d[7:4]
                            if opmask == 0:
                                descr = f'key off'
                            else:
                                descr = f'key on ({opmask:X})'
                        case (0, 0x2B):
                            res = 'enabled' if d[7] else 'disabled'
                            channel = 'DAC'
                            descr = f'DAC {res}'
                        case (p, a) if (a & 0xF0) == 0x30:
                            ch = ym2612_ch(port, addr)
                            op = ym2612_op(addr)
                            dt = d[5:4] if d[6] == 0 else -d[5:4]
                            channel = f'FM{ch}'
                            descr = f'operator {op}: multiply = {d[3:0]}; detune = {dt}'
                        case (p, a) if (a & 0xF0) == 0x40:
                            ch = ym2612_ch(port, addr)
                            op = ym2612_op(addr)
                            channel = f'FM{ch}'
                            descr = f'operator {op}: total level = {d[6:0]}'
                        case (p, a) if (a & 0xF0) == 0x50:
                            ch = ym2612_ch(port, addr)
                            op = ym2612_op(addr)
                            channel = f'FM{ch}'
                            descr = f'operator {op}: attack rate = {d[4:0]}; rate scaling = {d[6:0]}'
                        case (p, a) if (a & 0xF0) == 0x60:
                            ch = ym2612_ch(port, addr)
                            op = ym2612_op(addr)
                            channel = f'FM{ch}'
                            descr = f'operator {op}: decay rate = {d[4:0]}; AM '
                            if d[7]:
                                descr += 'enabled'
                            else:
                                descr += 'disabled'
                        case (p, a) if (a & 0xF0) == 0x70:
                            ch = ym2612_ch(port, addr)
                            op = ym2612_op(addr)
                            channel = f'FM{ch}'
                            descr = f'operator {op}: sustain rate = {d[4:0]}'
                        case (p, a) if (a & 0xF0) == 0x80:
                            ch = ym2612_ch(port, addr)
                            op = ym2612_op(addr)
                            channel = f'FM{ch}'
                            descr = f'operator {op}: release rate = {d[3:0]}; sustain level = {d[7:4]}'
                        case (p, a) if (a & 0xF0) == 0x90:
                            ch = ym2612_ch(port, addr)
                            op = ym2612_op(addr)
                            channel = f'FM{ch}'
                            if d[3]:
                                descr = f'operator {op}: SSG on ({d[2:0]})'
                            else:
                                descr = f'operator {op}: SSG off'
                        case (p, a) if (a & 0xFC) == 0xA0:
                            ch = ym2612_ch(port, addr)
                            channel = f'FM{ch}'
                            descr = f'frequency = 0x_{d[7:0]:02X}'
                        case (p, a) if (a & 0xFC) == 0xA4:
                            ch = ym2612_ch(port, addr)
                            channel = f'FM{ch}'
                            descr = f'frequency = 0x{d[2:0]:X}__; block = {d[5:3]}'
                        case (0, a) if (a & 0xFC) == 0xA8:
                            op = ym2612_ch3_op(addr)
                            channel = 'FM3'
                            descr = f'operator {op}: frequency = 0x_{d[7:0]:02X}'
                        case (0, a) if (a & 0xFC) == 0xAC:
                            op = ym2612_ch3_op(addr)
                            channel = 'FM3'
                            descr = f'operator {op}: frequency = 0x{d[2:0]:X}__; block = {d[5:3]}'
                        case (p, a) if (a & 0xFC) == 0xB0:
                            ch = ym2612_ch(port, addr)
                            channel = f'FM{ch}'
                            descr = f'algorithm {d[2:0]}; feedback = {d[5:3]}'
                        case (p, a) if (a & 0xFC) == 0xB4:
                            ch = ym2612_ch(port, addr)
                            channel = f'FM{ch}'
                            pan = ['?', 'right', 'left', 'center'][d[7:6]]
                            descr = f'AMS = {d[2:0]}; PMS = {d[5:4]}; panning = {pan}'
                        case _:
                            channel = ''
                            descr = 'unrecognized command'
                case (0x50, data):
                    chip = 'SN76489'
                    d = bitfield.make(data)
                    ch = d[6:5]
                    if d[7]:
                        if d[4]:
                            descr = f'volume {d[3:0]}'
                        elif d[6:5] != 3:
                            descr = f'period = 0x__{d[3:0]:X}'
                            sn76489_lastch = ch
                        else:
                            descr = f'mode = {d[2:0]}'
                    else:
                        ch = sn76489_lastch
                        descr = f'period = 0x{d[5:0]:02X}_'
                    if ch == 3:
                        channel = 'Noise'
                    else:
                        ch += 1
                        channel = f'PSG{ch}'
                case (0x61, pause):
                    chip = 'Pause'
                    channel = ''
                    wait = pause
                    descr = f'wait {wait} samples'
                case (0x62,):
                    chip = 'Pause'
                    channel = ''
                    wait = 735
                    descr = f'wait {wait} samples'
                case (0x63,):
                    chip = 'Pause'
                    channel = ''
                    wait = 882
                    descr = f'wait {wait} samples'
                case (x,) if x in irange(0x70, 0x7F):
                    chip = 'Pause'
                    channel = ''
                    wait = x - 0x70 + 1
                    descr = f'wait {wait} samples'
                case (x,) if x in irange(0x80, 0x8F):
                    chip = 'YM2612'
                    channel = 'DAC'
                    wait = x - 0x80
                    if wait == 0:
                        descr = 'play sample'
                    else:
                        descr = f'play sample and wait {wait} samples'
                case (0x68, chip, readoff, writeoff, size):
                    chip = 'PCM RAM'
                    channel = ''
                    descr = f'chip = {chip}; size = {size} bytes; read from 0x{readoff:06X}; write to 0x{writeoff:06X}'
                case (0x90, id, chip, port, com):
                    chip = 'Stream Control'
                    channel = f'ID{id}'
                    descr = f'setup stream: chip = {chip}; port = 0x{port:02X}; command/register = 0x{com:02X}'
                case (0x91, id, bank, step, start):
                    chip = 'Stream Control'
                    channel = f'ID{id}'
                    descr = f'set stream data: bank = {bank}; step = {step}; start = {start}'
                case (0x92, id, freq):
                    chip = 'Stream Control'
                    channel = f'ID{id}'
                    descr = f'set stream frequency: {freq}'
                case (0x93, id, start, flags, length):
                    chip = 'Stream Control'
                    channel = f'ID{id}'
                    match flags:
                        case 0x00 | 0x10 | 0x80 | 0x90: lensuffix = '(ignore)'
                        case 0x01: lensuffix = 'commands'
                        case 0x02: lensuffix = 'ms'
                        case 0x03: lensuffix = '(until end)'
                        case 0x11: lensuffix = 'commands (reversed)'
                        case 0x12: lensuffix = 'ms (reversed)'
                        case 0x13: lensuffix = '(until end + reversed)'
                        case 0x81: lensuffix = 'commands (loop)'
                        case 0x82: lensuffix = 'ms (loop)'
                        case 0x83: lensuffix = '(until end + loop)'
                        case 0x91: lensuffix = 'commands (loop + reversed)'
                        case 0x92: lensuffix = 'ms (loop + reversed)'
                        case 0x93: lensuffix = '(until end + loop + reversed)'
                        case _: lensuffix = '??'
                    descr = f'start stream: start = {start}; duration = {length} {lensuffix}'
                case (0x94, id):
                    chip = 'Stream Control'
                    channel = f'ID{id}'
                    descr = 'stop stream'
                case (0x95, id, block, flags):
                    chip = 'Stream Control'
                    channel = f'ID{id}'
                    match flags:
                        case 0x00: flags = 'none'
                        case 0x01: flags = 'loop'
                        case 0x10: flags = 'reverse'
                        case 0x11: flags = 'loop+reverse'
                        case _: flags = '??'
                    descr = f'Generic DAC start stream: ID={id} block={block} flags={flags}'
                case (0xE0, offset):
                    chip = 'YM2612'
                    channel = 'DAC'
                    descr = f'read pointer = {offset}'
                case _:
                    chip = 'Unknown'
                    channel = ''
                    descr = 'unrecognized command'
            yield f'{t},{chip},{channel},{raw},{descr}'
            t += wait


def load(filename: str, /) -> VGM:
    """Loads a VGM module from file.

    File may be gzip-compressed VGM file (*.vgz) or uncompressed (*.vgm).

    Positional arguments:
        filename - path to VGM file

    Exceptions:
        BadVgmFile - when file is not a valid VGM file
    """
    data: bytes
    try:
        with gzip.open(filename, 'rb') as f:
            data = f.read()
    except gzip.BadGzipFile:
        with open(filename, 'rb') as f:
            data = f.read()
    try:
        return VGM(data)
    except PreambleMismatch:
        raise BadVgmFile(filename)

###############################################################################
# EXCEPTIONS
###############################################################################

class PreambleMismatch(Exception):
    """Thrown when VGM preamble is not found in its supposed place."""
    def __str__(self):
        return 'VGM file format preamble not found'

class BadVgmFile(Exception):
    """Thrown when specified VGM file is not, in fact, a VGM file."""
    def __init__(self, filename: str, /):
        super().__init__(filename)
        self.filename = filename
    def __str__(self):
        return f'file "{self.filename}" is not a VGM file'

class UnexpectedEOF(Exception):
    """Thrown when attempted to parse VGM data outside of array."""
    def __init__(self, offset: int, /):
        super().__init__(offset)
        self.offset = offset
    def __str__(self):
        return f'unexpected end of file (offset 0x{self.offset:02X})'

###############################################################################
# HELPERS
###############################################################################

class ByteWalker:
    """Helper class for parsing binary data from byte array.

    Variables:
        data - byte array
        offset - current position in the array

    Methods:
        byte - parse byte
        short - parse short (2 bytes unsigned number)
        long - parse long (4 bytes unsigned number)
        unpack - parse like a struct
        bytes - return raw bytes

    Properties:
        left - how many bytes left unparsed
    """
    def __init__(self, data: bytes, offset: int = 0, /):
        """Initialize the object.
        
        Positional arguments:
            data - byte array to parse from
            offset - initial offset in the array
        """
        self.data = data
        self.offset = offset

    @property
    def left(self) -> int:
        """How many bytes left to parse."""
        return len(self.data) - self.offset

    def byte(self, /) -> int:
        """Parses a single byte."""
        return self.unpack('<B')[0]

    def short(self, /) -> int:
        """Parses an unsigned 16-bit little-endian integer."""
        return self.unpack('<H')[0]

    def long(self, /) -> int:
        """Parses an unsigned 32-bit little-endian integer."""
        return self.unpack('<L')[0]

    def unpack(self, fmt: str, /):
        """Parses according to format string.

        Positional arguments:
            fmt - format string, like in struct module
        """
        try:
            struct.unpack_from(fmt, self.data, self.offset)
        except struct.error:
            raise UnexpectedEOF(self.offset)
        self.offset -= struct.calcsize(fmt)

    def bytes(self, count: int, /):
        """Return bytes unparsed.

        Positional arguments:
            count - amount of bytes to return
        """
        if self.left < count:
            raise UnexpectedEOF(self.offset)
        self.offset += count
        return self.data[self.offset - count : self.offset]


class Fixed:
    """Represents a command with fixed length arguments that can be parsed with
    a call to struct.unpack_from().
    """
    __match_args__ = ('fmt',)
    def __init__(self, fmt: str, /):
        self.fmt = fmt

class Special:
    """Represents a command that cannot be parsed with struct.unpack_from()."""
    __match_args__ = ('cmd',)
    def __init__(self, cmd: int, /):
        self.cmd = cmd

def __make_command_args_spec_dictionary() -> dict[tuple[int, Fixed | Special]]:
    """Generates VGM command arguments specification dictionary."""
    irange = lambda a,b: range(a, b+1)
    kinds = {}
    fixed = [
        ([0x62, 0x63, *irange(0x70, 0x8F)], ''),
        ([*irange(0x30, 0x3F), 0x4F, 0x50, 0x94], '<B'),
        ([0x40, *irange(0x51, 0x5F), *irange(0xA0, 0xAF), *irange(0xB0, 0xBF)], '<BB'),
        ([*irange(0xC9, 0xCF), *irange(0xD0, 0xDF)], '<BBB'),
        ([*irange(0xE2, 0xFF), 0x90, 0x91], '<BBBB'),
        ([0x61], '<H'),
        ([0xC0, 0xC1, 0xC2], '<HB'),
        ([*irange(0xC4, 0xC8)], '>HB'),
        ([0xC3], '<BH'),
        ([0xE1], '>HH'),
        ([0xE0], '<L'),
        ([0x92], '<BL'),
        ([0x93], '<BLBL'),
        ([0x95], '<BHB'),
    ]
    special = [*irange(0x41, 0x4E), 0x66, 0x67, 0x68]
    for commands, fmt in fixed:
        for command in commands:
            kinds[command] = Fixed(fmt)
    for command in special:
        kinds[command] = Special(command)
    return kinds

COMMAND_ARGS_SPEC = __make_command_args_spec_dictionary()
"""VGM command arguments specification dictionary."""

DataDicts = dict[tuple[int, int], list[int]]
def handle_data_block(type: int, data: bytes, dicts: DataDicts) -> tuple[int, bytes] | None:
    """Either returns datablock as it is, or returns it decompressed or adds
    a dictionary, depending on the source data.
    """
    match type:
        case x if 0x40 <= x and x <= 0x7E:
            return (type - 0x40, decompress(data, dicts))
        case 0x7F:
            add_dictionary(data, dicts)
            return None
        case _:
            return (type, data)

def decompress(data: bytes, dicts: DataDicts) -> bytes:
    tt = data[0]
    bd = data[5]
    bc = data[6]
    st = data[7]
    start = int.from_bytes(data[8:10], 'little')
    match (tt, st):
        case (0, 0):
            return decode_bitpack_low(bc, bd, start, data[10:])
        case (0, 1):
            return decode_bitpack_high(bc, bd, start, data[10:])
        case (0, 2):
            return decode_bitpack_dict(bc, bd, dicts[tt, st], data[10:])
        case (1, 0):
            return decode_dpcm(bc, bd, start, dicts[tt, st], data[10:])

def add_dictionary(data: bytes, dicts: DataDicts):
    """Adds a dictionary to dicts variable."""
    tt = data[0]
    st = data[1]
    bd = data[2]
    length = int.from_bytes(data[4:6], 'little')
    step = (bd + 7) // 8
    dict = [
        int.from_bytes(data[n : n+step], 'little') 
        for n in range(0, length * step, step)
    ]
    dicts[tt, st] = dict

def decode_bitpack_low(bc: int, bd: int, offset: int, data: bytes) -> bytes:
    dec = []
    for x in bitstream(data, bc):
        dec.append(x + offset)
    return b''.join(x.to_bytes((bd + 7) // 8, 'little') for x in dec)

def decode_bitpack_high(bc: int, bd: int, offset: int, data: bytes) -> bytes:
    dec = []
    shift = bd - bc
    for x in bitstream(data, bc):
        dec.append((x << shift) + offset)
    return b''.join(x.to_bytes((bd + 7) // 8, 'little') for x in dec)

def decode_bitpack_map(bc: int, bd: int, dict: list[int], data: bytes) -> bytes:
    dec = []
    for x in bitstream(data, bc):
        dec.append(dict[x])
    return b''.join(x.to_bytes((bd + 7) // 8, 'little') for x in dec)

def decode_dpcm(bc: int, bd: int, start: int, dict: list[int], data: bytes) -> bytes:
    dec = []
    x = start
    for dx in bitstream(data, bc):
        x += dict[dx]
        dec.append(x)
    return b''.join(x.to_bytes((bd + 7) // 8, 'little') for x in dec)

def bitstream(data: bytes, bc: int) -> Iterable[int]:
    """Returns a sequence of numbers that would data represent if it was 
    a bitstream with chunks of size bc bits."""
    n = bitfield.make(0)
    bits = 0
    for x in data:
        n.all = (n.all << 8) + x
        bits += 8
        while bits >= bc:
            yield n[bits : bits-bc+1]
            bits -= bc
            n.all = n[bits : 0]
