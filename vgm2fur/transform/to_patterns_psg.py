import bisect
import furnace

def to_patterns_psg(chip):
    noted = list(map(_find_best_notes, chip))
    psg1 = _channel_data(noted, 0)
    psg2 = _channel_data(noted, 1)
    psg3 = _channel_data(noted, 2)
    noise = _channel_data(noted, 3)
    return (_transform(psg1, 0), _transform(psg2, 0), _transform(psg3, 1),
            _transform(noise, 2))

def _make_psg_note_map():
    freqs = [
#         A0    A#0     B0     C1    C#1     D1    D#1     E1     F1    F#1
        0x3F9, 0x3C0, 0x38A, 0x357, 0x327, 0x2FA, 0x2CF, 0x2A7, 0x281, 0x25D,
#         G1    G#1     A1    A#1     B1     C2    C#2     D2    D#2     E2
        0x23B, 0x21B, 0x1FC, 0x1E0, 0x1C5, 0x1AC, 0x194, 0x17D, 0x168, 0x153,
#         F2    F#2     G2    G#2     A2    A#2     B2     C3    C#3     D3
        0x140, 0x12E, 0x11D, 0x10D, 0x0FE, 0x0F0, 0x0E2, 0x0D6, 0x0CA, 0x0BE,
#        D#3     E3     F3    F#3     G3    G#3     A3    A#3     B3     C4
        0x0B4, 0x0AA, 0x0A0, 0x097, 0x08F, 0x087, 0x07F, 0x078, 0x071, 0x06B,
#        C#4     D4    D#4     E4     F4    F#4     G4    G#4     A4    A#4
        0x065, 0x05F, 0x05A, 0x055, 0x050, 0x04C, 0x047, 0x043, 0x040, 0x03C,
#         B4     C5    C#5     D5    D#5     E5     F5    F#5     G5    G#5
        0x039, 0x035, 0x032, 0x030, 0x02D, 0x02A, 0x028, 0x026, 0x024, 0x022,
#         A5    A#5     B5     C6    C#6     D6    D#6     E6     F6    F#6
        0x020, 0x01E, 0x01C, 0x01B, 0x019, 0x018, 0x016, 0x015, 0x014, 0x013,
#         G6    G#6     A6    A#6     B6     C7    C#7     D7    D#7     E7
        0x012, 0x011, 0x010, 0x00F, 0x00E, 0x00D, 0x00C, 0x00B, 0x00A, 0x009,
#         F7    F#7     G7    G#7     A7    A#7     B7     C8    C#8
        0x008, 0x007, 0x006, 0x005, 0x004, 0x003, 0x002, 0x001, 0x000
    ]

    notemap = [(furnace.notes.A0 + i, freq) for (i, freq) in enumerate(freqs)]
    return notemap[::-1]

PSG_NOTE_MAP = _make_psg_note_map()

def _find_best_note(freq):
    i = bisect.bisect(PSG_NOTE_MAP, freq, key=lambda x: x[1])
    if i < 1:
        (note_l, freq_l) = PSG_NOTE_MAP[0]
        (note_r, freq_r) = PSG_NOTE_MAP[1]
        diff_l = freq - freq_l
        diff_r = freq - freq_r
        candidates = [(note_l, diff_l), (note_r, diff_r)]
    elif i >= len(PSG_NOTE_MAP) - 2:
        (note_l, freq_l) = PSG_NOTE_MAP[-2]
        (note_r, freq_r) = PSG_NOTE_MAP[-1]
        diff_l = freq - freq_l
        diff_r = freq - freq_r
        candidates = [(note_l, diff_l), (note_r, diff_r)]
    else:
        (note_l, freq_l) = PSG_NOTE_MAP[i-1]
        (note_c, freq_c) = PSG_NOTE_MAP[i]
        (note_r, freq_r) = PSG_NOTE_MAP[i+1]
        diff_l = freq - freq_l
        diff_c = freq - freq_c
        diff_r = freq - freq_r
        candidates = [(note_l, diff_l), (note_c, diff_c), (note_r, diff_r)]
    return min(candidates, key=lambda x: abs(x[1]))

def _find_best_notes(psg):
    n1, d1 = _find_best_note(psg.tonal[0].freq)
    v1 = psg.tonal[0].vol
    n2, d2 = _find_best_note(psg.tonal[1].freq)
    v2 = psg.tonal[1].vol
    n3, d3 = _find_best_note(psg.tonal[2].freq)
    v3 = psg.tonal[2].vol
    mn = psg.noise.mode
    vn = psg.noise.vol
    return ((n1, d1, v1), (n2, d2, v2), (n3, d3, v3), (mn, vn))

def _channel_data(notetable, channel):
    if 0 <= channel and channel < 2:
        return [x[channel] for x in notetable]
    elif channel == 2:
        return [(n, d, v, m) for (_, _, (n, d, v), (m, _)) in notetable]
    elif channel == 3:
        return [(n, d, v, m) for (_, _, (n, d, _), (m, v)) in notetable]

def _fx_pitch(delta):
    if delta > 0:
        return [furnace.effects.pitch_up(delta)]
    elif delta < 0:
        return [furnace.effects.pitch_down(-delta)]
    else:
        return None

def _transform(psglist, type):
    note_c = furnace.notes.Off
    vol_c = 0
    disp_c = 0
    for psgentry in psglist:
        match type:
            case 0: # tonal
                (note, disp, vol) = psgentry
                silent = False
            case 1: # psg3
                (note, disp, vol, mode) = psgentry
                silent = ((mode & 3) == 3)
            case 2: # noise
                (note, disp, vol, mode) = psgentry
                silent = ((mode & 3) != 3)

        if silent:
            note = furnace.notes.Off
            disp = 0
            vol = 0
        else:
            vol = 15 - vol
            if vol == 0:
                note = furnace.notes.Off
                disp = 0
            disp = -disp

        mask = 0
        mask += 1 if note != note_c else 0
        mask += 2 if disp != disp_c else 0
        mask += 4 if vol != vol_c else 0
        match mask:
            case 0: yield furnace.Entry()
            case 2: yield furnace.Entry(fx=_fx_pitch(disp - disp_c))
            case 4: yield furnace.Entry(vol=vol)
            case 6: yield furnace.Entry(vol=vol, fx=_fx_pitch(disp - disp_c))
            case _:
                if note == furnace.notes.Off:
                    yield furnace.Entry(note=note)
                else:
                    yield furnace.Entry(note=note, ins=0, vol=vol, fx=_fx_pitch(disp))
        note_c = note
        disp_c = disp
        vol_c = vol
