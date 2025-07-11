from . import builder
import zlib

TARGET_FURNACE_VERSION = 228  # Furnace v0.6.8.1

def _make_entry_data(note, ins, vol, fx):
    mask = 0
    masklen = 1
    payload = b''
    if note is not None:
        mask |= 1
        payload += note.to_bytes(1)
    if ins is not None:
        mask |= 2
        payload += ins.to_bytes(1)
    if vol is not None:
        mask |= 4
        payload += vol.to_bytes(1)
    if fx is not None and len(fx) > 0:
        if len(fx) == 1:
            mask |= 8 | 16
            (fxtype, fxval) = fx[0]
            payload += fxtype.to_bytes(1) + fxval.to_bytes(1)
        else:
            if len(fx) > 8: fx = fx[:8]
            if len(fx) <= 4:
                mask |= 8 | 16 | 32
                masklen = 2
            else:
                mask |= 8 | 16 | 32 | 64
                masklen = 3
            m = 256 | 512
            for fxtype, fxval in fx:
                payload += fxtype.to_bytes(1) + fxval.to_bytes(1)
                mask |= m
                m <<= 2
    return mask.to_bytes(masklen, 'little') + payload

class Entry:
    def __init__(self, note=None, ins=None, vol=None, fx=None):
        self.data = _make_entry_data(note, ins, vol, fx)
        # self.note = note
        # self.ins = ins
        # self.vol = vol
        # self.fx = fx
        self.fxcount = len(fx) if fx is not None else 0

    @property
    def empty(self):
        return self.data == b'\0'

class Wait:
    __match_args__ = ('length', )
    def __init__(self, length):
        self.length = length

class Emit:
    __match_args__ = ('data', )
    def __init__(self, data):
        self.data = data

def _pass_entries(entries, onresult):
    """Passthrough. Remembers the biggest effect count across all entries.
    Sends found maximum of effect count to the callback `onresult`."""
    maxfxcount = 0
    for entry in entries:
        yield entry
        if entry.fxcount > maxfxcount:
            maxfxcount = entry.fxcount
    onresult(maxfxcount)

def _stream(entries):
    skipcount = 0
    for entry in entries:
        if not entry.empty:
            if skipcount > 0:
                yield Wait(skipcount)
                skipcount = 0
            yield Emit(entry.data)
        else:
            skipcount += 1

def _skip_n(n):
    while n > 128:
        yield b'\xFE'
        n -= 128
    if n >= 2:
        n = (n - 2) + 0x80
        yield n.to_bytes(1)
    else:
        yield b'\0'

class EndOfPattern:
    def __init__(self):
        pass

def _chunks(maxlen, stream):
    left = maxlen
    for elem in stream:
        match elem:
            case Emit(data):
                yield data
                left -= 1
            case Wait(n):
                while n > left:
                    yield from _skip_n(left)
                    n -= left
                    yield EndOfPattern()
                    left = maxlen
                # now n <= left
                yield from _skip_n(n)
                left -= n
        if left == 0:
            yield EndOfPattern()
            left = maxlen
    if left < maxlen:
        yield EndOfPattern()

def _patterns(channel, chunks):
    index = 0
    payload = bytearray()
    for chunk in chunks:
        match chunk:
            case bytes():
                payload += chunk
            case EndOfPattern():
                payload += b'\xFF'
                pat = [
                    b'PATN',
                    builder.long(0),  # size
                    builder.byte(0),  # subsong
                    builder.byte(channel),
                    builder.short(index),
                    builder.string(''),  # pattern name (left blank)
                    bytes(payload)
                ]
                pat[1] = builder.long(builder.bl_length(pat[2:]))
                yield b''.join(pat)
                index += 1
                payload = bytearray()

def _empty_pattern(channel, index):
    pat = [
        b'PATN',
        builder.long(0),  # size
        builder.byte(0),  # subsong
        builder.byte(channel),
        builder.short(index),
        builder.string(''),  # pattern name (left blank)
        b'\xFF'
    ]
    pat[1] = builder.long(builder.bl_length(pat[2:]))
    return b''.join(pat)

