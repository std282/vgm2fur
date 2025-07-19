from vgm2fur import bitfield
import copy
import warnings


class FreqLatch:
    use = False
    def __init__(self):
        self.state = 0
        self.freq = bitfield.make(0)
        self.block = 0
    _low_table = [2, 0, 2]
    def low(self, data: bitfield.Bitfield):
        self.freq[7:0] = data[7:0]
        if not FreqLatch.use: 
            return (self.freq.all, self.block)
        self.state = FreqLatch._low_table[self.state]
        return (self.freq.all, self.block) if self.state == 0 else None
    _high_table = [1, 1, 0]
    def high(self, data: bitfield.Bitfield):
        self.freq[10:8] = data[2:0]
        self.block = data[5:3]
        if not FreqLatch.use: 
            return (self.freq.all, self.block)
        self.state = FreqLatch._high_table[self.state]
        return (self.freq.all, self.block) if self.state == 0 else None


class IllFormedEvent(Exception):
    def __init__(self, eventdata):
        super().__init__(eventdata)
        self.eventdata = eventdata
    def __str__(self):
        return 'ill-formed VGM command: ' + self._repr_data() + '; ignored'
    def _repr_data(self):
        elems = []
        for x in self.eventdata:
            if x is None:
                elems.append('??')
            else:
                elems.append(f'{x:02X}')
        return ' '.join(elems)


class YM2612:
    def __init__(self, /, *, noinit=False):
        if noinit: return
        self.channels = [Channel1(), Channel(), Channel3(), Channel(), Channel(), Channel6()]
        self.regs = bytearray(0xC0 * 2)

    def ch(self, num):
        return self.channels[num - 1]

    _op_map = [0, 2, 1, 3]
    def _get_op(self, port, addr):
        addr = bitfield.make(addr)
        subch = addr[1:0]
        if subch == 3:
            raise IllFormedEvent((0x52 if port == 0 else 0x53, addr.all, None))
        ch = subch + port * 3
        op = YM2612._op_map[addr[3:2]]
        return self.channels[ch].operators[op]

    def _get_ch(self, port, addr):
        addr = bitfield.make(addr)
        subch = addr[1:0]
        if subch == 3:
            raise IllFormedEvent((0x52 if port == 0 else 0x53, addr.all, None))
        ch = subch + port * 3
        return self.channels[ch]

    _ch3_op_map = [2, 0, 1]
    def _get_ch3_op(self, addr):
        addr = bitfield.make(addr)
        index = addr[1:0]
        if index == 3:
            raise IllFormedEvent((0x52, addr.all, None))
        op = YM2612._ch3_op_map[index]
        return self.channels[2].operators[op]

    def __eq__(self, other):
        return (
            bytes(self.regs) == bytes(other.regs) and 
            all(a.keyid == b.keyid for (a, b) in zip(self.channels, other.channels)))

    def update(self, port, addr, data):
        self.regs[port * 0xC0 + addr] = data
        data = bitfield.make(data)
        try:
            match (port, addr):
                case (0, 0x22):
                    self.ch(1).lfo = data[2:0]
                    self.ch(1).lfo_en = data[3]
                case (0, 0x27):
                    self.ch(3).mode = data[7:6]
                case (0, 0x28):
                    subch = data[1:0]
                    if subch == 3:
                        raise IllFormedEvent((0x52, 0x28, data.all))
                    ch = self.channels[subch + 3 * data[2]]
                    opmask = data[7:4]
                    if ch.opmask != opmask:
                        ch.opmask = opmask
                        ch.keyid += 1
                case (0, 0x2B):
                    self.ch(6).dac_en = data[7]
                case (p, a) if (a & 0xF0) == 0x30:
                    op = self._get_op(p, a)
                    op.mult = data[3:0]
                    if data[6] == 0:
                        op.dt = data[5:4]
                    else:
                        op.dt = -data[5:4]
                case (p, a) if (a & 0xF0) == 0x40:
                    self._get_op(p, a).tl = data[6:0]
                case (p, a) if (a & 0xF0) == 0x50:
                    op = self._get_op(p, a)
                    op.ar = data[4:0]
                    op.rs = data[7:6]
                case (p, a) if (a & 0xF0) == 0x60:
                    op = self._get_op(p, a)
                    op.dr = data[4:0]
                    op.am = data[7]
                case (p, a) if (a & 0xF0) == 0x70:
                    self._get_op(p, a).sr = data[4:0]
                case (p, a) if (a & 0xF0) == 0x80:
                    op = self._get_op(p, a)
                    op.rr = data[3:0]
                    op.sl = data[7:4]
                case (p, a) if (a & 0xF0) == 0x90:
                    op = self._get_op(p, a)
                    op.ssg = data[2:0]
                    op.ssg_en = data[3]
                case (p, a) if (a & 0xFC) == 0xA0:
                    ch = self._get_ch(p, a)
                    res = ch.latch.low(data)
                    if res is not None:
                        ch.freq, ch.block = res
                case (p, a) if (a & 0xFC) == 0xA4:
                    ch = self._get_ch(p, a)
                    res = ch.latch.high(data)
                    if res is not None:
                        ch.freq, ch.block = res
                case (0, a) if (a & 0xFC) == 0xA8:
                    op = self._get_ch3_op(a)
                    res = op.latch.low(data)
                    if res is not None:
                        op.freq, op.block = res
                case (0, a) if (a & 0xFC) == 0xAC:
                    op = self._get_ch3_op(a)
                    res = op.latch.high(data)
                    if res is not None:
                        op.freq, op.block = res
                case (p, a) if (a & 0xFC) == 0xB0:
                    ch = self._get_ch(p, a)
                    ch.alg = data[2:0]
                    ch.fb = data[5:3]
                case (p, a) if (a & 0xFC) == 0xB4:
                    ch = self._get_ch(p, a)
                    ch.pms = data[2:0]
                    ch.ams = data[5:4]
                    ch.pan = data[7:6]
                case _:
                    pass
        except IllFormedEvent as err:
            warnings.warn(str(err))

    def copy(self):
        clone = YM2612(noinit=True)
        clone.channels = [ch.copy() for ch in self.channels]
        clone.regs = self.regs.copy()
        return clone


