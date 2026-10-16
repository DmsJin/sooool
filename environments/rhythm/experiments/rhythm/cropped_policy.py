"""Top-200-pixel crop only; no detection, thresholding or hidden state."""
from dataclasses import replace
import io

from PIL import Image


def prompt(observation, variant='pixels_cropped_v1', **_):
    return ('Find blue note rectangles. Lanes 0,1,2,3 left-right. Return only JSON '
            '[[lane,integer_y],...] for the topmost 2, sorted top-to-bottom; [] if none.')


def crop_observation(observation):
    with Image.open(io.BytesIO(observation.png)) as source:
        cropped = source.crop((0, 0, source.width, min(200, source.height)))
        output = io.BytesIO()
        cropped.save(output, format='PNG')
        width, height = cropped.size
    geometry = dict(observation.geometry)
    geometry.update(width=width, height=height, view='rendered_canvas_top200_crop',
                    crop_origin_y=0, full_canvas_height=observation.geometry['height'])
    # Original hitline and canvas_top remain unchanged: cropped pixel y is the
    # same observed y used by the deterministic public-geometry timing conversion.
    return replace(observation, png=output.getvalue(), geometry=geometry)
