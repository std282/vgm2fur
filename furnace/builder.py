import struct

def pack(format, *data):
    return struct.pack('<' + format, *data)

def byte(x):
    return struct.pack('<B', x)

def short(x):
    return struct.pack('<H', x)

def long(x):
    return struct.pack('<L', x)

def qlong(x):
    return struct.pack('<Q', x)

def string(x):
    return x.encode('utf-8') + b'\0'

def float(x):
    return struct.pack('<f', x)

def bl_length(byteslist):
    return sum(len(x) for x in byteslist)
