"""
extractor/model.py

Typed containers for every record the extraction pipeline produces.
The schema here is the contract between the Python pipeline and pack.py /
the C++ manifest reader.  A field may only be added or changed with an
explicit version bump and sign-off.

All classes expose:
  .to_dict()          -> plain dict suitable for json.dump / pack.py
  .from_dict(d)       -> classmethod, reconstructs from that same dict
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional


# ---------------------------------------------------------------------------
# Leaf types
# ---------------------------------------------------------------------------

@dataclass
class Arg:
    """A single function parameter."""
    name: Optional[str]
    kind: str                       # ffi kind string, e.g. "i32", "ptr", "str"
    view: Optional[str] = None      # pointee struct name when kind == "ptr"

    def to_dict(self) -> dict:
        d: dict = {"name": self.name, "kind": self.kind}
        if self.view is not None:
            d["view"] = self.view
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Arg":
        return cls(name=d.get("name"), kind=d["kind"], view=d.get("view"))


@dataclass
class Field:
    """A struct / union / class member."""
    name: str
    offset: int
    kind: str
    len: Optional[int] = None       # set when kind == "str" (char array length)
    view: Optional[str] = None      # pointee struct name when kind == "ptr"

    def to_dict(self) -> dict:
        d: dict = {"name": self.name, "offset": self.offset, "kind": self.kind}
        if self.len is not None:
            d["len"] = self.len
        if self.view is not None:
            d["view"] = self.view
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Field":
        return cls(
            name=d["name"], offset=d["offset"], kind=d["kind"],
            len=d.get("len"), view=d.get("view"),
        )


@dataclass
class EnumValue:
    name: str
    value: int

    def to_dict(self) -> dict:
        return {"name": self.name, "value": self.value}

    @classmethod
    def from_dict(cls, d: dict) -> "EnumValue":
        return cls(name=d["name"], value=d["value"])


# ===
# Top-level record types
# ===

@dataclass
class Function:
    flat: str                           # demangled, namespace-flattened name
    mangled: str                        # raw mangled symbol
    member: bool                        # is a non-static member function
    ret: str                            # ffi kind string for return type
    args: List[Arg] = field(default_factory=list)
    self_view: Optional[str] = None     # owning struct name when member == True
    rva: Optional[str] = None           # hex string e.g. "0x1a2b3c", or None
    loc: Optional[str] = None           # "file.cpp:42" source location, or None

    def to_dict(self) -> dict:
        return {
            "flat":      self.flat,
            "mangled":   self.mangled,
            "member":    self.member,
            "self_view": self.self_view,
            "rva":       self.rva,
            "loc":       self.loc,
            "ret":       self.ret,
            "args":      [a.to_dict() for a in self.args],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Function":
        return cls(
            flat=d["flat"], mangled=d["mangled"], member=d["member"],
            ret=d["ret"], args=[Arg.from_dict(a) for a in d.get("args", [])],
            self_view=d.get("self_view"), rva=d.get("rva"), loc=d.get("loc"),
        )


@dataclass
class Struct:
    name: str
    size: int
    fields: List[Field] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "size": self.size,
                "fields": [f.to_dict() for f in self.fields]}

    @classmethod
    def from_dict(cls, d: dict) -> "Struct":
        return cls(name=d["name"], size=d["size"],
                   fields=[Field.from_dict(f) for f in d.get("fields", [])])


@dataclass
class Enum:
    name: str # qualified: "Owner::EnumName" or "EnumName"
    values: List[EnumValue] = field(default_factory=list)
    owner: Optional[str] = None # enclosing struct/class name, if any

    def to_dict(self) -> dict:
        return {"name": self.name, "owner": self.owner,
                "values": [v.to_dict() for v in self.values]}

    @classmethod
    def from_dict(cls, d: dict) -> "Enum":
        return cls(name=d["name"], owner=d.get("owner"),
                   values=[EnumValue.from_dict(v) for v in d.get("values", [])])


@dataclass
class Global:
    name: str
    kind: str
    addr: Optional[str] = None # hex string, or None if stripped

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "addr": self.addr}

    @classmethod
    def from_dict(cls, d: dict) -> "Global":
        return cls(name=d["name"], kind=d["kind"], addr=d.get("addr"))


@dataclass
class Typedef:
    alias: str
    kind: str

    def to_dict(self) -> dict:
        return {"alias": self.alias, "kind": self.kind}

    @classmethod
    def from_dict(cls, d: dict) -> "Typedef":
        return cls(alias=d["alias"], kind=d["kind"])


# ===
# Manifest container
# ===

MANIFEST_VERSION = 2

@dataclass
class Manifest:
    version: int = MANIFEST_VERSION
    functions: List[Function] = field(default_factory=list)
    structs:   List[Struct]   = field(default_factory=list)
    enums:     List[Enum]     = field(default_factory=list)
    globals:   List[Global]   = field(default_factory=list)
    typedefs:  List[Typedef]  = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version":   self.version,
            "functions": [f.to_dict() for f in self.functions],
            "structs":   [s.to_dict() for s in self.structs],
            "enums":     [e.to_dict() for e in self.enums],
            "globals":   [g.to_dict() for g in self.globals],
            "typedefs":  [t.to_dict() for t in self.typedefs],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Manifest":
        return cls(
            version   = d.get("version", MANIFEST_VERSION),
            functions = [Function.from_dict(f) for f in d.get("functions", [])],
            structs   = [Struct.from_dict(s)   for s in d.get("structs",   [])],
            enums     = [Enum.from_dict(e)      for e in d.get("enums",     [])],
            globals   = [Global.from_dict(g)   for g in d.get("globals",   [])],
            typedefs  = [Typedef.from_dict(t)  for t in d.get("typedefs",  [])],
        )