"""VGM reading and parsing module.

Constants:
    SAMPLE_RATE - VGM sample rate

Functions:
    load - load VGM from file

Exceptions:
    BadVgmFile - thrown when loaded file is not a VGM file
    UnexpectedEOF - thrown when EOF condition is reached during parsing
"""

from .vgm import (
    # functions
    load, 
    # classes
    BadVgmFile, 
    UnexpectedEOF,
    # typing
    Command,
)

SAMPLE_RATE = 44100
