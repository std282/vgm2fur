import gzip
from . import unpacker
from vgm2fur import AppError as Vgm2FurError

class BadVgmFile(Vgm2FurError):
    def __init__(self, preamble):
        super().__init__(preamble)
        self.preamble = preamble
    def __str__(self):
        return f'not a VGM file; preamble {self.preamble}'

class UnknownCommand(Vgm2FurError):
    def __init__(self, com):
        super().__init__(com)
        self.com = com
    def __str__(self):
        return f'unknown VGM command: {self.com:#04x}'

class Song:
    def __init__(self, data):
        if data[:4] != b'Vgm ':
            raise BadVgmFile(self.unp.data[0:4])
        self.data = data

    def events(self, *chiplist):
        unp = unpacker.Unpacker(self.data)
        comset = {0x61, 0x62, 0x63, *range(0x70, 0x90)}
        for chip in chiplist:
            match chip:
                case 'ym2612':
                    comset |= {0x52, 0x53}
                case 'sn76489':
                    comset |= {0x50}
        _seek_vgm_data_start(unp)
        for com in _events(unp):
            if com[0] in comset:
                yield com

    @property
    def total_wait(self):
        return int.from_bytes(self.data[0x18:0x1C])

def load(filename):
    try:
        with gzip.open(filename) as f:
            data = f.read()
    except gzip.BadGzipFile:
        with open(filename, 'rb') as f:
            data = f.read()
    return Song(data)

def _seek_vgm_data_start(unp):
    unp.offset = 0x34
    rel = unp.unpack('L')
    if rel == 0:
        unp.offset = 0x40
    else:
        unp.offset = 0x34 + rel

def _make_com_dict():
    _0_ARGS = {0x62, 0x63, 0x66, *range(0x70, 0x90)}
    _1_ARGS = {*range(0x30, 0x40), 0x4F, 0x50, 0x94}
    _2_ARGS = {0x40, *range(0x41, 0x4F), *range(0x51, 0x60), 0x61, 0xA0, *range(0xB0, 0xC0)}
    _3_ARGS = {*range(0xC0, 0xE0)}
    _4_ARGS = {0x90, 0x91, 0x95, *range(0xE0, 0x100)}
    coms = [_0_ARGS, _1_ARGS, _2_ARGS, _3_ARGS, _4_ARGS]
    comdict = dict()
    for argcount in range(len(coms)):
        for com in coms[argcount]:
            comdict[com] = argcount
    comdict[0x67] = -1 # unbound size
    comdict[0x68] = 11
    comdict[0x92] = 5
    comdict[0x93] = 10
    return comdict

_COM_NARGS = _make_com_dict()
def _events(unp):
    try:
        while True:
            com = unp.byte()
            if com == 0x66:
                break
            match _COM_NARGS.get(com):
                case -1:
                    assert com == 0x67
                    unp.expect('B', 0x66)
                    (type, length) = unp.unpack('BL')
                    data = unp.bytes(length)
                    yield (com, type, data)
                case 0:
                    yield (com, )
                case int(n):
                    yield tuple([com] + [unp.byte() for _ in range(n)])
                case _:
                    raise UnknownCommand(com)
    except unpacker.NoDataError:
        pass
