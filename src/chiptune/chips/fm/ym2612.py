import enum
import warnings
from dataclasses import dataclass, field
from typing import TypeVar

import bitfield
import bestfit

from . import VGMCommand

T = TypeVar('T')
Tuple3 = tuple[T, T, T]
Tuple4 = tuple[T, T, T, T]
Tuple6 = tuple[T, T, T, T, T, T]

@dataclass(slots=True)
class Chip:
    """YM2612 chip state.

    Variables:
        lfo - LFO mode (None if disabled, int-magnitude if enabled)
        dac - is DAC enabled
        mode - channel 3 mode
        fm - FM channels
        ch3op - channel 3 special mode operator 1-3 frequencies

    Methods:
        update - update chip state according to VGM command
    """
    lfo: int | None = None
    dac: bool = False
    mode: int = 0
    fm: Tuple6['FM'] = field(default_factory=lambda: (FM(), FM(), FM(), FM(), FM(), FM()))
    ch3op: Tuple3['Ch3Op'] = field(default_factory=lambda: (Ch3Op(), Ch3Op(), Ch3Op()))

    supported_commands = frozenset([0x52, 0x53, *range(0x80, 0x90), 0xE0])
    """List of VGM command numbers that can be handled by YM2612."""

    def update(self, cmd: VGMCommand, /):
        """Updates chip state according to VGM command.

        Positional arguments:
            cmd - VGM command, tuple of kind (0x52, x, y) or (0x53, x, y)
        """
        if cmd[0] & 0xFE != 0x52:
            return
        (port, addr, data) = cmd
        data = bitfield.make(data)
        match (port, addr):
            case (0x52, 0x22):
                self.lfo = data[2:0] if data[3] else None
            case (0x52, 0x24):
                pass  # timer A
            case (0x52, 0x25):
                pass  # timer A
            case (0x52, 0x26):
                pass  # timer B
            case (0x52, 0x27):
                self.mode = data[7:6]
            case (0x52, 0x28):
                if data[1:0] < 3:
                    fm = self.fm[data[2] * 3 + data[1:0]]
                    opmask = data[7:4]
                    if fm.opmask != opmask:
                        fm.opmask = opmask
                        fm.trig += 1
                else:
                    warnings.warn(InvalidCommand(cmd))
            case (0x52, 0x2B):
                self.dac = (data[7] != 0)
            case (0x52, _) if (addr & 0xF8) == 0xA8 and (addr & 3) != 3:
                i = [2, 0, 1][addr & 3]
                self.fm3op[i].update(addr & 0xFC, data)
            case _ if (addr & 3) != 3:
                i = 3 * (port - 0x52) + (addr & 3)
                try:
                    self.fm[i].update(addr & 0xFC, data)
                except InvalidCommandReport:
                    warnings.warn(InvalidCommand(cmd))
            case _:
                warnings.warn(InvalidCommand(cmd))

    def copy(self) -> Chip:
        """Returns a copy of itself."""
        return Chip(lfo=self.lfo, dac=self.dac, mode=self.mode,
            fm=tuple(x.copy() for x in self.fm),
            ch3op=tuple(x.copy() for x in self.ch3op))

    def state(self) -> Chip:
        return self.copy()

    @property
    def fm1(self): return self.fm[0]
    @property
    def fm2(self): return self.fm[1]
    @property
    def fm3(self): return self.fm[2]
    @property
    def fm4(self): return self.fm[3]
    @property
    def fm5(self): return self.fm[4]
    @property
    def fm6(self): return self.fm[5]
    @property
    def ch3op1(self): return self.ch3op[0]
    @property
    def ch3op2(self): return self.ch3op[1]
    @property
    def ch3op3(self): return self.ch3op[2]

class FrequencyBitfield(bitfield.Bitfield):
    low = bitfield.named[7:0]
    high = bitfield.named[10:8]

    def __init__(self):
        super().__init__(0)

