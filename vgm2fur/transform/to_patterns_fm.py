from typing import NamedTuple
import bisect
from vgm2fur import furnace, bitfield
from vgm2fur import AppError as Vgm2FurError

def prepare(chip):
    fm1, fm2, fm3, fm4, fm5, fm6 = _split_fm(chip)
    if _has_csm(fm3):
        raise CsmNotSupported()

    fm1 = list(map(_to_key_voice_lfo, fm1))
    fm2 = list(map(_to_key_voice, fm2))
    fm4 = list(map(_to_key_voice, fm4))
    fm5 = list(map(_to_key_voice, fm5))
    fm6 = list(map(_to_key_voice_dac, fm6))

    if _has_special_mode(fm3):
        fm3 = list(_to_4key_voice_ch3(fm3))
    else:
        fm3 = list(map(_to_key_voice, fm3))

    return fm1, fm2, fm3, fm4, fm5, fm6

def collect_voices(channels, voice_start):
    return _collect_voices(channels, voice_start)

def is_special(channel3):
    return (type(channel3[0]) is tuple 
        and type(channel3[0][0]) is tuple
        and len(channel3[0][0]) == 4)

def split_special(channel3):
    split = ([], [], [], [])
    for state, voice in channel3:
        for i in range(4):
            split[i].append((state[i], voice))
    return split

def to_patterns(chdata, /, voices, *, channel=''):
    match channel.lower():
        case 'fm1':
            return _transform(chdata, voices, 1)
        case 'fm6':
            return _transform(chdata, voices, 2)
        case _:
            return _transform(chdata, voices, 0)

class FmFreqClass:
    def __init__(self):
        freq_map = _make_fm_freq_map()
        dist_min = (freq_map[1][1] - freq_map[0][1]) // 2
        dist_max = (freq_map[-1][1] - freq_map[-2][1]) // 2
        self.freq_map = freq_map[1:-1]
        self.freq_min = self.freq_map[0][1] - dist_min
        self.freq_max = self.freq_map[-1][1] + dist_max
        self.overfreq_map = _make_fm_overfreq_map(self.freq_map)
        self.underfreq_map = _make_fm_underfreq_map(self.freq_map)

def _make_fm_freq_map():
    freqs = [
    #     B-
        0x260,
    #     C      C#     D      D#     E      F
        0x284, 0x2AA, 0x2D2, 0x2FD, 0x32B, 0x35B,
    #     F#     G      G#     A      A#     B
        0x38E, 0x3C4, 0x3FE, 0x43B, 0x47B, 0x4C0,
    #     C+
        0x508,
    ]
    return [(furnace.notes.b_1 + i, freq) for (i, freq) in enumerate(freqs)]

def _make_fm_overfreq_map(freq_map):
    overfreq_map = []
    note = furnace.notes.C8
    shift = 1
    i = 0
    freq = freq_map[i][1] << shift
    while freq < 0x800:
        overfreq_map.append((note, freq))
        note += 1
        shift += 0 if i < 12 else 1
        i = (i + 1) if i < 12 else 0
        freq = freq_map[i][1] << shift
    return overfreq_map

def _make_fm_underfreq_map(freq_map):
    underfreq_map = []
    note = furnace.notes.b_1
    shift = 1
    i = 11
    freq = freq_map[i][1] >> shift
    while note >= 0:
        underfreq_map.append((note, freq))
        note -= 1
        shift += 0 if i > 0 else 1
        i = (i - 1) if i > 0 else 11
        freq = freq_map[i][1] >> shift
    return underfreq_map[::-1]

FmFreq = FmFreqClass()

