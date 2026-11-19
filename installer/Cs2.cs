// CatSystem2 檔案格式（KIF .int 封包、CatScene .cst、FES）讀寫：安裝程式用。
// 演算法參考 GARbro ArcINT.cs（MIT）之格式說明，程式為本專案獨立撰寫；Blowfish 常數由 π 產生（tools/gen_bf_tables.py）。
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;

namespace GrisaiaZhTW
{
    /// <summary>Blowfish（32 位元字組以 little-endian 讀寫，CatSystem2 用法）。</summary>
    partial class Bf
    {
        readonly uint[] P = new uint[18];
        readonly uint[] S = new uint[1024];

        public Bf(byte[] key)
        {
            Array.Copy(P0, P, 18); Array.Copy(S0, S, 1024);
            int j = 0;
            for (int i = 0; i < 18; i++)
            {
                uint d = 0;
                for (int k = 0; k < 4; k++) { d = (d << 8) | key[j]; j = (j + 1) % key.Length; }
                P[i] ^= d;
            }
            uint l = 0, r = 0;
            for (int i = 0; i < 18; i += 2) { Enc(ref l, ref r); P[i] = l; P[i + 1] = r; }
            for (int i = 0; i < 1024; i += 2) { Enc(ref l, ref r); S[i] = l; S[i + 1] = r; }
        }
        uint F(uint x) { return ((S[x >> 24] + S[256 + ((x >> 16) & 255)]) ^ S[512 + ((x >> 8) & 255)]) + S[768 + (x & 255)]; }
        public void Enc(ref uint xl, ref uint xr)
        {
            uint l = xl, r = xr, t;
            for (int i = 0; i < 16; i++) { l ^= P[i]; r ^= F(l); t = l; l = r; r = t; }
            t = l; l = r; r = t; r ^= P[16]; l ^= P[17]; xl = l; xr = r;
        }
        public void Dec(ref uint xl, ref uint xr)
        {
            uint l = xl, r = xr, t;
            for (int i = 17; i > 1; i--) { l ^= P[i]; r ^= F(l); t = l; l = r; r = t; }
            t = l; l = r; r = t; r ^= P[1]; l ^= P[0]; xl = l; xr = r;
        }
        public void DecBytes(byte[] d) { Blocks(d, false); }
        public void EncBytes(byte[] d) { Blocks(d, true); }
        void Blocks(byte[] d, bool enc)
        {
            int n = d.Length / 8 * 8;
            for (int i = 0; i < n; i += 8)
            {
                uint l = BitConverter.ToUInt32(d, i), r = BitConverter.ToUInt32(d, i + 4);
                if (enc) Enc(ref l, ref r); else Dec(ref l, ref r);
                Buffer.BlockCopy(BitConverter.GetBytes(l), 0, d, i, 4);
                Buffer.BlockCopy(BitConverter.GetBytes(r), 0, d, i + 4, 4);
            }
        }
    }

    class MT
    {
        readonly uint[] mt = new uint[624]; int mti = 624;
        public MT(uint seed) { SRand(seed); }
        public void SRand(uint seed)
        {
            for (mti = 0; mti < 624; mti++)
            {
                uint upper = seed & 0xffff0000; seed = 69069 * seed + 1;
                mt[mti] = upper | ((seed & 0xffff0000) >> 16); seed = 69069 * seed + 1;
            }
        }
        public uint Rand()
        {
            uint y;
            if (mti >= 624)
            {
                for (int kk = 0; kk < 624; kk++)
                {
                    y = (mt[kk] & 0x80000000) | (mt[(kk + 1) % 624] & 0x7fffffff);
                    mt[kk] = mt[(kk + 397) % 624] ^ (y >> 1) ^ ((y & 1) != 0 ? 0x9908B0DFu : 0u);
                }
                mti = 0;
            }
            y = mt[mti++];
            y ^= y >> 11; y ^= (y << 7) & 0x9D2C5680; y ^= (y << 15) & 0xEFC60000; y ^= y >> 18;
            return y;
        }
    }

    class KifEntry { public string Name; public uint Offset, Size; public byte[] NewData; }

    /// <summary>加密 KIF 封包：讀目錄、解密單檔、以同一金鑰重組（未修改的檔案直接沿用加密後位元組）。</summary>
    class Kif
    {
        const string Alpha = "zyxwvutsrqponmlkjihgfedcbaZYXWVUTSRQPONMLKJIHGFEDCBA";
        public readonly List<KifEntry> Entries = new List<KifEntry>();
        public readonly uint Seed, Key;
        readonly Bf bf; readonly byte[] raw;
        static readonly Encoding Sjis = Encoding.GetEncoding(932);