@dataclass(slots=True)
class FM:
    """FM channel state.

    Variables:
        op - FM operators state
        freq - channel frequency
        block - channel block (octave)
        opmask - operator mask
        trig - note trigger count
        fb - feedback level
        alg - algorithm
        ams - amplitude modulation sensivity
        pms - phase modulation sensivity
        pan - panning
    """
    op: Tuple4['Operator'] = field(default_factory=lambda: (Operator(), Operator(), Operator(), Operator()))
    freq: FrequencyBitfield = field(default_factory=FrequencyBitfield)
    block: int = 0
    opmask: int = 0
    trig: int = 0
    fb: int = 0
    alg: int = 0
    ams: int = 0
    pms: int = 0
    pan: int = 0

    def update(self, addr: int, data: bitfield.Bitfield, /):
        """Internal."""
        match addr:
            case 0xA0:
                self.freq.low = data.all
            case 0xA4:
                self.freq.high = data[2:0]
                self.block = data[5:3]
            case 0xB0:
                self.alg = data[2:0]
                self.fb = data[5:3]
            case 0xB4:
                self.pms = data[2:0]
                self.ams = data[5:4]
                self.pan = data[7:6]
            case _:
                i = [0, 2, 1, 3][(addr >> 2) & 3]
                self.op[i].update(addr & 0xF0, data)

    def copy(self) -> FM:
        """Returns a copy of itself."""
        return FM(op=tuple(x.copy() for x in self.op,
            freq=self.freq.copy()), block=self.block, opmask=self.opmask,
            trig=self.trig, fb=self.fb, alg=self.alg, ams=self.ams, 
            pms=self.pms, pan=self.pan)

    def note(self, notemap: list[tuple[T, int]]) -> tuple[T, int]:
        """Returns a note approximation for current frequency.

        Positional arguments:
            notemap - sorted list of tuples of kind (note, freq).
        """
        return _note(self.freq.all, self.block, notemap)

    def voice(self) -> tuple['Voice', int]:
        """Returns a voice and its volume of given channel."""
        op1 = self.op1
        op2 = self.op2
        op3 = self.op3
        op4 = self.op4
        match self.alg:
            case 0 | 1 | 2 | 3:
                vol = 0x7F - self.op4.tl
                op4 = op4.replace(tl=0)
            case 4:
                tl2 = op2.tl; tl4 = op4.tl
                mtl = min(tl2, tl4)
                vol = 0x7F - mtl
                op2 = op2.replace(tl=tl2-mtl)
                op4 = op4.replace(tl=tl4-mtl)
            case 5 | 6:
                tl2 = op2.tl; tl3 = op3.tl; tl4 = op4.tl
                mtl = min(tl2, tl3, tl4)
                vol = 0x7F - mtl
                op2 = op2.replace(tl=tl2-mtl)
                op3 = op3.replace(tl=tl3-mtl)
                op4 = op4.replace(tl=tl4-mtl)
            case 7:
                tl1 = op1.tl; tl2 = op2.tl; tl3 = op3.tl; tl4 = op4.tl
                mtl = min(tl2, tl3, tl4)
                vol = 0x7F - mtl
                op1 = op1.replace(tl=tl1-mtl)
                op2 = op2.replace(tl=tl2-mtl)
                op3 = op3.replace(tl=tl3-mtl)
                op4 = op4.replace(tl=tl4-mtl)
        voice = Voice(op=(op1.frozen(), op2.frozen(), op3.frozen(), op4.frozen()),
            fb=self.fb, alg=self.alg, ams=self.ams, pms=self.pms)
        return voice, vol

    def voice_special(self) -> tuple['Voice', Tuple4[int]]:
        """Returns a voice and its volume of given channel. Special mode variant."""
        vol = tuple(0x7F - x.tl for x in self.op)
        voice = Voice(
            op=(self.op1.replace(tl=0).frozen(), self.op2.replace(tl=0).frozen(),
                self.op3.replace(tl=0).frozen(), self.op4.replace(tl=0).frozen()),
            fb=self.fb, alg=self.alg, ams=self.ams, pms=self.pms)
        return voice, vol

    @property
    def op1(self): return self.op[0]
    @property
    def op2(self): return self.op[1]
    @property
    def op3(self): return self.op[2]
    @property
    def op4(self): return self.op[3]

