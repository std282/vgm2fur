import gzip
from . import unpacker
from vgm2fur import AppError as Vgm2FurError
from vgm2fur import bitfield

class BadVgmFile(Vgm2FurError):
    def __init__(self, filename, preamble):
        super().__init__(preamble)
        self.filename = filename
        self.preamble = preamble
    def __str__(self):
        return f'file "{self.filename}" is not a VGM file'

class UnknownCommand(Vgm2FurError):
    def __init__(self, com):
        super().__init__(com)
        self.com = com
    def __str__(self):
        return f'unknown VGM command: {self.com:#04x}'

class Song:
    def __init__(self, data):
        if data[:4] != b'Vgm ':
            raise BadVgmFile(None)
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
                case 'data':
                    comset |= {0x67}
                case 'dac':
                    comset |= {*range(0x90, 0x96), 0xE0}
        _seek_vgm_data_start(unp)
        for com in _events(unp, self.version):
            if com[0] in comset:
                yield com

    @property
    def version(self):
        return int.from_bytes(self.data[0x08:0x0C], 'little')

    @property
    def total_wait(self):
        return int.from_bytes(self.data[0x18:0x1C], 'little')

    @property
    def playback_rate(self):
        return int.from_bytes(self.data[0x24:0x28], 'little')

def load(filename):
    try:
        with gzip.open(filename) as f:
            data = f.read()
    except gzip.BadGzipFile:
        with open(filename, 'rb') as f:
            data = f.read()

    try:
        return Song(data)
    except BadVgmFile as err:
        err.filename = filename
        raise err

def _seek_vgm_data_start(unp):
    unp.offset = 0x34
    rel = unp.unpack('L')
    if rel == 0:
        unp.offset = 0x40
    else:
        unp.offset = 0x34 + rel

class Unpack:
    __match_args__ = ('format',)
    def __init__(self, format):
        self.format = format

class NoParams:
    pass

class SpecialCase:
    __match_args__ = ('com',)
    def __init__(self, com):
        self.com = com

class irange:
    def __init__(self, a, b):
        self.a = a
        self.b = b
    def __iter__(self):
        x = self.a
        while x <= self.b:
            yield x
            x += 1
    def __contains__(self, x):
        return self.a <= x and x <= self.b

def _make_com_kinds():
    kinds = {}
    noparams = [0x62, 0x63, *irange(0x70, 0x8F)]
    unpack = [
        ([*irange(0x30, 0x3F), 0x4F, 0x50, 0x94], 'B'),
        ([0x40, *irange(0x51, 0x5F), *irange(0xA0, 0xAF), *irange(0xB0, 0xBF)], 'BB'),
        ([*irange(0xC9, 0xCF), *irange(0xD0, 0xDF)], 'BBB'),
        ([*irange(0xE2, 0xFF), 0x90, 0x91], 'BBBB'),
        ([0x61], 'H'),
        ([0xC0, 0xC1, 0xC2], 'HB'),
        ([*irange(0xC4, 0xC8)], '>HB'),
        ([0xC3], 'BH'),
        ([0xE1], '>HH'),
        ([0xE0], 'L'),
        ([0x92], 'BL'),
        ([0x93], 'BLBL'),
        ([0x95], 'BHB'),
    ]
    special = [*irange(0x41, 0x4E), 0x66, 0x67, 0x68]
    for command in noparams:
        kinds[command] = NoParams()
    for commands, format in unpack:
        for command in commands:
            kinds[command] = Unpack(format)
    for command in special:
        kinds[command] = SpecialCase(command)
    return kinds

def _unpack_24bit(unp):
    return int.from_bytes(unp.bytes(3), 'little')

_COM_KINDS = _make_com_kinds()
def _events(unp, version):
    done = False
    while not done:
        com = unp.byte()
        match _COM_KINDS.get(com):
            case NoParams():
                yield (com,)
            case Unpack(format):
                yield (com,) + unp.unpack_tuple(format)
            case SpecialCase(x) if x in irange(0x41, 0x4E):
                if version >= 0x160:
                    yield (com,) + unp.unpack('BB')
                else:
                    yield (com, unp.byte())
            case SpecialCase(0x66):
                done = True
            case SpecialCase(0x67):
                unp.expect('B', 0x66)
                type, length = unp.unpack('BL')
                payload = unp.bytes(length)
                yield (com, type, payload)
            case SpecialCase(0x68):
                unp.expect('B', 0x66)
                type = unp.unpack('B')
                readoff = _unpack_24bit(unp)
                writeoff = _unpack_24bit(unp)
                size = _unpack_24bit(unp)
                if size == 0:
                    size = 0x1000000
                yield (com, type, readoff, writeoff, size)
            case _:
                raise UnknownCommand(com)