        public Kif(byte[] file, uint mainKey)
        {
            raw = file; Key = mainKey;
            if (file.Length < 8 || file[0] != 'K' || file[1] != 'I' || file[2] != 'F' || file[3] != 0) throw new Exception("不是 KIF 封包");
            int count = BitConverter.ToInt32(file, 4);
            string first = CStr(file, 8, 0x40);
            if (first != "__key__.dat") throw new Exception("封包未加密（非預期版本）");
            Seed = BitConverter.ToUInt32(file, 8 + 0x44);
            var tw = new MT(Seed);
            bf = new Bf(BitConverter.GetBytes(tw.Rand()));
            for (int i = 1; i < count; i++)
            {
                int o = 8 + 0x48 * i;
                uint off = BitConverter.ToUInt32(file, o + 0x40) + (uint)i, size = BitConverter.ToUInt32(file, o + 0x44);
                bf.Dec(ref off, ref size);
                tw.SRand(mainKey + (uint)i);
                string name = Name(file, o, tw.Rand(), false);
                Entries.Add(new KifEntry { Name = name, Offset = off, Size = size });
            }
        }
        static string CStr(byte[] b, int o, int n) { int e = o; while (e < o + n && b[e] != 0) e++; return Sjis.GetString(b, o, e - o); }

        static string Name(byte[] b, int o, uint key, bool unused)
        {
            int k = (byte)((key >> 24) + (key >> 16) + (key >> 8) + key);
            var outb = new List<byte>();
            for (int i = 0; i < 0x40 && b[o + i] != 0; i++, k++)
            {
                byte c = b[o + i]; int j = Alpha.IndexOf((char)c);
                if (j != -1) { j -= k % 0x34; if (j < 0) j += 0x34; c = (byte)Alpha[0x33 - j]; }
                outb.Add(c);
            }
            return Sjis.GetString(outb.ToArray());
        }
        static byte[] EncName(string name, uint key)
        {
            byte[] r = Sjis.GetBytes(name);
            int k = (byte)((key >> 24) + (key >> 16) + (key >> 8) + key);
            for (int i = 0; i < r.Length; i++, k++)
            {
                int p = Alpha.IndexOf((char)r[i]);
                if (p != -1) { int j = 0x33 - p + k % 0x34; if (j >= 0x34) j -= 0x34; r[i] = (byte)Alpha[j]; }
            }
            return r;
        }

        public KifEntry Find(string name)
        {
            foreach (var e in Entries) if (string.Equals(e.Name, name, StringComparison.OrdinalIgnoreCase)) return e;
            return null;
        }
        public byte[] Read(KifEntry e)
        {
            var d = new byte[e.Size]; Buffer.BlockCopy(raw, (int)e.Offset, d, 0, (int)e.Size); bf.DecBytes(d); return d;
        }

        public byte[] Build()
        {
            int n = Entries.Count + 1;
            var dir = new byte[0x48 * n];
            Buffer.BlockCopy(Encoding.ASCII.GetBytes("__key__.dat"), 0, dir, 0, 11);
            Buffer.BlockCopy(BitConverter.GetBytes(Seed), 0, dir, 0x44, 4);
            var ms = new MemoryStream();
            uint pos = (uint)(8 + dir.Length);
            var tw = new MT(Seed); tw.Rand();
            var bodies = new List<byte[]>();
            for (int i = 1; i < n; i++)
            {
                var e = Entries[i - 1];
                byte[] body;
                if (e.NewData != null) { body = (byte[])e.NewData.Clone(); bf.EncBytes(body); }
                else { body = new byte[e.Size]; Buffer.BlockCopy(raw, (int)e.Offset, body, 0, (int)e.Size); }
                tw.SRand(Key + (uint)i);
                var nb = EncName(e.Name, tw.Rand());
                int o = 0x48 * i;
                Buffer.BlockCopy(nb, 0, dir, o, nb.Length);
                uint eo = pos, es = (uint)body.Length; bf.Enc(ref eo, ref es);
                Buffer.BlockCopy(BitConverter.GetBytes(eo - (uint)i), 0, dir, o + 0x40, 4);
                Buffer.BlockCopy(BitConverter.GetBytes(es), 0, dir, o + 0x44, 4);
                bodies.Add(body); pos += (uint)body.Length;
            }
            ms.Write(new byte[] { (byte)'K', (byte)'I', (byte)'F', 0 }, 0, 4);
            ms.Write(BitConverter.GetBytes(n), 0, 4);
            ms.Write(dir, 0, dir.Length);
            foreach (var b in bodies) ms.Write(b, 0, b.Length);
            return ms.ToArray();
        }
    }