@dataclass(slots=True)
class Operator:
    """FM operator state.

    Variables:
        mult - multiplier
        dt - detune
        tl - total level
        ar - attack rate
        rs - rate scaling
        dr - decay rate
        am - amplitude modulation
        sr - sustain rate
        rr - release rate
        sl - sustain level
        ssg - None if disables, otherwise int-mode
    """
    mult: int = 0
    dt: int = 0
    tl: int = 127
    ar: int = 31
    rs: int = 0
    dr: int = 31
    am: int = 0
    sr: int = 31
    rr: int = 15
    sl: int = 15
    ssg: int | None = None

    def update(self, addr: int, data: bitfield.Bitfield, /):
        """Internal."""
        match addr:
            case 0x30:
                self.mult = data[3:0]
                self.dt = -data[5:4] if data[6] else data[5:4]
            case 0x40:
                self.tl = data[6:0]
            case 0x50:
                self.ar = data[4:0]
                self.rs = data[7:6]
            case 0x60:
                self.dr = data[4:0]
                self.am = data[7]
            case 0x70:
                self.sr = data[4:0]
            case 0x80:
                self.rr = data[3:0]
                self.sl = data[7:4]
            case 0x90:
                self.ssg = data[2:0] if data[3] else None
            case _:
                raise InvalidCommandReport()

    def copy(self) -> Operator:
        """Returns a copy of itself."""
        return Operator(mult=self.mult, dt=self.dt, tl=self.tl, ar=self.ar,
            rs=self.rs, dr=self.dr, am=self.am, sr=self.sr, rr=self.rr, 
            sl=self.sl, ssg=self.ssg)

    def frozen(self) -> 'FrozenOperator':
        """Returns a frozen copy of itself.

        Since it's frozen, it can be used as dictionary key.
        """
        return FrozenOperator(mult=self.mult, dt=self.dt, tl=self.tl, ar=self.ar,
            rs=self.rs, dr=self.dr, am=self.am, sr=self.sr, rr=self.rr, 
            sl=self.sl, ssg=self.ssg)

@dataclass(slots=True)
class Ch3Op:
    """Channel 3 operator frequency state.

    Variables:
        freq - operator frequency
        block - operator block (octave)
    """
    freq: FrequencyBitfield = field(default_factory=FrequencyBitfield)
    block: int = 0

    def update(self, addr: int, data: bitfield.Bitfield, /):
        """Internal."""
        match addr:
            case 0xA8:
                self.freq.low = data.all
            case 0xAC:
                self.freq.high = data[2:0]
                self.block = data[5:3]

    def copy(self) -> Ch3Op:
        """Returns a copy of itself."""
        return Ch3Op(freq=self.freq.copy(), block=self.block)

    def note(self, notemap: list[tuple[T, int]]) -> tuple[T, int]:
        """Returns a note approximation for current frequency.

        Positional arguments:
            notemap - sorted list of tuples of kind (note, freq).
        """
        return _note(self.freq.all, self.block, notemap)


class InvalidCommand(UserWarning):
    """Warning class for invalid YM2612 commands."""
    def __init__(self, cmd: VGMCommand, /):
        super().__init__(cmd)
        self.cmd = cmd
    def __str__(self):
        cmd = ' '.join(f'{x:02X}' for x in self.cmd)
        return 'ignored invalid YM2612 command: ' + cmd

class InvalidCommandReport(Exception):
    """Signalizes invalid YM2612 command.

    Raised when handled YM2612 command is obviously invalid, but given context
    does not have enough information to properly issue warning.
    """
    pass


@dataclass(frozen=True, slots=True)
class Voice:
    op: Tuple4['FrozenOperator']
    fb: int
    alg: int
    ams: int
    pms: int

@dataclass(frozen=True, slots=True)
class FrozenOperator:
    mult: int
    dt: int
    tl: int
    ar: int
    rs: int
    dr: int
    am: int
    sr: int
    rr: int
    sl: int
    ssg: int | None


def _note(freq: int, block: int, 
        notemap: list[tuple[T, int]]) -> tuple[T, int]:
    """Implementation for FM.note and Ch3Op.note."""
    freq <<= block
    note, disp = bestfit.bestfit(freq, notemap)
    disp >>= block
    return note, disp
