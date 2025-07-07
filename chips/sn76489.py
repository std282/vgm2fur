from . import bitfield
import copy

class TonalChannel:
    def __init__(self):
        self.freq = 0
        self.vol = 15

class NoiseChannel:
    def __init__(self):
        self.mode = 0
        self.vol = 15

class EventBF(bitfield.Bitfield):
    is_action = bitfield.named[7]
    channel = bitfield.named[6:5]
    is_volume = bitfield.named[4]
    payload_l = bitfield.named[3:0]
    payload_h = bitfield.named[5:0]

class SN76489:
    def __init__(self, /, noinit=False):
        if noinit:
            self.tonal = None
            self.noise = None
            self.lastch = None
        else:
            self.tonal = [TonalChannel() for _ in range(3)]
            self.noise = NoiseChannel()
            self.lastch = 0

    def _fields_tuple(self):
        return (self.tonal[0].freq, self.tonal[0].vol,
                self.tonal[1].freq, self.tonal[1].vol,
                self.tonal[2].freq, self.tonal[2].vol,
                self.noise.mode, self.noise.vol, self.lastch)

    def __eq__(self, other):
        return self._fields_tuple() == other._fields_tuple()

    def __hash__(self):
        return hash(self._fields_tuple())

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

    def updated(self, data):
        clone = copy.deepcopy(self)
        clone.update(data)
        return clone

    def __str__(self):
        return '{:1x} {:03x} {:1x} {:03x} {:1x} {:03x} {:1x} {:1x}'.format(
            self.tonal[0].vol, self.tonal[0].freq,
            self.tonal[1].vol, self.tonal[1].freq,
            self.tonal[2].vol, self.tonal[2].freq,
            self.noise.vol, self.noise.mode)
