"""CatSystem2 CST (CatScene) read / write.

File: "CatScene" + uint32 compressed_size + uint32 decompressed_size + zlib(body)
Body: uint32 script_len, uint32 input_count, uint32 offset_table_off, uint32 string_table_off
      (offsets relative to byte 16 of the body)
      input table : input_count x (uint32 line_count, uint32 first_line_index)
      offset table: line_total x uint32 (offset of each line inside string table)
      string table: each line = 0x01, type, cstring (cp932)
Line types: 0x02 input(wait), 0x03 page, 0x20 message, 0x21 name, 0x30 command, 0xF0 filename, 0xF1 line no.
"""
import struct, zlib

TYPE_NAMES = {0x02: 'input', 0x03: 'page', 0x20: 'message', 0x21: 'name', 0x30: 'command', 0xF0: 'file', 0xF1: 'lineno'}

class Scene:
    def __init__(self, inputs, lines):
        self.inputs = inputs   # list of (line_count, first_index)
        self.lines = lines     # list of [type, bytes]

    @classmethod
    def load(cls, data):
        if data[:8] != b'CatScene': raise ValueError('not CatScene')
        csize, dsize = struct.unpack_from('<II', data, 8)
        body = zlib.decompress(data[16:16 + csize])
        if len(body) != dsize: raise ValueError('size mismatch')
        slen, icount, ooff, soff = struct.unpack_from('<IIII', body, 0)
        base = 16
        inputs = [struct.unpack_from('<II', body, base + 8 * i) for i in range(icount)]
        nlines = (soff - ooff) // 4
        offs = struct.unpack_from('<%dI' % nlines, body, base + ooff)
        st = base + soff
        lines = []
        for o in offs:
            p = st + o
            if body[p] != 0x01: raise ValueError('bad line marker at %d' % p)
            t = body[p + 1]
            e = body.index(b'\0', p + 2)
            lines.append([t, body[p + 2:e]])
        sc = cls(list(inputs), lines)
        sc._orig_body = body
        return sc

    def build_body(self):
        icount = len(self.inputs)
        itab = b''.join(struct.pack('<II', *x) for x in self.inputs)
        strtab = bytearray(); offs = []
        for t, s in self.lines:
            offs.append(len(strtab)); strtab += bytes([0x01, t]) + bytes(s) + b'\0'
        otab = struct.pack('<%dI' % len(offs), *offs)
        ooff = len(itab); soff = ooff + len(otab)
        body = struct.pack('<IIII', len(itab) + len(otab) + len(strtab), icount, ooff, soff) + itab + otab + bytes(strtab)
        return body

    def dump(self, level=9):
        body = self.build_body()
        comp = zlib.compress(body, level)
        return b'CatScene' + struct.pack('<II', len(comp), len(body)) + comp
