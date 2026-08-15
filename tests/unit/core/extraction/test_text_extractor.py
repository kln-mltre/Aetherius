"""Tests for core/extraction/text_extractor.py

Decoding is the one place where the two engines could disagree in silence, so every rule asserted
here has a twin in ``sdks/engine/test/extraction.test.js`` — including the degenerate byte
sequences, whose expected values come from CPython and are copied verbatim into the JavaScript
test. A conformance case (``run/18-text-body-and-charset``) compares the two engines end to end;
these tests pin what a corpus served over HTTP cannot easily carry.
"""

from __future__ import annotations

import pytest

from aetherius.core.extraction.text_extractor import (
    TextExtractSpec,
    decode_body,
    extract_text,
    resolve_charset,
)

pytestmark = pytest.mark.unit


def _text(body: bytes, content_type: str | None = None) -> str:
    """The extractor's answer for a single named spec, through its real entry point."""
    extracted = extract_text(body, {"body": TextExtractSpec(from_="text")}, content_type)
    return str(extracted["body"])


def test_utf8_body_is_rendered_verbatim() -> None:
    assert _text(
        "BEGIN:VCALENDAR\r\nSUMMARY:Noël\r\n".encode(), "text/calendar; charset=utf-8"
    ) == ("BEGIN:VCALENDAR\r\nSUMMARY:Noël\r\n")


def test_declared_iso_8859_1_is_decoded_per_the_header() -> None:
    assert _text("Prénom;Zoé".encode("iso-8859-1"), "text/csv; charset=ISO-8859-1") == "Prénom;Zoé"


def test_a_mislabelled_body_decodes_the_same_way_it_is_labelled() -> None:
    # UTF-8 bytes served as latin-1: the mojibake is the *correct* answer, and both engines must
    # produce the same one. Guessing the encoding would make them differ on real French sources.
    assert _text("Prénom".encode(), "text/csv; charset=iso-8859-1") == "PrÃ©nom"


def test_windows_1252_maps_its_own_window() -> None:
    assert _text(b"\x80 \x99 \x8d", "text/plain; charset=windows-1252") == "€ ™ �"


def test_no_content_type_and_unknown_labels_fall_back_to_utf8() -> None:
    assert _text("café".encode()) == "café"
    assert _text("café".encode(), "text/calendar") == "café"
    assert _text("café".encode(), "text/plain; charset=shift_jis") == "café"


def test_an_empty_body_is_an_empty_string_not_none() -> None:
    assert _text(b"") == ""


def test_a_binary_body_is_replaced_never_raised() -> None:
    # An image is a sign the Blueprint aimed at the wrong source; it is not the engine's place to
    # decide that, so it decodes what it can and says nothing.
    assert _text(b"\x89PNG\r\n\x1a\n\xff\xfe", "image/png") == "�PNG\r\n\x1a\n��"


def test_a_bom_is_kept() -> None:
    # `Response.text()` strips it, the Python codec does not, and Python is the reference.
    assert _text(b"\xef\xbb\xbfBEGIN") == "﻿BEGIN"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"\xff", "�"),
        (b"\xff\xfe", "��"),
        (b"\xc3", "�"),
        (b"\xc3(", "�("),
        (b"\xe0\xa0", "�"),
        (b"\xf0\x9f\x98", "�"),
        (b"\xf0\x9f\x98\x81", "\U0001f601"),
        (b"\xc0\xaf", "��"),
        (b"\xed\xa0\x80", "���"),
        (b"\xf4\x90\x80\x80", "����"),
        (b"\xe0\x80\xaf", "���"),
    ],
)
def test_invalid_utf8_replaces_one_char_per_maximal_subpart(raw: bytes, expected: str) -> None:
    # The count is observable, so it is pinned: the embedded decoder implements the WHATWG
    # algorithm precisely to land on these values.
    assert decode_body(raw, "text/plain") == expected


def test_charset_resolution_reads_the_parameter_not_the_type() -> None:
    assert resolve_charset(None) == "utf-8"
    assert resolve_charset("text/plain") == "utf-8"
    assert resolve_charset('text/plain; charset="ISO-8859-1"') == "iso-8859-1"
    assert resolve_charset("text/plain;charset=latin-1") == "iso-8859-1"
    assert resolve_charset("text/plain; charset = Windows-1252 ") == "cp1252"
    assert resolve_charset("text/plain; boundary=charset=x") == "utf-8"
