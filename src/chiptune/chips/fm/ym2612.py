import enum
import warnings
from . import VGMCommand
import bitfield

class Chip:
    """YM2612 chip behaviour model class.

    Variables:
        lfo - LFO mode (None if disabled, int-magnitude if enabled)
        dac - is DAC enabled
        mode - channel 3 mode
        fm - FM channels state
        ch3op - channel 3 special mode operator 1-3 frequencies

    Methods:
        play - update chip state according to VGM command
    """
    def __init__(self, /):
        """Initializes YM2612 to its default state.
        
        Default state:
            - all channels at silence
            - all frequencies at 0, block 0
            - FM3 mode: normal
            - DAC: disabled
            - LFO: disabled
        """
        self.lfo = None
        self.dac = False
        self.mode = Ch3Mode.NORMAL
        self.fm = [FM(), FM(), FM(), FM(), FM(), FM()]
        self.ch3op = [Ch3Op(), Ch3Op(), Ch3Op()]

    supported_commands = frozenset([0x52, 0x53, *range(0x80, 0x90), 0xE0])
    """List of VGM command numbers that can be handled by YM2612."""

    def play(self, cmd: VGMCommand, /):
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
                self.mode = Ch3Mode(data[7:6])
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
                self.fm3op[i].play(addr & 0xFC, data)
            case _ if (addr & 3) != 3:
                i = 3 * (port - 0x52) + (addr & 3)
                try: 
                    self.fm[i].play(addr & 0xFC, data)
                except InvalidCommandReport:
                    warnings.warn(InvalidCommand(cmd))
            case _:
                warnings.warn(InvalidCommand(cmd))


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
    def __init__(self, /):
        """Initializes FM channel to its default state."""
        self.op = [Operator(), Operator(), Operator(), Operator()]
        self.freq = FrequencyBitfield(0)
        self.block = 0
        self.opmask = 0
        self.trig = 0
        self.fb = 0
        self.alg = 0
        self.ams = 0
        self.pms = 0
        self.pan = Panning.OFF

    def play(self, addr: int, data: bitfield.Bitfield, /):
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
                self.pan = Panning(data[7:6])
            case _:
                i = [0, 2, 1, 3][(addr >> 2) & 3]
                self.op[i].play(addr & 0xF0, data)

class Operator:
    """FM operator state class.

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
    def __init__(self, /):
        """Initializes FM operator to its default state."""
        self.mult = 0
        self.dt = 0
        self.tl = 127
        self.ar = 31
        self.rs = 0
        self.dr = 31
        self.am = 0
        self.sr = 31
        self.rr = 15
        self.sl = 15
        self.ssg = None

    def play(self, addr: int, data: bitfield.Bitfield, /):
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

class Ch3Op:
    """Channel 3 operator frequency.

    Variables:
        freq - operator frequency
        block - operator block (octave)
    """
    def __init__(self, /):
        self.freq = FrequencyBitfield(0)
        self.block = 0

    def play(self, addr: int, data: bitfield.Bitfield, /):
        """Internal."""
        match addr:
            case 0xA8:
                self.freq.low = data.all
            case 0xAC:
                self.freq.high = data[2:0]
                self.block = data[5:3]

class Ch3Mode(enum.IntEnum):
    """Enumeration for channel 3 modes."""
    NORMAL = 0
    SPECIAL = 1
    CSM = 2

class Panning(enum.IntEnum):
    """Enumeration for panning modes."""
    OFF = 0
    LEFT = 1
    RIGHT = 2
    CENTER = 3

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
