from dataclasses import dataclass
import warnings
import gzip

import rawdata
import bitfield
import adhoc

class Vgm:
    """Represents VGM file."""
    def __init__(self, data):
        if data[0:4] != b'Vgm ':
            raise NoVgmPreamble()
        self.data = data
        self._comlen = Vgm._make_comlen()
        # Adding missing events to comlen
        len4x = 3 if self.version >= 0x160 else 2
        self._comlen |= {com: len4x for com in range(0x41, 0x4F)}

    @staticmethod
    def _make_comlen():
        """Returns a mapping from VGM command to its length. Used for command
        parsing.

        The mapping is incomplete. It lacks commands 0x66 (end of data, no 
        need to parse after that), 0x67 (data block, variable length) and
        0x41-4C (length depends on version).
        """
        irange = lambda a, b: range(a, b + 1)
        lengths = [
            (1, [0x62, 0x63, *irange(0x70, 0x8F)]),
            (2, [*irange(0x30, 0x3F), 0x4F, 0x50, 0x94]),
            (3, [0x40, *irange(0x51, 0x5F), 0x61, *irange(0xA0, 0xBF)]),
            (4, [*irange(0xC0, 0xDF)]),
            (5, [0x90, 0x91, 0x95, *irange(0xE0, 0xFF)]),
            (6, [0x92]),
            (11, [0x93]),
            (12, [0x68]),
        ]
        comlen = {}
        for length, commands in lengths:
            for command in commands:
                comlen[command] = length
        return comlen

    @property
    def version(self):
        """Loaded VGM file version."""
        return rawdata.unpack('<L', self.data[0x08:0x0C])[0]

    @property
    def _content_offset(self):
        offset = int.from_bytes(self.data[0x34:0x38], 'little')
        if offset == 0:
            offset = 0x40
        else:
            offset += 0x34
        return offset

    def content(self):
        """Returns VGM content - commands and data blocks."""
        w = rawdata.Walker(self.data, self._content_offset)
        commands = CommandList()
        datablocks = DataBlockList()
        done = False
        t = 0
        datadicts = {}
        CT_DICT, CT_DPCM = (0, 2), (1, 0)  # pairs of kind (tt, st)
        while not done:
            match w.top:
                case 0x66:  # 0x66 is end of data
                    done = True
                case 0x67:  # 0x67 is data block
                    match (block := parse_data_block(w)):
                        case DataBlock(type='stream'):
                            datablocks.add(block)
                        case DataBlock(type='image'):
                            datablocks.add(block)
                        case DataBlock(type='write'):
                            pass # issue an appropriate command instead
                        case CompCopyLow() | CompCopyHigh():
                            datablocks.add(block.decompress())
                        case CompDict():
                            datablocks.add(block.decompress(datadicts[CT_DICT]))
                        case CompDPCM():
                            datablocks.add(block.decompress(datadicts[CT_DPCM]))
                        case DataDict(tt=tt, st=st):
                            assert (tt, st) in [CT_DICT, CT_DPCM]
                            datadicts[tt, st] = block
                case _:    # anything else is pauses and/or chip commands
                    match parse_command(w, self._comlen):
                        case Pause(wait=wait, before=None):
                            t += wait
                        case Pause(wait=wait, before=com):
                            commands.add(t, com)
                            t += wait
                        case com:
                            commands.add(t, com)
        return commands, datablocks

    def raw_content(self):
        """Returns content as sequence of raw bytes."""
        w = rawdata.Walker(self.data, self._content_offset)
        done = False
        while not done:
            match w.top:
                case 0x66:
                    done = True
                case 0x67:
                    length = int.from_bytes(w.rest[3:7], 'little')
                    yield w.bytes(length + 7)
                case com:
                    length = self._comlen.get(com, 1)
                    yield w.bytes(length)