def _find_best_note(freq, block):
    if freq < FmFreq.freq_min:
        while freq < FmFreq.freq_min and block > 0:
            freq *= 2
            block -= 1
        
        if freq < FmFreq.freq_min:
            return _find_best_note_bisect(freq, FmFreq.underfreq_map)
    elif freq > FmFreq.freq_max:
        if block < 7:
            freq //= 2
            block += 1
        else:
            return _find_best_note_bisect(freq, FmFreq.overfreq_map)
    note, disp = _find_best_note_bisect(freq, FmFreq.freq_map)
    note += block * 12
    return note, disp

def _find_best_note_bisect(freq, freq_map):
    i = bisect.bisect(freq_map, freq, key=lambda x: x[1])
    if i < 1:
        (note_l, freq_l) = freq_map[0]
        (note_r, freq_r) = freq_map[1]
        diff_l = freq - freq_l
        diff_r = freq - freq_r
        candidates = [(note_l, diff_l), (note_r, diff_r)]
    elif i > len(freq_map) - 2:
        (note_l, freq_l) = freq_map[-2]
        (note_r, freq_r) = freq_map[-1]
        diff_l = freq - freq_l
        diff_r = freq - freq_r
        candidates = [(note_l, diff_l), (note_r, diff_r)]
    else:
        (note_l, freq_l) = freq_map[i-1]
        (note_c, freq_c) = freq_map[i]
        (note_r, freq_r) = freq_map[i+1]
        diff_l = freq - freq_l
        diff_c = freq - freq_c
        diff_r = freq - freq_r
        candidates = [(note_l, diff_l), (note_c, diff_c), (note_r, diff_r)]
    return min(candidates, key=lambda x: abs(x[1]))

def _split_fm(fmtable):
    chs = tuple(list() for _ in range(6))
    for fm in fmtable:
        for i in range(6):
            chs[i].append(fm.channels[i])
    return chs

def _has_special_mode(fm3):
    return any(cs.mode == 1 for cs in fm3)

def _has_csm(fm3):
    return any(cs.mode == 2 for cs in fm3)

class Key(NamedTuple):
    note: int
    disp: int
    vol: int
    id: int
    pan: int

def _to_key_voice(ch):
    if ch.opmask != 0:
        note, disp = _find_best_note(ch.freq, ch.block)
        voice = _extract_voice(ch)
        voice, vol = _normalize_voice(voice)
        key = Key(note=note, disp=disp, vol=vol,
            id=ch.keyid, pan=ch.pan)
    else:
        voice = None
        key = Key(note=furnace.notes.Off, disp=0, vol=0, id=ch.keyid, pan=ch.pan)
    return key, voice

def _to_4key_voice_ch3(chs):
    opmask_prev = [0, 0, 0, 0]
    keyid_prev = [0, 0, 0, 0]
    for ch in chs:
        keys = [None] * 4
        opmask = bitfield.make(ch.opmask)
        if opmask.all == 0:
            keyid = ch.keyid
            for i in range(4):
                keys[i] = Key(note=furnace.notes.Off, disp=0, vol=0, id=keyid, pan=ch.pan)
                opmask_prev[i] = 0
                keyid_prev[i] = keyid
            voice = None
        elif ch.mode == 1:
            for i in range(4):
                if opmask[i]:
                    op = ch.operators[i]
                    note, disp = _find_best_note(op.freq, op.block)
                    vol = 0x7F - op.tl
                else:
                    note = furnace.notes.Off
                    disp = 0
                    vol = 0
                if opmask[i] != opmask_prev[i]:
                    keyid = ch.keyid
                else:
                    keyid = keyid_prev[i]
                keys[i] = Key(note=note, disp=disp, vol=vol, id=keyid, pan=ch.pan)
                opmask_prev[i] = opmask[i]
                keyid_prev[i] = keyid
            voice = _normalize_voice_ch3(_extract_voice(ch))
        else:
            keyid = ch.keyid
            note, disp = _find_best_note(ch.freq, ch.block)
            for i in range(4):
                if opmask[i]:
                    note_o = note
                    disp_o = disp
                    vol = 0x7F - ch.operators[i].tl
                else:
                    note_o = furnace.notes.Off
                    disp_o = 0
                    vol = 0
                keys[i] = Key(note=note_o, disp=disp_o, vol=vol, id=keyid, pan=ch.pan)
                opmask_prev[i] = opmask[i]
                keyid_prev[i] = keyid
            voice = _normalize_voice_ch3(_extract_voice(ch))
        yield tuple(keys), voice