class ChannelBase:
    def __init__(self, /, *, noinit=False):
        if noinit: return
        self.keyid = 0
        self.opmask = 0
        self.freq = 0
        self.block = 0
        self.alg = 0
        self.fb = 0
        self.pms = 0
        self.ams = 0
        self.pan = 0

    def copy(self):
        clone = type(self)(noinit=True)
        clone.keyid = self.keyid
        clone.opmask = self.opmask
        clone.freq = self.freq
        clone.block = self.block
        clone.alg = self.alg
        clone.fb = self.fb
        clone.pms = self.pms
        clone.ams = self.ams
        clone.pan = self.pan
        return clone


class Channel(ChannelBase):
    def __init__(self, /, *, noinit=False):
        if noinit: return
        super().__init__()
        self.latch = FreqLatch()
        self.operators = [Operator(), Operator(), Operator(), Operator()]

    def op(self, num):
        return self.operators[num - 1]

    def copy(self):
        clone = super().copy()
        clone.latch = self.latch
        clone.operators = [op.copy() for op in self.operators]
        return clone


class Channel1(Channel):
    def __init__(self, /, *, noinit=False):
        if noinit: return
        super().__init__()
        self.lfo = 0
        self.lfo_en = 0

    def copy(self):
        clone = super().copy()
        clone.lfo = self.lfo
        clone.lfo_en = self.lfo_en
        return clone


class Channel3(ChannelBase):
    def __init__(self, /, *, noinit=False):
        if noinit: return
        super().__init__()
        self.mode = 0
        self.latch = FreqLatch()
        self.operators = [Operator3(), Operator3(), Operator3(), Operator3_4(self)]

    op = Channel.op

    def copy(self):
        clone = super().copy()
        clone.mode = self.mode
        clone.latch = self.latch
        clone.operators = [
            self.operators[0].copy(),
            self.operators[1].copy(),
            self.operators[2].copy(),
            self.operators[3].copy(clone),
        ]
        return clone


class Channel6(Channel):
    def __init__(self, /, *, noinit=False):
        if noinit: return
        super().__init__()
        self.dac_en = 0

    def copy(self):
        clone = super().copy()
        clone.dac_en = self.dac_en
        return clone


