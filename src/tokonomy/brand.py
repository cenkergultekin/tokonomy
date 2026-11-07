"""One geometry for the SVG mark and both terminal renderers."""
# The selected Kat silhouette, shared with the original SVG direction.
MARK = ((15, 15), (85, 15), (68, 32), (58, 32), (58, 68), (40, 86), (40, 32), (15, 32))


def _path(points):
    return 'M' + ' '.join(f'{x:.3f},{y:.3f}' for x, y in points) + 'Z'


TOKEN_PATH = _path(MARK)
LOGO = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="{TOKEN_PATH}"/></svg>'


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


def terminal_logo(width=10):
    """Sample SVG geometry into square pixels, two per terminal row."""
    def filled(column, row):
        x, y = (column + .5) * 100 / width, (row + .5) * 100 / width
        return _inside(x, y, MARK)
    return tuple(''.join(' ▀▄█'[filled(x, y) + 2 * filled(x, y + 1)]
                         for x in range(width)) for y in range(0, width, 2))