class CommandList:
    """Represents a list of commands."""
    def __init__(self, init=[]):
        self.list = init

    def add(self, t, com):
        """Adds a command com that was executed at time t.

        Internal usage. Do not use. Modifies a command argument.
        """
        com.t = t
        self.list.append(com)

    def __iter__(self):
        return iter(self.list)

    def __len__(self):
        return len(self.list)

    def select(self, **attrs):
        """Query. Returns a CommandList of commands that satisfy the conditions.

        Usage:
            newlist = comlist.select(chip='ym2612', type='sampler')
            # newlist contains every command from comlist that has fields
            # 'chip' equal to 'ym2612' and 'type' equal to 'sampler'.
        """
        newlist = []
        attrs = list(attrs.items())
        attr_eq = lambda obj, attr: hasattr(com, attr[0]) and getattr(com, attr[0]) == attr[1]
        for com in self.list:
            if all(attr_eq(com, attr) for attr in attrs):
                newlist.append(com)
        return CommandList(newlist)

    def contains(self, **attrs):
        """Query. Returns true if a there exists a command that satisfies the
        conditions.

        Usage:
            hasfm = comlist.contains(chip='ym2612', type='fm')
            # hasfm is True if there is a command in comlist that has fields
            # 'chip' equal to 'ym2612' and 'type' equal to 'fm'.
        """
        for com in self.list:
            for (attr, value) in attrs.items():
                if hasattr(com, attr) and getattr(com, attr) == value:
                    return True
        return False

class DataBlockList:
    """Represents a list of data blocks."""
    def __init__(self):
        self.list = {}

    def add(self, block):
        """Adds a data block to list.

        Internal usage.
        """
        if block.chip == 'unknown':
            return
        code = f'{block.type}/{block.chip}'
        match block.type, (code in self.list):
            case 'stream', False:
                self.list[code] = BankedStream(block.data)
            case 'stream', True:
                self.list[code].append(block.data)
            case 'image', False:
                image = Image(block.size)
                image.write(block.addr, block.data)
            case 'image', True:
                self.list[code].place(block.addr, block.data)

    def __getitem__(self, key):
        return self.list[key]

    def __contains__(self, key):
        return key in self.list

class BankedStream:
    """Represents a banked stream, for usage with 0x95 commands.

    Access to unbanked data is through a single argument in brackets:
        bs[10:100]
    Access to a banked data is through a double argument:
        bs[3, 1:100]
    """
    def __init__(self, data):
        self.data = data
        self._banks = [slice(0, len(data))]

    def __getitem__(self, key):
        match key:
            case int() | slice():
                return self.data[key]
            case int(), int() | slice():
                bank = self._banks[key[0]]
                subkey = key[1]
                return self.data[bank][subkey]
            case _:
                raise KeyError('BankedStream cannot be indexed like this')

    def append(self, data):
        """Adds a new data block, meaning a new bank."""
        self.data += data
        start = self.banks[-1].stop
        stop = start + len(data)
        self._banks.append(slice(start, stop))

class Image:
    """Represents a ROM image."""
    def __init__(self, size):
        self.space = bytearray(size)

    def write(self, addr, data):
        """Writes data into ROM."""
        self.space[addr : addr + len(data)] = data

    def read(self, addr, size):
        """Reads data from ROM."""
        return self.space[addr : addr + size]

    def __getitem__(self, key):
        return self.space[key]

def parse_command(w, comlen):
    """Parses a command from byte stream."""
    match com := w.byte():
        # Pause
        case 0x61:
            wait, = w.unpack('<H')
            return Pause(wait)
        case 0x62:
            return Pause(735) # one 60 Hz frame
        case 0x63:
            return Pause(882) # one 50 Hz frame
        case x if 0x70 <= x and x <= 0x7F:
            wait = x - 0x6F
            return Pause(wait)
        # SN76489
        case 0x50:
            data, = w.unpack('<B')
            return Command.sn76489(data)
        # YM2612
        case 0x52 | 0x53:
            port = com & 0x01
            addr, data = w.unpack('<BB')
            if port == 0 and addr == 0x2A:
                return Command.ym2612_direct(data)
            else:
                return Command.ym2612_fm(port, addr, data)
        case 0x80:
            return Command.ym2612_play()
        case x if 0x81 <= x and x <= 0x8F:
            wait = x - 0x80
            return Pause(wait, before=Command.ym2612_play())
        case 0xE0:
            ptr, = w.unpack('<L')
            return Command.ym2612_setptr(ptr)
        # (NEW CHIPS HERE)

        # Anything else
        case _:
            length = comlen.get(com, 0)
            if length == 0:
                warnings.warn(UnrecognizedCommand(com))
                return Command.unknown(com, b'')
            else:
                rest = w.bytes(comlen[com] - 1)
                return Command.unknown(com, rest)

