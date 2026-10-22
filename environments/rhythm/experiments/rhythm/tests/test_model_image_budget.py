import io
import json
from pathlib import Path
import tempfile
import unittest
import struct
import zlib
from PIL import Image

from experiments.rhythm.model_image_budget import certified_input_bound, load_certificate, png_dimensions


class ImageBudgetTests(unittest.TestCase):
    def png(self, size=(390,844)):
        output=io.BytesIO();Image.new('RGB',size).save(output,format='PNG');return output.getvalue()

    def certificate(self):
        return {'schema':1,'model':'gpt-6.1-sol','detail':'high','width':390,'height':844,
                'framed_image_input_tokens':450,
                'response_object':'response.input_tokens','billing':'full_uncertain_reservation_retained'}

    def test_unicode_text_bound_uses_utf8_bytes_and_exact_certificate(self):
        text='节奏🎵';certificate=self.certificate();image=self.png()
        self.assertEqual(png_dimensions(image),(390,844))
        self.assertEqual(certified_input_bound(text,[image],certificate),len(text.encode())+450+128)

    def test_unknown_geometry_or_image_count_uses_original_bound(self):
        text='hello';certificate=self.certificate()
        for images in ([],[self.png((391,844))],[self.png(),self.png()],[b'not-png']):
            self.assertEqual(certified_input_bound(text,images,certificate),4096+5+8192*len(images))

    def test_invalid_header_crc_truncation_and_encoding_fail_closed(self):
        image=self.png();bad=bytearray(image);bad[16]^=1
        bad_color=bytearray(image);bad_color[25]=1
        bad_color[29:33]=struct.pack('>I',zlib.crc32(bytes(bad_color[12:29])) & 0xffffffff)
        for data in (image[:32],bytes(bad),bytes(bad_color),b'GIF89a'+image[6:],image[:8]+b'\x00\x00\x00\x0c'+image[12:]):
            with self.assertRaises(ValueError):png_dimensions(data)
            self.assertEqual(certified_input_bound('',[data],self.certificate()),4096+8192)

    def test_certificate_validation_rejects_mismatch_and_invalid_evidence(self):
        mutations=[('schema',True),('schema',2),('model','other'),('detail','low'),('width',0),
                   ('height',False),('framed_image_input_tokens',0),
                   ('response_object','response'),('billing','released')]
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'certificate.json'
            path.write_text(json.dumps(self.certificate()));self.assertEqual(load_certificate(path,'high'),self.certificate())
            for key,value in mutations:
                with self.subTest(key=key,value=value):
                    certificate=self.certificate();certificate[key]=value;path.write_text(json.dumps(certificate))
                    with self.assertRaises(ValueError):load_certificate(path,'high')
            for certificate in ({},None,{'schema':1}):
                self.assertEqual(certified_input_bound('',[self.png()],certificate),4096+8192)


if __name__=='__main__':unittest.main()
