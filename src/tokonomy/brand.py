"""One geometry for the SVG coin and both terminal renderers."""
import math

COIN = tuple((32 + 28 * math.cos(i * math.tau / 128),
              32 + 28 * math.sin(i * math.tau / 128)) for i in range(128))
LETTER = ((19, 19), (45, 19), (45, 27), (36, 27),
          (36, 46), (28, 46), (28, 27), (19, 27))


def _path(points):
    return 'M' + ' '.join(f'{x:.3f},{y:.3f}' for x, y in points) + 'Z'


TOKEN_PATH = _path(COIN) + _path(LETTER)
LOGO = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="{TOKEN_PATH}"/></svg>'


def _inside(x, y, polygon):
    inside = False
    previous = polygon[-1]
    for current in polygon:
        ax, ay = previous
        bx, by = current
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
        previous = current
    return inside


def terminal_logo(width=16):
    """Sample SVG geometry into square pixels, two per terminal row."""
    def filled(column, row):
        x, y = (column + .5) * 64 / width, (row + .5) * 64 / width
        return _inside(x, y, COIN) and not _inside(x, y, LETTER)
    return tuple(''.join(' ▀▄█'[filled(x, y) + 2 * filled(x, y + 1)]
                         for x in range(width)) for y in range(0, width, 2))
