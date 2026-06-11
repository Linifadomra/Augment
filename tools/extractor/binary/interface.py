"""
extractor/binary/interface.py

Abstract base for debug-info backends. Each backend implements extract_rvas()
    extract_rvas() - Used by the merge step to enrich AST records.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict
from extractor.model import Manifest


class DebugInfoBackend(ABC):

    #: Short name used in --debug-format and error messages.
    name: str = ""

    @abstractmethod
    def extract_rvas(self, binary_path: str) -> Dict[str, int]:
        """
        Return {mangled_name: rva} for every symbol that has an address.
        RVAs are plain ints (not hex strings) at this layer; the merge
        step converts to the "0x..." string the manifest expects.
        """
