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
        for com in _events(unp):
            if com[0] in comset:
                yield com

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

def _event_67_bytes(type, data):
    yield from [0x67, 0x66]
    yield type
    yield from len(data).to_bytes(4, 'little')

def events_csv(events):
    t = 0
    yield 'Sample,Description,Raw data'
    for event in events:
        if event[0] == 0x67:
            (_, type, data) = event
            descr = f'DATA type={type} len={len(data)}'
            rawdata = ' '.join(f'{x:02X}' for x in _event_67_bytes(type, data)) + ' ...'
            yield f'{t},{descr},{rawdata}'
            continue
        rawdata = ' '.join(f'{x:02X}' for x in event)
        wait = 0
        match event[0]:
            case 0x52 | 0x53:
                port = event[0] & 1
                addr = event[1]
                d = bitfield.make(event[2])
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
            case 0x50:
                d = bitfield.make(event[1])
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
            case 0x61:
                wait = event[1] + (event[2] << 8)
                descr = f'Wait {wait} samples'
            case 0x62:
                wait = 735
                descr = f'Wait {wait} samples'
                t += wait
            case 0x63:
                wait = 882
                descr = f'Wait {wait} samples'
                t += wait
            case _ if (event[0] & 0xF0) == 0x70:
                wait = 1 + (event[0] & 0x0F)
                descr = f'Wait {wait} samples'
            case _ if (event[0] & 0xF0) == 0x80:
                wait = event[0] & 0x0F
                if wait == 0:
                    descr = 'YM2612 DAC play sample'
                else:
                    descr = f'YM2612 DAC play sample and wait {wait} samples'
            case 0x68:
                chip = event[2]
                readoff = event[3] + (event[4] << 8) + (event[5] << 16)
                writeoff = event[6] + (event[7] << 8) + (event[8] << 16)
                size = event[9] + (event[10] << 8) + (event[11] << 16)
                descr = f'DAC PCM RAM operation: chip={chip} size={size} read={readoff} write={writeoff}'
            case 0x90:
                descr = f'Generic DAC setup: ID={event[1]} chip={event[2]} port={event[3]} com={event[4]}'
            case 0x91:
                descr = f'Generic DAC set stream data: ID={event[1]} bank={event[2]} step={event[3]} start={event[4]}'
            case 0x92:
                freq = event[2] + (event[3] << 8) + (event[4] << 16) + (event[5] << 24)
                descr = f'Generic DAC set stream freq: ID={event[1]} freq={freq}'
            case 0x93:
                start = event[2] + (event[3] << 8) + (event[4] << 16) + (event[5] << 24)
                length = event[7] + (event[8] << 8) + (event[9] << 16) + (event[10] << 24)
                match event[6]:
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
                descr = f'Generic DAC start stream: ID={event[1]} start={start} len={length}{lensuffix}'
            case 0x94:
                descr = f'Generic DAC stop stream: ID={event[1]}'
            case 0x95:
                block = event[2] + (event[3] << 8)
                match event[4]:
                    case 0x00: flags = 'none'
                    case 0x01: flags = 'loop'
                    case 0x10: flags = 'reverse'
                    case 0x11: flags = 'loop+reverse'
                    case _: flags = '??'
                descr = f'Generic DAC start stream: ID={event[1]} block={block} flags={flags}'
            case 0xE0:
                read = event[1] + (event[2] << 8) + (event[3] << 16) + (event[4] << 24)
                descr = f'YM2612 DAC read={read}'
            case 0x67:
                type = event[2]
                length = event[3] + (event[4] << 8) + (event[5] << 16) + (event[6] << 24)
                descr = f'DATA type={type} len={length}'
                del type
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
