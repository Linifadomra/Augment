#!/usr/bin/env python3
import sys, json, struct, bisect

MAGIC = b"AGMF"
VERSION = 3
_SECTIONS = [("functions","flat"),("structs","name"),("enums","name"),
             ("globals","name"),("typedefs","alias")]

class _Str:
    def __init__(self):
        self.buf = bytearray(b"\x00")
        self.map = {"": 0}
    def add(self, s):
        if s is None:
            s = ""
        if s in self.map:
            return self.map[s]
        off = len(self.buf)
        self.buf += s.encode("utf-8") + b"\x00"
        self.map[s] = off
        return off

def _rva(v):
    if not v:
        return 0
    try:
        return int(v, 16)
    except (ValueError, TypeError) as e:
        raise ValueError(f"malformed rva value {v!r}") from e

def _pack_func(st, f):
    b = bytearray()
    b += struct.pack("<IBxxxQIII", st.add(f["mangled"]), 1 if f["member"] else 0,
                     _rva(f.get("rva")), st.add(f.get("loc")), st.add(f["ret"]),
                     st.add(f.get("self_view")))
    args = f.get("args", [])
    b += struct.pack("<I", len(args))
    for a in args:
        b += struct.pack("<III", st.add(a.get("name")), st.add(a["kind"]), st.add(a.get("view")))
    return bytes(b)

def _pack_struct(st, s):
    b = bytearray(struct.pack("<II", s["size"], len(s["fields"])))
    for fl in s["fields"]:
        b += struct.pack("<IiIiI", st.add(fl["name"]), fl["offset"], st.add(fl["kind"]),
                        fl.get("len", -1), st.add(fl.get("view") or ""))
    return bytes(b)

def _u64(v: int) -> int:
    """Reinterpret any integer as unsigned 64-bit (two's complement)."""
    return v & 0xFFFFFFFFFFFFFFFF

def _pack_enum(st, e):
    b = bytearray(struct.pack("<II", st.add(e.get("owner")), len(e["values"])))
    for v in e["values"]:
        b += struct.pack("<IQ", st.add(v["name"]), _u64(v["value"]))
    return bytes(b)

def _pack_global(st, g):
    return struct.pack("<IxxxxQ", st.add(g["kind"]), _rva(g["addr"]))

def _pack_typedef(st, t):
    return struct.pack("<I", st.add(t["kind"]))

_PACKERS = {"functions": _pack_func, "structs": _pack_struct, "enums": _pack_enum,
            "globals": _pack_global, "typedefs": _pack_typedef}

def pack(manifest):
    from extractor.utility.spinner import Progress
    st = _Str()
    payloads = bytearray()
    sections = []

    total = sum(len(manifest.get(key, [])) for key, _ in _SECTIONS)
    with Progress("records", total=total) as progress:
        for key, namefield in _SECTIONS:
            groups = {}
            for it in manifest.get(key, []):
                groups.setdefault(it[namefield], []).append(it)
            packer = _PACKERS[key]
            entries = []
            for name in sorted(groups):
                recs = groups[name]
                off = len(payloads)
                payloads += struct.pack("<I", len(recs))
                for r in recs:
                    body = packer(st, r)
                    payloads += struct.pack("<I", len(body)) + body
                    progress.increment()
                entries.append((st.add(name), off))
            sections.append(entries)

    out = bytearray(MAGIC) + struct.pack("<II", VERSION, len(st.buf)) + st.buf
    for entries in sections:
        out += struct.pack("<I", len(entries))
        for no, po in entries:
            out += struct.pack("<II", no, po)
    out += struct.pack("<I", len(payloads)) + payloads
    return bytes(out)

