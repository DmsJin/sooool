"""Conservative token reservations from a fixed-framing image certificate.

No network, pricing assumptions or cache discounts. Unsupported image framing
falls back to the original large bound; it never guesses a smaller image cost.
"""
import json
from pathlib import Path
import re
import struct
import zlib

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
_REQUIRED = {'schema', 'model', 'detail', 'width', 'height', 'framed_image_input_tokens',
             'count_request_sha256', 'response_object', 'billing'}


def _positive_integer(value):
    return type(value) is int and value > 0


def _validate(certificate, detail):
    if not isinstance(certificate, dict) or not _REQUIRED <= set(certificate):
        raise ValueError('Incomplete token certificate')
    if type(certificate['schema']) is not int or certificate['schema'] != 1:
        raise ValueError('Unsupported certificate schema')
    if certificate['model'] != 'gpt-6.1-sol' or detail not in ('low', 'high') or certificate['detail'] != detail:
        raise ValueError('Certificate model/detail mismatch')
    if not all(_positive_integer(certificate[key]) for key in ('width', 'height', 'framed_image_input_tokens')):
        raise ValueError('Certificate dimensions/count must be positive integers')
    digest = certificate['count_request_sha256']
    if not isinstance(digest, str) or re.fullmatch(r'[0-9a-fA-F]{64}', digest) is None:
        raise ValueError('Invalid count request SHA256')
    if certificate['response_object'] != 'response.input_tokens':
        raise ValueError('Certificate must originate from the input-token counter')
    if certificate['billing'] != 'full_uncertain_reservation_retained':
        raise ValueError('Counter reservation must remain fully retained')
    return dict(certificate)


def load_certificate(path, detail):
    """Reject malformed/unmatched evidence; do not silently accept a certificate."""
    return _validate(json.loads(Path(path).read_text()), detail)


def png_dimensions(image):
    """Read only a valid PNG signature and CRC-checked first IHDR chunk."""
    if not isinstance(image, (bytes, bytearray, memoryview)):
        raise ValueError('PNG must be bytes')
    image = bytes(image)
    if len(image) < 33 or image[:8] != PNG_SIGNATURE:
        raise ValueError('Missing/truncated PNG signature or IHDR')
    length = struct.unpack('>I', image[8:12])[0]
    if length != 13 or image[12:16] != b'IHDR':
        raise ValueError('First PNG chunk must be a 13-byte IHDR')
    data = image[16:29]
    expected_crc = struct.unpack('>I', image[29:33])[0]
    if zlib.crc32(b'IHDR' + data) & 0xffffffff != expected_crc:
        raise ValueError('Invalid IHDR checksum')
    width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
    valid_depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
    if not 0 < width <= 0x7fffffff or not 0 < height <= 0x7fffffff:
        raise ValueError('Invalid PNG dimensions')
    if color not in valid_depths or depth not in valid_depths[color] or compression != 0 or filtering != 0 or interlace not in (0, 1):
        raise ValueError('Invalid PNG IHDR encoding')
    return width, height


def certified_input_bound(prompt, images, certificate):
    """Return an uncached input-token upper bound for the existing user framing.

    The certificate is for empty text plus exactly one PNG in one user content.
    Extra images, unknown geometry, malformed headers or invalid certificates
    use the original bound. The prompt remains the caller's original string.
    """
    text_bytes = len(prompt.encode('utf-8'))
    fallback = 4096 + text_bytes + 8192 * len(images)
    if len(images) != 1:
        return fallback
    try:
        certificate = _validate(certificate, certificate.get('detail') if isinstance(certificate, dict) else None)
        dimensions = png_dimensions(images[0])
    except (ValueError, TypeError, KeyError):
        return fallback
    if dimensions != (certificate['width'], certificate['height']):
        return fallback
    return text_bytes + certificate['framed_image_input_tokens'] + 128