def _event_bytes(event):
    ev0 = event[0].to_bytes(1, 'little')
    match _COM_KINDS.get(event[0]):
        case NoParams():
            return ev0
        case Unpack(format):
            return ev0 + unpacker.pack(format, *event[1:])
        case SpecialCase(x) if x in irange(0x41, 0x4E):
            if len(event) == 3:
                return ev0 + unpacker.pack('BB', *event[1:])
            else:
                return ev0 + unpacker.pack('B', *event[1:])
        case SpecialCase(0x67):
            return ev0 + b'\x66' + unpacker.pack('BL', event[1], event[2])
        case SpecialCase(0x68):
            return b''.join([
                ev0, 
                b'\x66',
                unpacker.pack('B', event[1]),
                event[2].to_bytes(3, 'little'),
                event[3].to_bytes(3, 'little'),
                (event[4] & 0xFFFFFF).to_bytes(3, 'little'),
            ])
        case _:
            raise UnknownCommand(com)

def events_csv(events):
    t = 0
    yield 'Sample,Description,Raw data'
    for event in events:
        rawdata = ' '.join(f'{x:02X}' for x in _event_bytes(event))
        wait = 0
        match event:
            case (0x67, type, data):
                descr = f'DATA type={type} len={len(data)}'
                rawdata += ' ...'
            case (0x52, addr, data) | (0x53, addr, data):
                port = event[0] & 1
                d = bitfield.make(data)
                match (port, addr):
                    case (0, 0x22):
                        res = 'En' if d[3] else 'Dis'
                        descr = f'YM2612 LFO {res} Val={d[2:0]}'
                    case (0, 0x27):
                        fm3mode = ['normal', 'special', 'CSM', '??']
                        descr = f'YM2612 FM3 mode: {fm3mode[d[7:6]]}'
                    case (0, 0x28):
                        i = d[2:0] % 4 + 3 * (d[2:0] // 4)
                        opmask = d[7:4]
                        if opmask == 0:
                            descr = f'YM2612 FM{i+1} key off'
                        else:
                            descr = f'YM2612 FM{i+1} key on ({opmask:X})'
                    case (0, 0x2B):
                        res = 'En' if d[7] else 'Dis'
                        descr = f'YM2612 DAC {res}'
                    case (p, a) if (a & 0xF0) == 0x30:
                        dt = d[5:4] if d[6] == 0 else -d[5:4]
                        descr = _fm_op(p, a) + f'Mult={d[3:0]} Dt={dt}'
                    case (p, a) if (a & 0xF0) == 0x40:
                        descr = _fm_op(p, a) + f'TL={d[6:0]}'
                    case (p, a) if (a & 0xF0) == 0x50:
                        descr = _fm_op(p, a) + f'AR={d[4:0]} RS={d[6:0]}'
                    case (p, a) if (a & 0xF0) == 0x60:
                        op = _fm_op(p, a)
                        descr = _fm_op(p, a) + f'DR={d[4:0]} AM={d[7]}'
                    case (p, a) if (a & 0xF0) == 0x70:
                        descr = _fm_op(p, a) + f'SR={d[4:0]}'
                    case (p, a) if (a & 0xF0) == 0x80:
                        descr = _fm_op(p, a) + f'RR={d[3:0]} SL={d[7:4]}'
                    case (p, a) if (a & 0xF0) == 0x90:
                        res = 'En' if d[3] else 'Dis'
                        descr = _fm_op(p, a) + f'SSG {res} = {d[2:0]}'
                    case (p, a) if (a & 0xFC) == 0xA0:
                        descr = _fm_ch(p, a) + f'FreqL={d[7:0]}'
                    case (p, a) if (a & 0xFC) == 0xA4:
                        descr = _fm_ch(p, a) + f'FreqH={d[2:0]} Block={d[5:3]}'
                    case (0, a) if (a & 0xFC) == 0xA8:
                        descr = _fm_ch3_op(a) + f'FreqL={d[7:0]}'
                    case (0, a) if (a & 0xFC) == 0xAC:
                        descr = _fm_ch3_op(a) + f'FreqH={d[2:0]} Block={d[5:3]}'
                    case (p, a) if (a & 0xFC) == 0xB0:
                        descr = _fm_ch(p, a) + f'Alg={d[2:0]} FB={d[5:3]}'
                    case (p, a) if (a & 0xFC) == 0xB4:
                        descr = _fm_ch(p, a) + f'AMS={d[2:0]} PMS={d[5:4]} Pan={d[7:6]}'
                    case _:
                        descr = 'YM2612 unrecognized command'
            case (0x50, data):
                d = bitfield.make(data)
                if d[7]:
                    if d[4]:
                        ch = f'PSG{1+d[6:5]} ' if d[6:5] != 3 else 'PSG Noise '
                        descr = 'SN76489 ' + ch + f'Vol={d[3:0]}'
                    elif d[6:5] != 3:
                        chno = 1+d[6:5]
                        descr = f'SN76489 PSG{chno} FreqL={d[3:0]}'
                    else:
                        descr = f'SN76489 PSG Noise Mode={d[3:0]}'
                else:
                    descr = f'SN76489 PSG^ FreqH={d[5:0]}'
            case (0x61, pause):
                wait = pause
                descr = f'Wait {wait} samples'
            case (0x62,):
                wait = 735
                descr = f'Wait {wait} samples'
            case (0x63,):
                wait = 882
                descr = f'Wait {wait} samples'
            case (x,) if x in irange(0x70, 0x7F):
                wait = x - 0x70 + 1
                descr = f'Wait {wait} samples'
            case (x,) if x in irange(0x80, 0x8F):
                wait = x - 0x80
                if wait == 0:
                    descr = 'YM2612 DAC play sample'
                else:
                    descr = f'YM2612 DAC play sample and wait {wait} samples'
            case (0x68, chip, readoff, writeoff, size):
                descr = f'DAC PCM RAM operation: chip={chip} size={size} read={readoff} write={writeoff}'
            case (0x90, id, chip, port, com):
                descr = f'Generic DAC setup: ID={id} chip={chip} port={port} com={com}'
            case (0x91, id, bank, step, start):
                descr = f'Generic DAC set stream data: ID={id} bank={bank} step={step} start={start}'
            case (0x92, id, freq):
                descr = f'Generic DAC set stream freq: ID={id} freq={freq}'
            case (0x93, id, start, flags, length):
                start = event[2] + (event[3] << 8) + (event[4] << 16) + (event[5] << 24)
                length = event[7] + (event[8] << 8) + (event[9] << 16) + (event[10] << 24)
                match flags:
                    case 0x00 | 0x10 | 0x80 | 0x90: lensuffix = '(ignore)'
                    case 0x01: lensuffix = 'cmd'
                    case 0x02: lensuffix = 'ms'
                    case 0x03: lensuffix = '(untilend)'
                    case 0x11: lensuffix = 'cmd(reversed)'
                    case 0x12: lensuffix = 'ms(reversed)'
                    case 0x13: lensuffix = '(untilend+reversed)'
                    case 0x81: lensuffix = 'cmd(loop)'
                    case 0x82: lensuffix = 'ms(loop)'
                    case 0x83: lensuffix = '(untilend+loop)'
                    case 0x91: lensuffix = 'cmd(loop+reversed)'
                    case 0x92: lensuffix = 'ms(loop+reversed)'
                    case 0x93: lensuffix = '(untilend+loop+reversed)'
                    case _: lensuffix = '??'
                descr = f'Generic DAC start stream: ID={id} start={start} len={length}{lensuffix}'
            case (0x94, id):
                descr = f'Generic DAC stop stream: ID={id}'
            case (0x95, id, block, flags):
                block = event[2] + (event[3] << 8)
                match flags:
                    case 0x00: flags = 'none'
                    case 0x01: flags = 'loop'
                    case 0x10: flags = 'reverse'
                    case 0x11: flags = 'loop+reverse'
                    case _: flags = '??'
                descr = f'Generic DAC start stream: ID={id} block={block} flags={flags}'
            case (0xE0, offset):
                descr = f'YM2612 DAC read={offset}'
            case _:
                descr = ''
        yield f'{t},{descr},{rawdata}'
        t += wait

def _fm_op(port, addr):
    _op_map = [1, 3, 2, 4]
    addr = bitfield.make(addr)
    ch = 1 + addr[1:0] + port * 3
    op = _op_map[addr[3:2]]
    return f'YM2612 FM{ch} OP{op} '

def _fm_ch(port, addr):
    addr = bitfield.make(addr)
    ch = 1 + addr[1:0] + port * 3
    return f'YM2612 FM{ch} '

def _fm_ch3_op(addr):
    _ch3_op_map = [3, 1, 2]
    addr = bitfield.make(addr)
    op = _ch3_op_map[addr[1:0]]
    return f'YM2612 FM3 OP{op} '
