from . import bitfield

class YM2612:
    def __init__(self, init=None):
        if init is None:
            self.r0 = bytes(b'\0' * 0xC0 if init is None else init[0])
            self.r1 = bytes(b'\0' * 0xC0 if init is None else init[1])
        else:
            self.r0 = init[0]
            self.r1 = init[1]
        self._ch = [
            Channel(self, 0), Channel(self, 1), Channel(self, 2),
            Channel(self, 3), Channel(self, 4), Channel(self, 5),
        ]

    def __eq__(self, other):
        return self.r0 == other.r0 and self.r1 == other.r1

    def __hash__(self):
        return hash((self.r0, self.r1))

    def get(self, port, addr):
        if port == 0:
            return self.r0[addr]
        else:
            return self.r1[addr]

    def updated(self, port, addr, data):
        if port == 0:
            r0 = bytearray(self.r0)
            r0[addr] = data
            return YM2612((bytes(r0), self.r1))
        elif port == 1:
            r1 = bytearray(self.r1)
            r1[addr] = data
            return YM2612((self.r0, bytes(r1)))
        else:
            return self

    @property
    def lfo_en(self): return bitfield.make(self.r0[0x22])[3]
    @property
    def lfo(self): return bitfield.make(self.r0[0x22])[2:0]
    @property
    def tmra(self): return bitfield.join(self.r0[0x25] << 6, self.r0[0x24])[15:6]
    @property
    def tmrb(self): return int(self.r0[0x26])
    @property
    def tmra_load(self): return bitfield.make(self.r0[0x27])[0]
    @property
    def tmrb_load(self): return bitfield.make(self.r0[0x27])[1]
    @property
    def tmra_en(self): return bitfield.make(self.r0[0x27])[2]
    @property
    def tmrb_en(self): return bitfield.make(self.r0[0x27])[3]
    @property
    def tmra_rst(self): return bitfield.make(self.r0[0x27])[4]
    @property
    def tmrb_rst(self): return bitfield.make(self.r0[0x27])[5]
    @property
    def fm3_mode(self): return bitfield.make(self.r0[0x27])[7:6]

    @property
    def key_chan(self): 
        ch = bitfield.make(self.r0[0x28])[2:0]
        return ch % 4 + (ch // 4) * 3 + 1

    @property
    def key_opmask(self): return bitfield.make(self.r0[0x28])[7:4]
    @property
    def dac_en(self): return bitfield.make(self.r0[0x2B])[7]

    def ch(self, num):
        return self._ch[num - 1]

    def __str__(self):
        ch1 = self.ch(1)
        ch2 = self.ch(2)
        ch3 = self.ch(3)
        ch4 = self.ch(4)
        ch5 = self.ch(5)
        ch6 = self.ch(6)
        return (' '.join(str(x) for x in [self.lfo_en, self.lfo, self.fm3_mode])
            + f' {self.key_opmask:X}/{self.key_chan} {self.dac_en} '
            + ' '.join([str(ch1), str(ch2), str(ch3), str(ch4), str(ch5), str(ch6)]))


class Channel:
    def __init__(self, chip, chan_no):
        self.chip = chip
        self.chan_off = chan_no % 3
        self.port_no = chan_no // 3
        self._op = [
            Operator(self.chip, self.chan_off, self.port_no, 0),
            Operator(self.chip, self.chan_off, self.port_no, 1),
            Operator(self.chip, self.chan_off, self.port_no, 2),
            Operator(self.chip, self.chan_off, self.port_no, 3),
        ]

    def _reg(self, offset):
        port = self.chip.r1 if self.port_no == 1 else self.chip.r0
        return port[offset + self.chan_off]

    @property
    def freq(self): return bitfield.join(self._reg(0xA0), self._reg(0xA4))[10:0]
    @property
    def block(self): return bitfield.make(self._reg(0xA4))[5:3]
    @property
    def alg(self): return bitfield.make(self._reg(0xB0))[2:0]
    @property
    def fb(self): return bitfield.make(self._reg(0xB0))[5:3]
    @property
    def pms(self): return bitfield.make(self._reg(0xB4))[2:0]
    @property
    def ams(self): return bitfield.make(self._reg(0xB4))[5:4]
    @property
    def pan(self): return bitfield.make(self._reg(0xB4))[7:6]

    def op(self, num):
        return self._op[num - 1]

    def __str__(self):
        op1 = self.op(1)
        op2 = self.op(2)
        op3 = self.op(3)
        op4 = self.op(4)
        return (f'{self.freq:04d}/{self.block}' + ' '.join(str(x) for x in [
            self.pan, self.pms, self.ams, self.fb, self.alg])
            + ' << ' + ' '.join(f'{x:03d}' for x in [op1.tl, op2.tl, op3.tl, op4.tl])
            + ' | '
            + ' '.join([op1.timbre(), op2.timbre(), op3.timbre(), op4.timbre()])
            + ' >>')

class Operator:
    def __init__(self, chip, chan_off, port_no, op_no):
        op_map = [0, 2, 1, 3]
        self.chip = chip
        self.op_off = chan_off + op_map[op_no] * 4
        self.port_no = port_no

    def _reg(self, offset):
        port = self.chip.r1 if self.port_no == 1 else self.chip.r0
        return port[offset + self.op_off]

    @property
    def mul(self): return bitfield.make(self._reg(0x30))[3:0]

    @property
    def dt(self):
        dt = bitfield.make(self._reg(0x30))
        if dt[6] == 0:
            return dt[5:4]
        else:
            return -dt[5:4]

    @property
    def tl(self): return int(self._reg(0x40))
    @property
    def ar(self): return bitfield.make(self._reg(0x50))[4:0]
    @property
    def rs(self): return bitfield.make(self._reg(0x50))[7:6]
    @property
    def dr(self): return bitfield.make(self._reg(0x60))[4:0]
    @property
    def am(self): return bitfield.make(self._reg(0x60))[7]
    @property
    def sr(self): return bitfield.make(self._reg(0x70))[4:0]
    @property
    def rr(self): return bitfield.make(self._reg(0x80))[3:0]
    @property
    def sl(self): return bitfield.make(self._reg(0x80))[7:4]
    @property
    def ssg_en(self): return bitfield.make(self._reg(0x90))[3]
    @property
    def ssg(self): return bitfield.make(self._reg(0x90))[2:0]

    def timbre(self):
        return '/'.join(f'{x:02d}' for x in [
            self.mul, self.dt, self.ar, self.rs, self.dr, self.am, self.sr, 
            self.rr, self.sl, self.ssg_en, self.ssg])