class Command:
    """Represents a VGM command.

    It is just a set of fields.
    """
    def __init__(self, chip, **kwargs):
        self.t = None
        self.chip = chip
        for (attr, value) in kwargs.items():
            setattr(self, attr, value)

    # Constructors

    @classmethod
    def sn76489(cls, data):
        return cls('sn76489', data=data)

    @classmethod
    def ym2612_fm(cls, port, addr, data):
        return cls('ym2612', type='fm', port=port, addr=addr, data=data)

    @classmethod
    def ym2612_play(cls):
        return cls('ym2612', type='sampler', action='play')

    @classmethod
    def ym2612_setptr(cls, ptr):
        return cls('ym2612', type='sampler', action='setptr', ptr=ptr)

    @classmethod
    def ym2612_direct(cls, data):
        return cls('ym2612', type='direct', data=data)

    # (NEW CHIPS HERE)

    @classmethod
    def unknown(cls, com, payload):
        return cls('unknown', com=com, payload=payload)

class Pause:
    """Represents a pause between commands."""
    def __init__(self, wait, before=None):
        self.wait = wait
        self.before = before

def parse_data_block(w):
    """Parses a single data block."""
    _, _, kind, length = w.unpack('<BBBL')
    match kind:
        case x if 0 <= x and x <= 0x3F:
            chip = DataBlock._CHIPNAMES.get(kind, None)
            data = w.bytes(length)
            return DataBlock.stream(chip, data)
        case x if 0 <= 0x40 and x <= 0x7E:
            assert length > 10
            chip = DataBlock._name(kind - 0x40)
            tt, _, bd, bc, st, extra = w.unpack('<BLBBBH')
            data = w.bytes(length - 10)
            match (tt, st):
                case (0, 0):
                    return CompCopyLow(chip=chip, data=data, bc=bc, bd=bd, offset=extra)
                case (0, 1):
                    return CompCopyHigh(chip=chip, data=data, bc=bc, bd=bd, offset=extra)
                case (0, 2):
                    return CompDict(chip=chip, data=data, bc=bc, bd=bd)
                case (1, 0):
                    return CompDPCM(chip=chip, data=data, bc=bc, bd=bd, s0=extra)
        case 0x7F:
            tt, st, bd, bc, count = w.unpack('<BBBBH')
            size = (bd + 7) // 8  # ceil(bd / 8)
            data = []
            for _ in range(count):
                data.append(int.from_bytes(w.bytes(size), 'little'))
            _ = w.bytes(length - count * size)
            return DataDict(tt=tt, st=st, bc=bc, bd=bd, data=data)
        case x if 0x80 <= x and x <= 0xBF:
            chip = DataBlock._CHIPNAMES.get(kind, None)
            size, addr = w.unpack('<LL')
            data = w.bytes(length - 8)
            return DataBlock.image(chip, size, addr, data)
        case x if 0xC0 <= x and x <= 0xDF:
            chip = DataBlock._CHIPNAMES.get(kind, None)
            addr, = w.unpack('<H')
            data = w.bytes(length - 2)
            return DataBlock.write(chip, addr, data)
        case x if 0xE0 <= x and x <= 0xFF:
            chip = DataBlock._CHIPNAMES.get(kind, None)
            addr, = w.unpack('<L')
            data = w.bytes(length - 4)
            return DataBlock.write(chip, addr, data)

