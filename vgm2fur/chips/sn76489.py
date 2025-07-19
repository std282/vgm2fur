from vgm2fur import bitfield
import copy


class TonalChannel:
    def __init__(self, noinit=False):
        if noinit: return
        self.freq = 0
        self.vol = 15

    def copy(self):
        clone = TonalChannel(noinit=True)
        clone.freq = self.freq
        clone.vol = self.vol
        return clone


class NoiseChannel:
    def __init__(self, noinit=False):
        if noinit: return
        self.mode = 0
        self.vol = 15

    def copy(self):
        clone = NoiseChannel(noinit=True)
        clone.mode = self.mode
        clone.vol = self.vol
        return clone


class EventBF(bitfield.Bitfield):
    is_action = bitfield.named[7]
    channel = bitfield.named[6:5]
    is_volume = bitfield.named[4]
    payload_l = bitfield.named[3:0]
    payload_h = bitfield.named[5:0]


class SN76489:
    def __init__(self, /, noinit=False):
        if noinit: return
        self.tonal = [TonalChannel() for _ in range(3)]
        self.noise = NoiseChannel()
        self._lastch = None
        self._freq = None

    def _tuple(self):
        return (self.tonal[0].freq,
            self.tonal[0].vol,
            self.tonal[1].freq,
            self.tonal[1].vol,
            self.tonal[2].freq,
            self.tonal[2].vol,
            self.noise.mode,
            self.noise.vol)

    def __eq__(self, other):
        return self._tuple() == other._tuple()

    def ch(self, chan_no):
        match chan_no:
            case 0 | 1 | 2: return self.tonal[chan_no]
            case 3: return self.noise

    def update(self, data):
        data = EventBF(data)
        if data.is_action:
            if data.is_volume:
                self.ch(data.channel).vol = data.payload_l
            elif data.channel != 3:
                self._freq = data.payload_l
                self._lastch = data.channel
            else:
                self.noise.mode = data.payload_l
        else:
            self.tonal[self._lastch].freq = self._freq | (data.payload_h << 4)

    def copy(self):
        clone = SN76489(noinit=True)
        clone.tonal = [ch.copy() for ch in self.tonal]
        clone.noise = self.noise.copy()
        return clone


def csv(chip_states, src_features):
    snft = []
    toft = []
    noft = []
    for feature in src_features:
        match feature:
            case 'psg1' | 'psg2' | 'psg3' | 'noise':
                snft.append(feature)
            case 'psgt':
                snft += 'psg1 psg2 psg3'.split()
            case 'psgx':
                snft += 'psg1 psg2 psg3 noise'.split()
            case 'vol':
                toft.append(feature)
                noft.append(feature)
            case 'freqpsg':
                toft.append(feature)
            case 'nmode':
                noft.append(feature)
    if len(snft) == 0:
        return None
    return _csv(chip_states, snft, toft, noft)

def _csv(chip_states, snft, toft, noft):
    yield _csv_header(snft, toft, noft)
    for chip in chip_states:
        yield _csv_chip(chip, snft, toft, noft)

def _csv_header(snfts, tofts, nofts):
    ss = []
    for snft in snfts:
        match snft:
            case 'psg1' | 'psg2' | 'psg3':
                ss1 = []
                chname = snft.upper() + ' '
                for toft in tofts:
                    match toft:
                        case 'vol': s1 = chname + 'Vol'
                        case 'freqpsg': s1 = chname + 'Freq'
                    ss1.append(s1)
                s = ','.join(ss1)
            case 'noise':
                ss1 = []
                chname = snft.upper() + ' '
                for toft in tofts:
                    match toft:
                        case 'vol': s1 = chname + 'Vol'
                        case 'nmode': s1 = chname + 'Freq'
                    ss1.append(s1)
                s = ','.join(ss1)
        ss.append(s)
    return ','.join(ss)


def _csv_chip(psg, snfts, tofts, nofts):
    ss = []
    for snft in snfts:
        match snft:
            case 'psg1' | 'psg2' | 'psg3':
                ss1 = []
                ch = psg.tonal[int(snft[3]) - 1]
                for toft in tofts:
                    match toft:
                        case 'vol': s1 = f'{ch.vol}'
                        case 'freqpsg': s1 = f'{ch.freq}'
                    ss1.append(s1)
                s = ','.join(ss1)
            case 'noise':
                ss1 = []
                ch = psg.noise
                for toft in tofts:
                    match toft:
                        case 'vol': s1 = f'{ch.vol}'
                        case 'nmode': s1 = f'{ch.mode}'
                    ss1.append(s1)
                s = ','.join(ss1)
        ss.append(s)
    return ','.join(ss)
