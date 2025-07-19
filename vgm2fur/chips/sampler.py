class Sampler:
    def __init__(self, /, *, noinit=False):
        if noinit: return
        self.keyid = 0
        self.begin = 0
        self._length = [0]

    @property
    def length(self):
        return self._length[0]

    @length.setter
    def length(self, value):
        self._length[0] = value

    def __eq__(self, other):
        return self.keyid == other.keyid

    def set(self, ptr):
        self.begin = ptr
        self._length = [0]
        self.keyid += 1

    def play(self):
        self.length += 1

    def copy(self):
        clone = Sampler(noinit=True)
        clone.keyid = self.keyid
        clone.begin = self.begin
        clone._length = self._length
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
                    elements.append(f'{state.begin}:{state.length}')
        yield ','.join(elements)
