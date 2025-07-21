from . import builder

def sample(data, rate, name=''):
    samp = [
        b'SMP2',
        builder.long(0),
        builder.string(name),
        builder.long(len(data)),  # length of sample
        builder.long(rate),  # compatibility rate (??)
        builder.long(rate),  # C-4 rate
        builder.byte(8),  # 8-bit PCM
        builder.byte(0),  # loop: forward (not that it matters...)
        builder.byte(0),  # BRR emphasis (wth is that?)
        builder.byte(0),  # dithering: no
        builder.long(0xFFFFFFFF),  # loop start: none  
        builder.long(0xFFFFFFFF),  # loop end: none
        builder.long(0xFFFFFFFF) * 4,  # sample presence bitfields
        data
    ]
    samp[1] = builder.long(builder.bl_length(samp[2:]))
    return b''.join(samp)
