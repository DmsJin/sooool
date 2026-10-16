"""Experimental top-of-screen vision policy; no chart or image processing."""


def prompt(observation, variant='pixels_sparse', **_):
    geometry = observation.geometry
    return (f'Four-lane rhythm screenshot. Lanes left to right D,F,J,K = 0,1,2,3. '
            f'Image {geometry["width"]}x{geometry["height"]} pixels. '
            'Find only BLUE glowing horizontal NOTE rectangles whose vertical '
            'pixel centers are between 0 and 200 inclusive. Ignore lane lines, '
            'keyboard, rings, text, digits and particles. If more than two qualify, '
            'choose the TOPMOST TWO (smallest y). Use the rectangle center to '
            'identify its lane in the tapered highway. Return ONLY JSON '
            '[[lane,y_center],...] sorted TOP TO BOTTOM, at most two entries; '
            '[] if none. Round observed y centers to integer pixels; no decimal '
            'fractions. Give accurate observed centers. No offscreen notes, '
            'song recall, timing extrapolation or prose.')