class CsmNotSupported(Vgm2FurError):
    def __init__(self):
        super().__init__()
    def __str__(self):
        return f'YM2612 CSM is not supported'

def _to_key_voice_dac(ch6):
    key, voice = _to_key_voice(ch6)
    return key, voice, ch6.dac_en

def _to_key_voice_lfo(ch1):
    key, voice = _to_key_voice(ch1)
    lfo = ch1.lfo if ch1.lfo_en else None
    return key, voice, lfo

def _extract_voice(ch):
    op1 = ch.op(1)
    op2 = ch.op(2)
    op3 = ch.op(3)
    op4 = ch.op(4)
    return furnace.instr.FMVoice(
        ch3=False, alg=ch.alg, fb=ch.fb, pms=ch.pms, ams=ch.ams, op=(
            furnace.instr.FMOp(mult=op1.mult, dt=op1.dt, tl=op1.tl, ar=op1.ar,
                rs=op1.rs, dr=op1.dr, am=op1.am, sr=op1.sr, rr=op1.rr, sl=op1.sl,
                ssg=op1.ssg, ssg_en=op1.ssg_en),
            furnace.instr.FMOp(mult=op2.mult, dt=op2.dt, tl=op2.tl, ar=op2.ar,
                rs=op2.rs, dr=op2.dr, am=op2.am, sr=op2.sr, rr=op2.rr, sl=op2.sl,
                ssg=op2.ssg, ssg_en=op2.ssg_en),
            furnace.instr.FMOp(mult=op3.mult, dt=op3.dt, tl=op3.tl, ar=op3.ar,
                rs=op3.rs, dr=op3.dr, am=op3.am, sr=op3.sr, rr=op3.rr, sl=op3.sl,
                ssg=op3.ssg, ssg_en=op3.ssg_en),
            furnace.instr.FMOp(mult=op4.mult, dt=op4.dt, tl=op4.tl, ar=op4.ar,
                rs=op4.rs, dr=op4.dr, am=op4.am, sr=op4.sr, rr=op4.rr, sl=op4.sl,
                ssg=op4.ssg, ssg_en=op4.ssg_en)))

def _normalize_voice(voice):
    match voice.alg:
        case 0 | 1 | 2 | 3:
            vol = voice.op[3].tl
            voice = voice._replace(op=(
                voice.op[0], voice.op[1],
                voice.op[2], voice.op[3]._replace(tl=0)))
        case 4:
            tl = (voice.op[1].tl, voice.op[3].tl)
            vol = min(tl)
            tl = (tl[0] - vol, tl[1] - vol)
            voice = voice._replace(op=(
                voice.op[0], voice.op[1]._replace(tl=tl[0]),
                voice.op[2], voice.op[3]._replace(tl=tl[1])))
        case 5 | 6:
            tl = (voice.op[1].tl, voice.op[2].tl, voice.op[3].tl)
            vol = min(tl)
            tl = (tl[0] - vol, tl[1] - vol, tl[2] - vol)
            voice = voice._replace(op=(
                voice.op[0],
                voice.op[1]._replace(tl=tl[0]),
                voice.op[2]._replace(tl=tl[1]),
                voice.op[3]._replace(tl=tl[2])))
        case 7:
            tl = (voice.op[0].tl, voice.op[1].tl, voice.op[2].tl, voice.op[3].tl)
            vol = min(tl)
            tl = (tl[0] - vol, tl[1] - vol, tl[2] - vol, tl[3] - vol)
            voice = voice._replace(op=(
                voice.op[0]._replace(tl=tl[0]),
                voice.op[1]._replace(tl=tl[1]),
                voice.op[2]._replace(tl=tl[2]),
                voice.op[3]._replace(tl=tl[3])))
    return voice, 0x7F - vol