class Module:
    def __init__(self):
        self.channel_count = 10
        self.pattern_length = 128
        self.ticks_per_second = 60
        self.pattern_matrix = [list() for _ in range(self.channel_count)]
        self.effects_count = [1] * self.channel_count
        self.order_count = 0
        self.pattern_count = 0
        self.instruments = []
        self.ym2612_volume = 1.0
        self.sn76489_volume = 1.0
        self.song_comment = ''

    @property
    def instrument_count(self):
        return len(self.instruments)

    def add_patterns(self, entries, channel):
        if type(channel) is str:
            match channel.lower():
                case 'fm1': channel = 0
                case 'fm2': channel = 1
                case 'fm3': channel = 2
                case 'fm4': channel = 3
                case 'fm5': channel = 4
                case 'fm6': channel = 5
                case 'psg1': channel = 6
                case 'psg2': channel = 7
                case 'psg3': channel = 8
                case 'psg4' | 'noise': channel = 9
                case _:
                    raise TypeError('invalid value for "channel"')
        else:
            raise TypeError('invalid type for "channel"')

        def _update_effects_count(fxcount):
            if fxcount > 0:
                self.effects_count[channel] = fxcount

        new_patterns = list(
            _patterns(channel,
                _chunks(self.pattern_length,
                    _stream(
                        _pass_entries(
                            entries, _update_effects_count)))))

        if len(new_patterns) > self.pattern_count:
            self.order_count = len(new_patterns)
        self.pattern_count += len(new_patterns)
        self.pattern_matrix[channel] = new_patterns

    def add_instrument(self, ins):
        self.instruments.append(ins)

    def prebuild(self):
        for chno, ch in enumerate(self.pattern_matrix):
            index = 0
            while len(ch) < self.order_count:
                ch.append(_empty_pattern(chno, index))
                index += 1
                self.pattern_count += 1

    def build(self, *, comp=True):
        self.prebuild()
        fileptr = 0
        file = bytearray()
        header = [
            b'-Furnace module-',
            builder.short(TARGET_FURNACE_VERSION),
            builder.short(0),  # reserved
            builder.long(0),   # song info pointer
            builder.qlong(0),  # reserved
        ]
        # computing length of header and writing it to header
        header[3] = builder.long(builder.bl_length(header))
        # writing header to file
        header = b''.join(header)
        file += header
        fileptr += len(header)

        info = [
            b'INFO',
            builder.long(0),   # size
            builder.byte(1),   # time base
            builder.byte(1),   # speed 1
            builder.byte(1),   # speed 2
            builder.byte(0),   # initial arp time
            builder.float(float(self.ticks_per_second)),
            builder.short(self.pattern_length),
            builder.short(self.order_count),
            builder.byte(0),   # highlight A
            builder.byte(0),   # highlight B
            builder.short(len(self.instruments)),
            builder.short(0),  # wavetable count
            builder.short(0),  # sample count
            builder.long(self.pattern_count),
            builder.byte(2),   # system: Genesis
            builder.byte(0) * 31,  # end of system list + 30 bytes padding
            builder.byte(0x40) * 32,  # for compatibility
            builder.byte(0) * 32,  # for compatibility
            builder.long(0) * 32,  # chip flags pointers
            builder.string(''),    # song name
            builder.string(''),    # song author
            builder.float(440.0),  # A-4 tuning
            builder.byte(0),       # compat flags
            builder.byte(0),       # compat flags: non-linear pitch (very important!)
            builder.byte(0) * 18,  # compat flags
        ]

        ins_ptr = [builder.long(0)] * len(self.instruments)
        pat_ptr = [builder.long(0)] * self.pattern_count
        info_2 = [
            b''.join(builder.byte(n) for n in range(self.order_count)) * self.channel_count,  # orders
            b''.join(builder.byte(n) for n in self.effects_count),  # effects columns
            builder.byte(1) * self.channel_count,  # channel hide status
            builder.byte(0) * self.channel_count,  # channel collapse status
            builder.string('') * self.channel_count,  # channel names
            builder.string('') * self.channel_count,  # channel short names
            builder.string(self.song_comment),
            builder.float(1.0),  # master volume
            builder.byte(0) * 28,  # ext compat flags
            builder.short(150),  # v.tempo numerator
            builder.short(150),  # v.tempo denominator
            builder.string(''),  # first subsong name
            builder.string(''),  # first subsong comment
            builder.byte(0),     # no. of additional subsongs
            builder.byte(0) * 3,  # reserved
            builder.string('SEGA Genesis'),  # system name
            builder.string(''),  # album/cat./game name
            builder.string(''),  # song name (JP)
            builder.string(''),  # song author (JP)
            builder.string('SEGA MegaDrive'),  # system name (JP)
            builder.string(''),  # album/cat./game name (JP)
            builder.float(self.ym2612_volume),  # chip 1 volume
            builder.float(0.0),  # chip 1 panning
            builder.float(0.0),  # chip 1 front/rear balance
            builder.float(self.sn76489_volume),  # chip 2 volume
            builder.float(0.0),  # chip 2 panning
            builder.float(0.0),  # chip 2 front/rear balance
            builder.long(0),     # patchbay connection count
            builder.byte(1),     # automatic patchbay
            builder.byte(0) * 8,  # yet more compat flags
            builder.byte(0) * 17,  # speed pattern
            builder.byte(0),     # groove entry count
            builder.long(0),     # pointer to instruments asset dir
            builder.long(0),     # pointer to wavetables asset dir
            builder.long(0),     # pointer to samples asset dir
        ]

        # computing song info size
        info_size = sum(map(builder.bl_length, [info[2:], ins_ptr, pat_ptr, info_2]))
        # writing song info size to song info
        info[1] = builder.long(info_size)
        # updating file pointer as if we have already written song info
        fileptr += info_size + 8

        # writing instrument asset directory pointer to song info
        info_2[-3] = builder.long(fileptr)
        # creating instrument asset directory data
        ins_adir = _make_instrument_asset_dir(len(self.instruments))
        # updating file pointer with as if we have already written it
        fileptr += len(ins_adir)

        # writing wavetable and sample asset directory pointer to song info
        info_2[-2] = builder.long(fileptr)
        info_2[-1] = info_2[-2]
        # creating empty asset directory data
        empty_adir = _make_empty_asset_dir()
        # updating file pointer with as if we have already written it
        fileptr += len(empty_adir)

        for i, ins in enumerate(self.instruments):
            # writing instrument data pointer to song info
            ins_ptr[i] = builder.long(fileptr)
            # updating file pointer as if we have already written instrument data
            fileptr += len(ins)

        patterns = _flatten_list_list(self.pattern_matrix)
        assert len(patterns) == self.pattern_count
        for i, pat in enumerate(patterns):
            # writing pattern data pointer to song info
            pat_ptr[i] = builder.long(fileptr)
            # updating file pointer as if we have already written pattern data
            fileptr += len(pat)

        # writing song info
        file += b''.join(info + ins_ptr + pat_ptr + info_2)

        # writing asset directories
        file += ins_adir + empty_adir
        # writing instrument data
        file += b''.join(self.instruments)
        # writing pattern data
        file += b''.join(patterns)

        if comp:
            return zlib.compress(bytes(file))
        else:
            return bytes(file)


def _make_instrument_asset_dir(instcount):
    adir = [
        b'ADIR',
        builder.long(0),  # size
        builder.long(1),  # no. of dirs
        builder.string(''),  # dir name
        builder.short(instcount),  # no. of assets in dir
        b''.join(x.to_bytes(1) for x in range(instcount))  # assets in dir
    ]
    adir[1] = builder.long(builder.bl_length(adir[2:]))
    return b''.join(adir)

def _make_empty_asset_dir():
    adir = [
        b'ADIR',
        builder.long(0),  # size
        builder.long(0),  # no. of dirs
    ]
    adir[1] = builder.long(builder.bl_length(adir[2:]))
    return b''.join(adir)

def _flatten_list_list(ll):
    l_total = []
    for l in ll:
        l_total += l
    return l_total
