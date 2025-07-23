from vgm2fur import vgm

class Sampler:
    separation_margin = 512
    def __init__(self, /, *, noinit=False):
        if noinit: return
        self.keyid = 0
        self.start = 0
        self._length = [0]
        self._duration = [0]
        self.pause = 0
        self.idle = True

    @property
    def length(self):
        return self._length[0]
    @length.setter
    def length(self, value):
        self._length[0] = value
    @property
    def duration(self):
        return self._duration[0]
    @duration.setter
    def duration(self, value):
        self._duration[0] = value
    @property
    def rate(self):
        return vgm.SAMPLE_RATE * self.length // self.duration

    def __eq__(self, other):
        return self.keyid == other.keyid

    def set(self, ptr):
        if self.duration > 0 or self.idle:
            self.keyid += 1
            self.start = ptr
            self._length = [0]
            self._duration = [0]
            self.pause = 0
            self.idle = False
        else:
            self.start = ptr
            self.length = 0
            self.pause = 0

    def play(self):
        if self.length > 0:
            if self.pause > self.separation_margin:
                if self.duration > 0:
                    # situation: PTR_SET S w S w ... S w S LONG_SILENCE
                    # resolution: pretend a new sample started
                    self.keyid += 1
                    self.start += self.length
                    self._length = [0]
                    self._duration = [0]
                else:
                    # situation: PTR_SET S S ... S LONG_SILENCE
                    # resolution: cut current sample
                    self.start += self.length
                    self.length = 0
            else:
                self.duration += self.pause
        self.length += 1
        self.pause = 0

    def wait(self, duration):
        self.pause += duration

    def copy(self):
        clone = Sampler(noinit=True)
        clone.keyid = self.keyid
        clone.start = self.start
        clone._length = self._length
        clone._duration = self._duration
        clone.pause = self.pause
        clone.idle = self.idle
        return clone

def csv(chip_states, features):
    fts = []
    for ft in features:
        if ft in {'dacid', 'dacinfo'}:
            fts.append(ft)
    if len(fts) == 0:
        return None
    return _csv(chip_states, fts)

def _csv(chip_states, fts):
    elements = []
    for ft in fts:
        match ft:
            case 'dacid':
                elements.append('DAC ID')
            case 'dacinfo':
                elements.append('DAC Sample Pos:Len')
    yield ','.join(elements)

    for state in chip_states:
        elements = []
        for ft in fts:
            match ft:
                case 'dacid':
                    elements.append(f'{state.keyid}')
                case 'dacinfo':
                    elements.append(f'{state.start}:{state.length}')
        yield ','.join(elements)
