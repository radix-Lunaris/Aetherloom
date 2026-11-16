"""Minimal enum surface from CraftLink punch.py for its STUN diagnostics.

GPLv3; upstream attribution and exact source pins are in SOURCE.json.
No punching or inbound-admission behavior is replaced by this adapter.
"""
import enum

FILTER_ADF_OR_EIF='adf_or_eif'

class NatSub(enum.Enum):
    CONE='cone'
    EASY_INC='sym_easy_inc'
    EASY_DEC='sym_easy_dec'
    HARD='sym_hard'
    UNKNOWN='unknown'
    @property
    def label(self):
        from .stun import NAT_SUB_LABEL
        return NAT_SUB_LABEL[self.value]

class Filter(enum.Enum):
    EIF='eif'
    ADF='adf'
    ADF_OR_EIF='adf_or_eif'
    APDF='apdf'
    UNKNOWN='unknown'
    @property
    def label(self):
        from .stun import NAT_FILTER_LABEL
        return NAT_FILTER_LABEL[self.value]
