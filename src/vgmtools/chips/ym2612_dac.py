from . import VGMCommand

class Chip:
    """YM2612 DAC part model class.
    
    Tracks which samples are being played.
    """
    def __init__(self, /):
        self.ptr = 0
        self.trig = 0

    id = 'ym2612/dac'
    supported_commands = frozenset([0xE0, *range(0x80, 0x90)])
    def play(self, cmd: VGMCommand, /):
        """Updates chip state according to VGM command.

        Positional arguments:
            cmd - VGM command, tuple of kind (0xE0, ptr) or (0x8X,)
        """
        match cmd:
            case (x,) if 0x80 <= x and x <= 0x8F:
                self.trig += 1
                self.ptr += 1
            case (0xE0, ptr):
                self.ptr = ptr
