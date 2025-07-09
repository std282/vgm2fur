from . import bitfield
import copy
from typing import NamedTuple

class TonalChannel:
    def __init__(self):
        self.freq = 0
        self.vol = 15
    def as_tuple(self):
        return TonalChannel_NT(freq=self.freq, vol=self.vol)

class NoiseChannel:
    def __init__(self):
        self.mode = 0
        self.vol = 15
    def as_tuple(self):
        return NoiseChannel_NT(mode=self.mode, vol=self.vol)

class EventBF(bitfield.Bitfield):
    is_action = bitfield.named[7]
    channel = bitfield.named[6:5]
    is_volume = bitfield.named[4]
    payload_l = bitfield.named[3:0]
    payload_h = bitfield.named[5:0]

class SN76489:
    def __init__(self):
        self.tonal = [TonalChannel() for _ in range(3)]
        self.noise = NoiseChannel()
        self.lastch = 0

    def as_tuple(self):
        return SN76489_NT(
            tonal=tuple(t.as_tuple() for t in self.tonal),
            noise=self.noise.as_tuple(),
            lastch=self.lastch)

    def _channel(self, chan_no):
        match chan_no:
            case 0 | 1 | 2: return self.tonal[chan_no]
            case 3: return self.noise
            case _: return None

    def update(self, data):
        data = EventBF(data)
        if data.is_action:
            if data.is_volume:
                self._channel(data.channel).vol = data.payload_l
            elif data.channel != 3:
                self.tonal[data.channel].freq = data.payload_l
                self.lastch = data.channel
            else:
                self.noise.mode = data.payload_l
        else:
            self.tonal[self.lastch].freq |= data.payload_h << 4


class TonalChannel_NT(NamedTuple):
    freq: int
    vol: int

class NoiseChannel_NT(NamedTuple):
    mode: int
    vol: int

class SN76489_NT(NamedTuple):
    tonal: tuple[TonalChannel_NT, TonalChannel_NT, TonalChannel_NT]
    noise: NoiseChannel_NT
    lastch: int
    def __str__(self):
        elements = [
            f'PSG1: {self.tonal[0].freq:03X} {self.tonal[0].vol:X}',
            f'PSG2: {self.tonal[1].freq:03X} {self.tonal[1].vol:X}',
            f'PSG3: {self.tonal[2].freq:03X} {self.tonal[2].vol:X}',
            f'NOISE: {self.noise.mode:X} {self.noise.vol:X}',
        ]
        return '  '.join(elements)
