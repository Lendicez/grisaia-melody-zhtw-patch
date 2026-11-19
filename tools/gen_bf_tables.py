"""產生 Blowfish 初始常數（P 18 個、S 1024 個 32 位元字 = π 小數部分的十六進位數字）→ installer/BfTables.cs。
需要 mpmath；並以 pycryptodome 驗證（若有安裝）。用法：python gen_bf_tables.py OUT.cs
"""
import sys, struct
import mpmath

def tables():
    mpmath.mp.dps = 10200
    x = mpmath.mp.pi - 3; words = []
    for _ in range(18 + 1024):
        x *= (1 << 32); w = int(mpmath.floor(x)); words.append(w); x -= w
    return words[:18], words[18:]

def fmt(arr):
    return ',\n'.join('            ' + ', '.join('0x%08X' % v for v in arr[i:i + 8]) for i in range(0, len(arr), 8))

if __name__ == '__main__':
    P, S = tables()
    assert P[0] == 0x243F6A88 and S[0] == 0xD1310BA6
    src = ('// Blowfish 初始常數（π 的十六進位小數），由 tools/gen_bf_tables.py 產生。\nnamespace GrisaiaZhTW\n{\n    partial class Bf\n    {\n'
           '        static readonly uint[] P0 = {\n' + fmt(P) + '\n        };\n        static readonly uint[] S0 = {\n' + fmt(S) + '\n        };\n    }\n}\n')
    open(sys.argv[1], 'w', encoding='utf-8').write(src)
    print('ok')