def _normalize_voice_ch3(voice):    
    return voice._replace(ch3=True, op=(
        voice.op[0]._replace(tl=0),
        voice.op[1]._replace(tl=0),
        voice.op[2]._replace(tl=0),
        voice.op[3]._replace(tl=0)))

def _collect_voices(chlist, init=0):
    voices = dict()
    index = init
    for i, ch in enumerate(chlist):
        for state in ch:
            if i == 0 or i == 5:
                (_, voice, _) = state
            else:
                (_, voice) = state
            if voice is not None and voice not in voices:
                voices[voice] = index
                index += 1
    return voices

def _fx_pitch(delta):
    if delta > 0:
        return furnace.effects.pitch_up(delta)
    elif delta < 0:
        return furnace.effects.pitch_down(-delta)
    else:
        return None

def _fx_pan(pan):
    match pan:
        case 0: return furnace.effects.pan(0x00)
        case 1: return furnace.effects.pan(0x01)
        case 2: return furnace.effects.pan(0x10)
        case 3: return furnace.effects.pan(0x11)

def _fx_legato(on):
    if on:
        return furnace.effects.legato(0x01)
    else:
        return furnace.effects.legato(0x00)

def _fx_lfo(value):
    if value is None:
        return furnace.effects.lfo(0x00)
    else:
        return furnace.effects.lfo(0x10 + value)

def _transform(ch, voices, type):
    note_c = furnace.notes.Off
    disp_c = 0
    vol_c = 0
    keyid_c = -1
    ins_c = -1
    pan_c = 0
    lfo_c = None
    legato = False
    for state in ch:
        lfo = lfo_c
        match type:
            case 1:
                key, voice, lfo = state
                silent = False
            case 2:
                key, voice, dac = state
                silent = (dac != 0)
            case _:
                key, voice = state
                silent = False
        if silent:
            note = furnace.notes.Off
        else:
            note, disp, vol, keyid, pan = key
        fx = []

        if lfo != lfo_c:
            fx.append(_fx_lfo(lfo))
            lfo_c = lfo

        if note == furnace.notes.Off:
            if legato: fx.append(_fx_legato(0))
            if note == note_c:
                note = None
            yield furnace.Entry(note=note, fx=fx)
            note_c = furnace.notes.Off
            disp_c = 0
            vol_c = 0
            legato = False
            continue

        ins = voices[voice]
        if keyid != keyid_c:
            if disp != 0: fx.append(_fx_pitch(disp))
            if legato: fx.append(_fx_legato(0))
            if pan != pan_c: fx.append(_fx_pan(pan))
            yield furnace.Entry(note=note, ins=ins, vol=vol, fx=fx)
            note_c = note
            disp_c = disp
            vol_c = vol
            keyid_c = keyid
            ins_c = ins
            pan_c = pan
            legato = False
        elif note != note_c or ins != ins_c:
            if disp != 0: fx.append(_fx_pitch(disp))
            if not legato: fx.append(_fx_legato(1))
            if pan != pan_c: fx.append(_fx_pan(pan))
            ins = voices[voice]
            yield furnace.Entry(note=note, ins=ins, vol=vol, fx=fx)
            note_c = note
            disp_c = disp
            vol_c = vol
            ins_c = ins
            pan_c = pan
            legato = True
        else:
            if disp != disp_c: fx.append(_fx_pitch(disp - disp_c))
            if pan != pan_c: fx.append(_fx_pan(pan))
            vol_o = vol if vol != vol_c else None
            yield furnace.Entry(vol=vol_o, fx=fx)
            disp_c = disp
            vol_c = vol
            pan_c = pan