class Operator:
    def __init__(self, /, *, noinit=False):
        if noinit: return
        self.mult = 0
        self.dt = 0
        self.tl = 0
        self.ar = 0
        self.rs = 0
        self.dr = 0
        self.am = 0
        self.sr = 0
        self.rr = 0
        self.sl = 0
        self.ssg = 0
        self.ssg_en = 0

    def copy(self):
        clone = type(self)(noinit=True)
        clone.mult = self.mult
        clone.dt = self.dt
        clone.tl = self.tl
        clone.ar = self.ar
        clone.rs = self.rs
        clone.dr = self.dr
        clone.am = self.am
        clone.sr = self.sr
        clone.rr = self.rr
        clone.sl = self.sl
        clone.ssg = self.ssg
        clone.ssg_en = self.ssg_en
        return clone


class Operator3(Operator):
    def __init__(self, /, *, noinit=False):
        if noinit: return
        super().__init__()
        self.freq = 0
        self.block = 0
        self.latch = FreqLatch()

    def copy(self):
        clone = super().copy()
        clone.freq = self.freq
        clone.block = self.block
        clone.latch = self.latch
        return clone


class Operator3_4(Operator):
    def __init__(self, owner=None, /, *, noinit=False):
        if noinit: return
        super().__init__()
        self._owner = owner

    @property
    def freq(self): return self._owner.freq
    @property
    def block(self): return self._owner.block

    def copy(self, owner):
        clone = super().copy()
        clone._owner = owner
        return clone


_OPMASK_MAP = {'0': '.', '1': '#'}

_CHIP_FEATURES = frozenset('lfo dacen fm1 fm2 fm3 fm4 fm5 fm6 fmx freqfm3'.split())
_CHANNEL_FEATURES = frozenset('id opmask freqfm alg fb mod pan op1 op2 op3 op4 opx'.split())
_OPERATOR_FEATURES = frozenset('mult dt tl ar rs dr am sr rr sl ssg'.split())
def csv(chip_states, src_features):
    ymft = []
    chft = []
    opft = []
    for feature in src_features:
        if feature in _CHIP_FEATURES:
            ymft.append(feature)
        elif feature in _CHANNEL_FEATURES:
            chft.append(feature)
        elif feature in _OPERATOR_FEATURES:
            opft.append(feature)
    ymft = _norm_chip(ymft)
    chft = _norm_channel(chft)
    opft = _norm_operator(opft)
    if len(ymft) == 0:
        return None
    return _csv(chip_states, ymft, chft, opft)

def _csv(chip_states, ymft, chft, opft):
    yield _csv_header(ymft, chft, opft)
    for chip in chip_states:
        yield _csv_chip(chip, ymft, chft, opft)

def _norm_chip(fts):
    fts1 = []
    for ft in fts:
        match ft:
            case 'fmx':
                fts1 += 'fm1 fm2 fm3 fm4 fm5 fm6'.split()
            case _:
                fts1.append(ft)
    return fts1

def _norm_channel(fts):
    fts1 = []
    for ft in fts:
        match ft:
            case 'opx':
                fts1 += 'op1 op2 op3 op4'.split()
            case _:
                fts1.append(ft)
    return fts1

def _norm_operator(fts):
    fts1 = []
    for ft in fts:
        match ft:
            case 'parx':
                fts1 += 'mult dt tl ar rs dr am sr rr sl ssg'.split()
            case _:
                fts1.append(ft)
    return fts1

