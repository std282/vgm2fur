"""Provides functions for parsing and building byte structures."""

from dataclasses import dataclass
import struct

pack = struct.pack
unpack = struct.unpack

@dataclass(slots=True)
class Walker:
    data: bytes
    offset: int = 0

    @property
    def top(self):
        return self.data[self.offset]

    @property
    def rest(self):
        return StricterAccessor(self.data[self.offset:])

    def __len__(self):
        return len(self.data)

    def __getitem__(self, key):
        return self.data[self.offset:][key]

    @property
    def left(self):
        return len(self) - self.offset

    def bytes(self, length):
        if self.left < length:
            raise IndexError('requested amount of bytes is out of range')
        begin = self.offset
        self.offset += length
        return self.data[begin : self.offset]

    def unpack(self, fmt, off=None):
        ret = struct.unpack_from(fmt, buffer=self.data, offset=self.offset)
        delta = struct.calcsize(fmt)
        self.offset += delta
        return ret

    def byte(self):
        byte = self.top
        self.offset += 1
        return byte

@dataclass(slots=True)
class StricterAccessor:
    data: bytes

    def __getitem__(self, key):
        match key:
            case slice():
                if key.stop is None:
                    required = 0
                else:
                    required = key.stop
            case int(x):
                required = x
            case _:
                required = 0
        if len(self.data) < required:
            raise IndexError('requested amount of bytes is out of range')
        return self.data[key]
