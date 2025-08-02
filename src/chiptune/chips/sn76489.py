from . import VGMCommand
import bitfield

class Chip:
    """SN76489 chip behaviour model class.

    Variables:
        tonal - tonal channels (PSG1-PSG3) state
        noise - noise channel state

    Methods:
        play - update chip state according to VGM command
    """
    def __init__(self, /):
        """Initializes chip to default state.
        
        Default state: 
            - all channels volume = 15 (no sound)
            - tonal channels frequency = 0
            - noise mode = 0
        """
        self.tonal = (TonalChannel(), TonalChannel(), TonalChannel())
        self.noise = NoiseChannel()
        self._prevtonal = None

    supported_commands = frozenset([0x50])
    """List of VGM command numbers that can be handled by SN76489."""
    id = 'sn76489'

    def play(self, cmd: VGMCommand, /):
        """Updates chip state according to VGM command.

        Positional arguments:
            cmd - VGM command, tuple of kind (0x50, x)
        """
        (_, data) = cmd
        match decode(bitfield.make(data)):
            case TonalVolume(i, vol):
                self.tonal[i].vol = vol
            case TonalFreqLow(i, freq_l):
                self.tonal[i].freq.low = freq_l
                self._prevtonal = self.tonal[i]
            case TonalFreqHigh(i, freq_h):
                self._prevtonal.freq.high = freq_q
            case NoiseVolume(vol):
                self.noise.vol = vol
            case NoiseMode(vol):
                self.noise.mode = mode


class TonalChannel:
    """Tonal channel (PSG1-PSG3)."""
    def __init__(self, /):
        """Initializes tonal channel to its default state."""
        self.freq = FrequencyBitfield(0)
        self.vol = 15

class FrequencyBitfield(bitfield.Bitfield):
    """Divides PSG "frequency" into two fields, according to write order."""
    low = bitfield.named[3:0]
    high = bitfield.named[9:4]


class NoiseChannel:
    """Noise channel."""
    def __init__(self, /):
        """Initializes noise channel to default state."""
        self.mode = 0
        self.vol = 15


class TonalVolume(NamedTuple): ch: int; vol: int
class TonalFreqLow(NamedTuple): ch: int; freq: int
class TonalFreqHigh(NamedTuple): freq: int
class NoiseVolume(NamedTuple): vol: int
class NoiseMode(NamedTuple): mode: int
Decoded = TonalVolume | TonalFreqLow | TonalFreqHigh | NoiseVolume | NoiseMode

def decode(data: bitfield.Bitfield, /) -> Decoded:
    """Decodes VGM command data field."""
    match (data[7], data[6:5], data[4]):
        case (0, _, _):
            return TonalFreqHigh(data[5:0])
        case (1, 3, 0):
            return NoiseMode(data[2:0])
        case (1, 3, 1):
            return NoiseVolume(data[3:0])
        case (1, i, 0):
            return TonalFreqLow(i, data[3:0])
        case (1, i, 1):
            return TonalVolume(i, data[3:0])