class Reader:
    def __init__(self, blob):
        assert blob[:4] == MAGIC, "bad magic"
        self.b = blob
        self.version, stlen = struct.unpack_from("<II", blob, 4)
        if self.version != VERSION:
            raise ValueError(f"unsupported version {self.version}, expected {VERSION}")
        self._stoff = 12
        off = 12 + stlen
        self._sec = {}
        for key, _ in _SECTIONS:
            n, = struct.unpack_from("<I", blob, off); off += 4
            ents = []
            for _ in range(n):
                no, po = struct.unpack_from("<II", blob, off); off += 8
                ents.append((self._s(no), po))
            self._sec[key] = ents
        off += 4
        self._pbase = off

    def _s(self, o):
        end = self.b.index(b"\x00", self._stoff + o)
        return self.b[self._stoff + o:end].decode("utf-8")

    def _payload(self, key, name):
        ents = self._sec[key]
        names = [n for n, _ in ents]
        i = bisect.bisect_left(names, name)
        if i >= len(names) or names[i] != name:
            return None
        return self._pbase + ents[i][1]

    def _read_func(self, p):
        mo, member, rva, lo, ro, svo, nargs = struct.unpack_from("<IBxxxQIIII", self.b, p)
        p += struct.calcsize("<IBxxxQIIII")
        args = []
        for _ in range(nargs):
            no, ko, vo = struct.unpack_from("<III", self.b, p); p += 12
            args.append({"name": self._s(no), "kind": self._s(ko), "view": self._s(vo)})
        return {"mangled": self._s(mo), "member": bool(member), "rva": rva,
                "loc": self._s(lo), "ret": self._s(ro), "self_view": self._s(svo), "args": args}

    def _records(self, key, name):
        p = self._payload(key, name)
        if p is None: return
        count, = struct.unpack_from("<I", self.b, p); p += 4
        for _ in range(count):
            rec_len, = struct.unpack_from("<I", self.b, p); p += 4
            yield p
            p += rec_len

    def lookup_function(self, flat):
        g = self.lookup_function_group(flat)
        return g[0] if g else None
    def lookup_function_group(self, flat):
        return [self._read_func(p) for p in self._records("functions", flat)]
    def lookup_struct(self, name):
        for p in self._records("structs", name):
            size, nfields = struct.unpack_from("<II", self.b, p); q = p + 8
            fields = []
            for _ in range(nfields):
                no, off, ko, ln, vo = struct.unpack_from("<IiIiI", self.b, q); q += 20
                fields.append({"name": self._s(no), "offset": off, "kind": self._s(ko),
                               "len": ln, "view": self._s(vo)})
            return {"size": size, "fields": fields}
        return None
    def lookup_enum(self, name):
        for p in self._records("enums", name):
            oo, nv = struct.unpack_from("<II", self.b, p); q = p + 8
            vals = []
            for _ in range(nv):
                no, val = struct.unpack_from("<IQ", self.b, q); q += 12
                vals.append({"name": self._s(no), "value": val})
            return {"owner": self._s(oo), "values": vals}
        return None
    def lookup_global(self, name):
        for p in self._records("globals", name):
            ko, addr = struct.unpack_from("<IxxxxQ", self.b, p)
            return {"kind": self._s(ko), "addr": addr}
        return None
    def lookup_typedef(self, alias):
        for p in self._records("typedefs", alias):
            ko, = struct.unpack_from("<I", self.b, p)
            return {"kind": self._s(ko)}
        return None

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--exclude-file", default=None)
    ap.add_argument("--exclude-prefix-file", default=None)
    args = ap.parse_args()

    with open(args.input) as f:
        manifest = json.load(f)

    excluded = set()
    if args.exclude_file:
        with open(args.exclude_file) as f:
            excluded = {l.strip() for l in f if l.strip()}

    prefixes = []
    if args.exclude_prefix_file:
        with open(args.exclude_prefix_file) as f:
            prefixes = [l.strip() for l in f if l.strip()]

    if excluded or prefixes:
        manifest["functions"] = [
            fn for fn in manifest.get("functions", [])
            if fn["flat"] not in excluded
            and fn["mangled"] not in excluded
            and not any(fn["flat"].startswith(p) for p in prefixes)
            and not any(fn["mangled"].startswith(p) for p in prefixes)
        ]

    with open(args.output, "wb") as f:
        f.write(pack(manifest))
    print(f"pack: {args.input} -> {args.output}")

if __name__ == "__main__":
    main()