class DataBlock:
    """Represents a data block. 

    Like a Command, it's just a set of fields.
    """
    def __init__(self, type, chip, **kwargs):
        self.type = type
        self.chip = chip
        for (attr, value) in kwargs.items():
            setattr(self, attr, value)

    # a map of chip number to chip name
    _CHIPNAMES = {
        0x00: 'ym2612'
        # (NEW CHIPS HERE)
    }

    # Constructors

    @classmethod
    def stream(cls, chip, data):
        return cls('stream', chip, data=data)

    @classmethod
    def image(cls, chip, size, addr, data):
        return cls('image', chip, size=size, addr=addr, data=data)

    @classmethod
    def write(cls, chip, addr, data):
        return cls('write', chip, addr=addr, data=data)

@dataclass(frozen=True)
class CompCopyLow:
    """Represents a compressed block. Algorithm: copy lower bits."""
    chip: str
    data: bytes
    bc: int
    bd: int
    offset: int

    def decompress(self):
        decomp = []
        for x in bitstream(self.data, self.bc):
            decomp.append(x + self.offset)
        return DataBlock.stream(self.chip, decomp)

@dataclass(frozen=True)
class CompCopyHigh:
    """Represents a compressed block. Algorithm: copy upper bits."""
    chip: str
    data: bytes
    bc: int
    bd: int
    offset: int

    def decompress(self):
        decomp = []
        shift = self.bd - self.bc
        for x in bitstream(self.data, self.bc):
            decomp.append((x << shift) + self.offset)
        return DataBlock.stream(self.chip, decomp)

@dataclass(frozen=True)
class CompDict:
    """Represents a compressed block. Algorithm: copy from dictionary."""
    chip: str
    data: bytes
    bc: int
    bd: int

    def decompress(self, dict):
        assert (self.bc, self.bd) == (dict.bc, dict.bd)
        decomp = []
        for x in bitstream(self.data, self.bc):
            decomp.append(dict[x])
        return DataBlock.stream(self.chip, decomp)

@dataclass(frozen=True)
class CompDPCM:
    """Represents a compressed block. Algorithm: DPCM."""
    chip: str
    data: bytes
    bc: int
    bd: int
    s0: int

    def decompress(self, dict):
        assert (self.bc, self.bd) == (dict.bc, dict.bd)
        decomp = []
        s = self.s0
        mask = (1 << self.bd) - 1
        for x in bitstream(self.data, self.bc):
            s = (s + dict[x]) & mask
            decomp.append(s)
        return DataBlock.stream(self.chip, decomp)

class DataDict:
    """Represents a compression dictionary."""
    def __init__(self, *, bc, bd, data):
        self.bc = bc
        self.bd = bd
        size = bd + 7 // 8  # ceil(bd) / 8
        self.data = []
        for i in range(len(data) // size):
            a = i * size
            b = a + size
            self.data.append(int.from_bytes(data[a:b], 'little'))

    def __getitem__(self, index):
        return self.data[index]

def bitstream(data, bc):
    """Interprets a byte stream as a stream of fixed bit width numbers."""
    avail = 0
    bf = bitfield.make(0)
    for byte in data:
        bf.all = (bf.all << 8) | byte
        avail += 8
        while avail >= bc:
            elem = slice(avail, avail - bc + 1)
            yield bf[elem]
            bf[elem] = 0
            avail -= bc

def load(filename):
    """Loads VGM module from file, vgm or vgz."""
    try:
        with gzip.open(filename, 'rb') as f:
            data = f.read()
    except gzip.BadGzipFile:
        with open(filename, 'rb') as f:
            data = f.read()
    try:
        return Vgm(data)
    except NoVgmPreamble:
        raise BadVgmFile(filename)

NoVgmPreamble = adhoc.exception('NoVgmPreamble', 'no preamble found')
BadVgmFile = adhoc.exception('BadVgmFile', '"{0}": not a VGM file')
VgmAbruptEnd = adhoc.warning('VgmAbruptEnd', 'VGM file ended abruptly, probably corrupt')
UnrecognizedCommand = adhoc.warning('UnrecognizedCommand', 'unrecognized VGM command: 0x{0:02X} at offset 0x{1:06X}')
