"""Parse shared command values and read API credentials without retaining them."""
import argparse
from decimal import Decimal, InvalidOperation
import getpass
import math
import os
import sys


def positive_decimal(value):
    """Parse a finite, positive dollar amount at the CLI boundary."""
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("Expected a finite positive decimal") from exc
    if not number.is_finite() or number <= 0:
        raise argparse.ArgumentTypeError("Expected a finite positive decimal")
    return number


def positive_float(value):
    """Parse a finite, positive floating-point value at the CLI boundary."""
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected a finite positive number") from exc
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Expected a finite positive number")
    return number


def credential():
    """Read one process-only API credential, prompting only at an interactive terminal."""
    if "OPENAI_API_KEY" in os.environ:
        key = os.environ["OPENAI_API_KEY"].strip()
    elif sys.stdin.isatty():
        key = getpass.getpass("OpenAI API key (process memory only): ").strip()
    else:
        raise ValueError("Set OPENAI_API_KEY before running a paid API command")
    if not key or "\n" in key or "\r" in key:
        raise ValueError("OPENAI_API_KEY must contain one nonempty value")
    return key