def _csv_header(ymfts, chfts, opfts):
    ss = []
    for ymft in ymfts:
        match ymft:
            case 'lfo': s = 'LFO En,LFO'
            case 'dacen': s = 'DAC En'
            case 'freqfm3': 
                s = ','.join([
                    'FM3 Sp En',
                    'FM3 Sp OP1 Freq', 'FM3 Sp OP1 Blk',
                    'FM3 Sp OP2 Freq', 'FM3 Sp OP2 Blk',
                    'FM3 Sp OP3 Freq', 'FM3 Sp OP3 Blk',
                    'FM3 Sp OP4 Freq', 'FM3 Sp OP4 Blk'])
            case 'fm1' | 'fm2' | 'fm3' | 'fm4' | 'fm5' | 'fm6': 
                chname = ymft.upper() + ' '
                ss1 = []
                for chft in chfts:
                    match chft:
                        case 'id': s1 = chname + 'Key ID'
                        case 'opmask': s1 = chname + 'OP Mask'
                        case 'freqfm': s1 = chname + 'Freq,' + chname + 'Block'
                        case 'alg': s1 = chname + 'Alg'
                        case 'fb': s1 = chname + 'Fb'
                        case 'mod': s1 = chname + 'AMS,' + chname + 'PMS'
                        case 'pan': s1 = chname + 'Pan'
                        case 'op1' | 'op2' | 'op3' | 'op4':
                            opname = chname + chft.upper() + ' '
                            ss2 = []
                            for opft in opfts:
                                match opft:
                                    case 'mult': s2 = opname + 'Mult'
                                    case 'dt': s2 = opname + 'Dt'
                                    case 'tl' | 'ar' | 'rs' | 'dr' | 'am' | 'sr' | 'rr' | 'sl':
                                        s2 = opname + opft.upper()
                                    case 'ssg': s2 = opname + 'SSG En,' + opname + 'SSG'
                                ss2.append(s2)
                            s1 = ','.join(ss2)
                    ss1.append(s1)
                s = ','.join(ss1)
        ss.append(s)
    return ','.join(ss)

def _csv_chip(ym, ymft, chft, opft):
    ss = []
    for ft in ymft:
        match ft:
            case 'lfo': s = f'{ym.ch(1).lfo_en},{ym.ch(1).lfo}'
            case 'dacen': s = f'{ym.ch(6).dac_en}'
            case 'freq3sp':
                ch3 = ym.ch(3)
                if ch3.mode:
                    ss1 = ['1']
                    for op in map(lambda n: ch3.op(n), range(1, 5)):
                        ss1.append(f'{op.freq},{op.block}')
                    s = ','.join(ss1)
                else:
                    s = '0,,,,,,,,'
            case 'fm1' | 'fm2' | 'fm3' | 'fm4' | 'fm5':
                n = int(ft[2])
                s = _csv_channel(ym.ch(n), chft, opft)
            case 'fm6':
                ch = ym.ch(6)
                if ch.dac_en:
                    s = _csv_channel_empty(chft, opft)
                else:
                    s = _csv_channel(ch, chft, opft)
        ss.append(s)
    return ','.join(ss)

def _csv_channel(ch, chft, opft):
    ss = []
    for ft in chft:
        match ft:
            case 'id': s = f'{ch.keyid}'
            case 'opmask': s = f'{ch.opmask}'
            case 'freqfm': s = f'{ch.freq},{ch.block}'
            case 'alg': s = f'{ch.alg}'
            case 'fb': s = f'{ch.fb}'
            case 'mod': s = f'{ch.ams},{ch.pms}'
            case 'pan': s = f'{ch.pan}'
            case 'op1' | 'op2' | 'op3' | 'op4':
                n = int(ft[2])
                s = _csv_operator(ch.op(n), opft)
        ss.append(s)
    return ','.join(ss)

def _csv_channel_empty(chft, opft):
    ss = []
    for ft in chft:
        match ft:
            case 'op1' | 'op2' | 'op3' | 'op4':
                s = _csv_operator_empty(opft)
        ss.append(s)
    return ','.join(ss)

def _csv_operator(op, opft):
    ss = []
    for ft in opft:
        match ft:
            case 'mult': s = f'{op.mult}'
            case 'dt': s = f'{op.dt}'
            case 'tl': s = f'{op.tl}'
            case 'ar': s = f'{op.ar}'
            case 'rs': s = f'{op.rs}'
            case 'dr': s = f'{op.dr}'
            case 'am': s = f'{op.am}'
            case 'sr': s = f'{op.sr}'
            case 'rr': s = f'{op.rr}'
            case 'sl': s = f'{op.sl}'
            case 'ssg': s = f'{op.ssg_en},{op.ssg}'
        ss.append(s)
    return ','.join(ss)

def _csv_operator_empty(opft):
    ss = []
    for _ in opft:
        ss.append('')
    return ','.join(ss)
