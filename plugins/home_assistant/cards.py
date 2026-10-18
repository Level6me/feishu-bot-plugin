"""Compatibility proxy for ha_cards."""
try:
    from ha_cards import *
except ImportError:
    from .ha_cards import *
