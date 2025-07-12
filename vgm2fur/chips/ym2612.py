import bitfield
import copy

class YM2612:
    def __init__(self):
        self.lfo = 0
        self.lfo_en = 0
        self.channels = [Channel(), Channel(), Channel3(),
                         Channel(), Channel(), Channel6()]
        self.regs = bytearray(0xC0 * 2)

    def ch(self, num):
        return self.channels[num - 1]

    _op_map = [0, 2, 1, 3]
    def _get_op(self, port, addr):
        addr = bitfield.make(addr)
        ch = addr[1:0] + port * 3
        op = YM2612._op_map[addr[3:2]]
        return self.channels[ch].operators[op]

    def _get_ch(self, port, addr):
        addr = bitfield.make(addr)
        ch = addr[1:0] + port * 3
        return self.channels[ch]

    _ch3_op_map = [2, 0, 1]
    def _get_ch3_op(self, addr):
        addr = bitfield.make(addr)
        op = YM2612._ch3_op_map[addr[1:0]]
        return self.channels[2].operators[op]

    def __eq__(self, other):
        # return (self._tuple() == other._tuple() and
        #     all(a == b for (a, b) in zip(self.channels, other.channels)))
        return bytes(self.regs) == bytes(other.regs)

    def update(self, port, addr, data):
        self.regs[port * 0xC0 + addr] = data
        data = bitfield.make(data)
        match (port, addr):
            case (0, 0x22):
                self.lfo = data[2:0]
                self.lfo_en = data[3]
            case (0, 0x27):
                self.ch(3).mode = data[7:6]
            case (0, 0x28):
                i = data[2:0] % 4 + 3 * (data[2:0] // 4)
                self.channels[i].opmask = data[7:4]
                self.channels[i].keyid += 1
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
                freq = bitfield.make(ch.freq)
                freq[7:0] = data[7:0]
                ch.freq = freq.all
            case (p, a) if (a & 0xFC) == 0xA4:
                ch = self._get_ch(p, a)
                freq = bitfield.make(ch.freq)
                freq[10:8] = data[2:0]
                ch.freq = freq.all
                ch.block = data[5:3]
            case (0, a) if (a & 0xFC) == 0xA8:
                op = self._get_ch3_op(a)
                freq = bitfield.make(op.freq)
                freq[7:0] = data[7:0]
                op.freq = freq.all
            case (0, a) if (a & 0xFC) == 0xAC:
                op = self._get_ch3_op(a)
                freq = bitfield.make(op.freq)
                freq[10:8] = data[2:0]
                op.freq = freq.all
                op.block = data[5:3]
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

    def updated(self, port, addr, data):
        clone = self.clone()
        clone.update(port, addr, data)
        return clone

    def __str__(self):
        elements = [
            f'LFO:{'ENA' if self.lfo_en else 'DIS'}/{self.lfo}',
            f'FM1 [ {self.channels[0]} ]',
            f'FM2 [ {self.channels[1]} ]',
            f'FM3 [ {self.channels[2]} ]',
            f'FM4 [ {self.channels[3]} ]',
            f'FM5 [ {self.channels[4]} ]',
            f'FM6 [ {self.channels[5]} ]',
        ]
        return ' '.join(elements)

    def clone(self):
        clone = copy.copy(self)
        clone.channels = [ch.clone() for ch in self.channels]
        clone.regs = clone.regs.copy()
        return clone

class Channel:
    def __init__(self):
        self._make_most_fields()
        self.operators = [Operator(), Operator(), Operator(), Operator()]

    def op(self, num):
        return self.operators[num - 1]

    def _make_most_fields(self):
        self.keyid = 0
        self.opmask = 0
        self.freq = 0
        self.block = 0
        self.alg = 0
        self.fb = 0
        self.pms = 0
        self.ams = 0
        self.pan = 0

    _fields = 'keyid opmask freq block alg fb pms ams pan'.split(' ')
    def _tuple(self):
        return tuple(getattr(self, x) for x in type(self)._fields)

    def __eq__(self, other):
        return (self._tuple() == other._tuple() and
            all(a == b for (a, b) in zip(self.operators, other.operators)))

    _pan_map = '-RLC'
    def __str__(self):
        elements = [
            f'{self.keyid: 8d}',
            ''.join(map(lambda x: _OPMASK_MAP[x], f'{self.opmask:04b}')),
            f'{self.freq:03X}/{self.block} ',
            f'{self.operators[0].tl:02X}',
            f'{self.operators[1].tl:02X}',
            f'{self.operators[2].tl:02X}',
            f'{self.operators[3].tl:02X} ',
            f'{self.alg}',
            f'{Channel._pan_map[self.pan]}',
            f'{self.fb}',
            f'{self.pms}',
            f'{self.ams}',
            f'OP1 {{ {self.operators[0]} }}',
            f'OP2 {{ {self.operators[1]} }}',
            f'OP3 {{ {self.operators[2]} }}',
            f'OP4 {{ {self.operators[3]} }}',
        ]
        return ' '.join(elements)

    def clone(self):
        clone = copy.copy(self)
        clone.operators = [op.clone() for op in clone.operators]
        return clone


class Channel3(Channel):
    def __init__(self):
        self._make_most_fields()
        self.mode = 0
        self.operators = [Operator3(), Operator3(), Operator3(), Operator3_4(self)]

    _fields = Channel._fields + ['mode']

    def __str__(self):
        if self.mode == 1:
            elements = [
                f'MODE:SP',
                f'{self.keyid: 8d}',
                ''.join(map(lambda x: _OPMASK_MAP[x], f'{self.opmask:04b}')),
                f'{self.operators[0].freq:06X}/{self.operators[0].block}',
                f'{self.operators[0].tl:02X}',
                f'{self.operators[1].freq:06X}/{self.operators[1].block}',
                f'{self.operators[1].tl:02X}',
                f'{self.operators[2].freq:06X}/{self.operators[2].block}',
                f'{self.operators[2].tl:02X}',
                f'{self.operators[3].freq:06X}/{self.operators[3].block}',
                f'{self.operators[3].tl:02X}',
                f'{self.alg}',
                f'{Channel._pan_map[self.pan]}',
                f'{self.fb}',
                f'{self.pms}',
                f'{self.ams}',
                f'OP1 {{ {self.operators[0]} }}',
                f'OP2 {{ {self.operators[1]} }}',
                f'OP3 {{ {self.operators[2]} }}',
                f'OP4 {{ {self.operators[3]} }}',
            ]
        else:
            elements = [
                f'MODE:FM',
                f'{self.keyid: 8d}',
                ''.join(map(lambda x: _OPMASK_MAP[x], f'{self.opmask:04b}')),
                f'{self.freq:06X}/{self.block}',
                f'{self.operators[0].tl:02X}',
                f'{self.operators[1].tl:02X}',
                f'{self.operators[2].tl:02X}',
                f'{self.operators[3].tl:02X}',
                f'{self.alg}',
                f'{Channel._pan_map[self.pan]}',
                f'{self.fb}',
                f'{self.pms}',
                f'{self.ams}',
                f'OP1 {{ {self.operators[0]} }}',
                f'OP2 {{ {self.operators[1]} }}',
                f'OP3 {{ {self.operators[2]} }}',
                f'OP4 {{ {self.operators[3]} }}',
            ]
        return ' '.join(elements)

    def clone(self):
        clone = copy.copy(self)
        clone.operators = [
            clone.operators[0].clone(),
            clone.operators[1].clone(),
            clone.operators[2].clone(),
            clone.operators[3].clone(clone),
        ]
        return clone

class Channel6(Channel):
    def __init__(self):
        self._make_most_fields()
        self.operators = [Operator(), Operator(), Operator(), Operator()]
        self.dac_en = 0

    _fields = Channel._fields + ['dac_en']

    def __str__(self):
        elements = [
            f'DAC:{'ENA' if self.dac_en else 'DIS'}',
            f'{self.keyid: 8d}',
            ''.join(map(lambda x: _OPMASK_MAP[x], f'{self.opmask:04b}')),
            f'{self.freq:03X}/{self.block} ',
            f'{self.operators[0].tl:02X}',
            f'{self.operators[1].tl:02X}',
            f'{self.operators[2].tl:02X}',
            f'{self.operators[3].tl:02X} ',
            f'{self.alg}',
            f'{Channel._pan_map[self.pan]}',
            f'{self.fb}',
            f'{self.pms}',
            f'{self.ams}',
            f'OP1 {{ {self.operators[0]} }}',
            f'OP2 {{ {self.operators[1]} }}',
            f'OP3 {{ {self.operators[2]} }}',
            f'OP4 {{ {self.operators[3]} }}',
        ]
        return ' '.join(elements)

class Operator:
    def __init__(self):
        self._make_most_fields()

    def _make_most_fields(self):
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

    _fields = 'mult dt tl ar rs dr am sr rr sl ssg ssg_en'.split()
    def _tuple(self):
        return tuple(getattr(self, x) for x in self._fields)

    def __eq__(self, other):
        return self._tuple() == other._tuple()

    def __str__(self):
        elements = [
            f'MULT:{self.mult:02d}',
            f'DT:{self.dt:+2d}',
            f'AR:{self.ar:02d}',
            f'RS:{self.rs}',
            f'DR:{self.dr:02d}',
            f'AM:{self.am}',
            f'SR:{self.sr:02d}',
            f'RR:{self.rr:02d}',
            f'SL:{self.sl:02d}',
            f'SSG:{'ENA' if self.ssg_en else 'DIS'}/{self.ssg}',
        ]
        return ' '.join(elements)

    def clone(self):
        return copy.copy(self)


class Operator3(Operator):
    def __init__(self):
        self._make_most_fields()
        self.freq = 0
        self.block = 0

    _fields = Operator._fields + 'freq block'.split()

    def clone(self):
        return copy.copy(self)


class Operator3_4(Operator):
    def __init__(self, owner):
        self._make_most_fields()
        self._owner = owner

    @property
    def freq(self): return self._owner.freq
    @property
    def block(self): return self._owner.block

    def clone(self, owner):
        clone = copy.copy(self)
        clone._owner = owner
        return clone


_OPMASK_MAP = {'0': '.', '1': '#'}