    static class Zl
    {
        public static byte[] Inflate(byte[] src, int off, int len, int expect)
        {
            using (var ms = new MemoryStream(src, off + 2, len - 2))
            using (var ds = new DeflateStream(ms, CompressionMode.Decompress))
            {
                var outb = new byte[expect]; int got = 0, r;
                while (got < expect && (r = ds.Read(outb, got, expect - got)) > 0) got += r;
                if (got != expect) throw new Exception("解壓長度不符");
                return outb;
            }
        }
        public static byte[] Deflate(byte[] data)
        {
            var ms = new MemoryStream();
            ms.WriteByte(0x78); ms.WriteByte(0x9C);
            using (var ds = new DeflateStream(ms, CompressionLevel.Optimal, true)) ds.Write(data, 0, data.Length);
            uint a = 1, b = 0;
            foreach (var x in data) { a = (a + x) % 65521; b = (b + a) % 65521; }
            uint ad = (b << 16) | a;
            ms.WriteByte((byte)(ad >> 24)); ms.WriteByte((byte)(ad >> 16)); ms.WriteByte((byte)(ad >> 8)); ms.WriteByte((byte)ad);
            return ms.ToArray();
        }
    }

    /// <summary>CatScene：每列 = 0x01, 類型, 字串(NUL 結尾)。</summary>
    class Cst
    {
        public List<uint[]> Inputs = new List<uint[]>();
        public List<byte> Types = new List<byte>();
        public List<byte[]> Lines = new List<byte[]>();

        public Cst(byte[] file)
        {
            if (Encoding.ASCII.GetString(file, 0, 8) != "CatScene") throw new Exception("不是 CatScene");
            int csize = BitConverter.ToInt32(file, 8), dsize = BitConverter.ToInt32(file, 12);
            var body = Zl.Inflate(file, 16, csize, dsize);
            int icount = BitConverter.ToInt32(body, 4), ooff = BitConverter.ToInt32(body, 8), soff = BitConverter.ToInt32(body, 12);
            for (int i = 0; i < icount; i++) Inputs.Add(new[] { BitConverter.ToUInt32(body, 16 + 8 * i), BitConverter.ToUInt32(body, 20 + 8 * i) });
            int nl = (soff - ooff) / 4, st = 16 + soff;
            for (int i = 0; i < nl; i++)
            {
                int p = st + BitConverter.ToInt32(body, 16 + ooff + 4 * i);
                if (body[p] != 1) throw new Exception("CatScene 列格式錯誤");
                int e = p + 2; while (body[e] != 0) e++;
                Types.Add(body[p + 1]);
                var s = new byte[e - p - 2]; Buffer.BlockCopy(body, p + 2, s, 0, s.Length); Lines.Add(s);
            }
        }
        public byte[] Build()
        {
            var itab = new MemoryStream();
            foreach (var x in Inputs) { itab.Write(BitConverter.GetBytes(x[0]), 0, 4); itab.Write(BitConverter.GetBytes(x[1]), 0, 4); }
            var strt = new MemoryStream(); var offs = new MemoryStream();
            for (int i = 0; i < Lines.Count; i++)
            {
                offs.Write(BitConverter.GetBytes((int)strt.Length), 0, 4);
                strt.WriteByte(1); strt.WriteByte(Types[i]); strt.Write(Lines[i], 0, Lines[i].Length); strt.WriteByte(0);
            }
            int ooff = (int)itab.Length, soff = ooff + (int)offs.Length;
            var body = new MemoryStream();
            body.Write(BitConverter.GetBytes((int)(itab.Length + offs.Length + strt.Length)), 0, 4);
            body.Write(BitConverter.GetBytes(Inputs.Count), 0, 4);
            body.Write(BitConverter.GetBytes(ooff), 0, 4);
            body.Write(BitConverter.GetBytes(soff), 0, 4);
            itab.WriteTo(body); offs.WriteTo(body); strt.WriteTo(body);
            var raw = body.ToArray(); var comp = Zl.Deflate(raw);
            var f = new MemoryStream();
            f.Write(Encoding.ASCII.GetBytes("CatScene"), 0, 8);
            f.Write(BitConverter.GetBytes(comp.Length), 0, 4); f.Write(BitConverter.GetBytes(raw.Length), 0, 4);
            f.Write(comp, 0, comp.Length);
            return f.ToArray();
        }
    }

    /// <summary>FES 前端腳本：'FES\0' + 壓縮長 + 原長 + 保留 + zlib 文字。</summary>
    static class Fes
    {
        public static byte[] Text(byte[] file) { return Zl.Inflate(file, 16, BitConverter.ToInt32(file, 4), BitConverter.ToInt32(file, 8)); }
        public static byte[] Pack(byte[] orig, byte[] text)
        {
            var comp = Zl.Deflate(text); var f = new MemoryStream();
            f.Write(orig, 0, 4); f.Write(BitConverter.GetBytes(comp.Length), 0, 4); f.Write(BitConverter.GetBytes(text.Length), 0, 4);
            f.Write(orig, 12, 4); f.Write(comp, 0, comp.Length);
            return f.ToArray();
        }
    }
}
