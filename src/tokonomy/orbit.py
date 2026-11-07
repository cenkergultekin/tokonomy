"""Original shaded token sculpture and restrained economic motion."""
import math
from rich.text import Text
from textual.widgets import Static

WORDMARK = [
 r'  _        _                                  ',
 r' | |_ ___ | | _____  _ __   ___  _ __ ___  _   _',
 r" | __/ _ \| |/ / _ \| '_ \ / _ \| '_ ` _ \| | | |",
 r' | || (_) |   < (_) | | | | (_) | | | | | | |_| |',
 r'  \__\___/|_|\_\___/|_| |_|\___/|_| |_| |_|\__, |',
 r'                                          |___/ ',
]


def green(value):
    value = max(0, min(1, value))
    return '#%02x%02x%02x' % (int(51+145*value), int(103+141*value), int(61+143*value))


class TokenOrbit(Static):
    phase = 0.0
    paused = False

    def on_mount(self):
        self.styles.height = 12
        self.set_interval(1/12, self.tick)

    def tick(self):
        if not self.paused:
            self.phase += 0.055
            self.refresh()

    def sculpture(self, width=23, height=10):
        grid = [[(' ', 0.0) for _ in range(width)] for _ in range(height)]
        angle = self.phase*0.7
        face = abs(math.cos(angle))
        half_width = 2 + 6.5*face
        for row in range(height):
            for col in range(width):
                x, y = (col-width/2)/half_width, (row-(height-1)/2)/3.7
                radius = math.hypot(x,y)
                if radius > 1: continue
                rim = radius > 0.78
                shine = max(0, 1-abs(x+0.35*math.sin(angle)-0.15))
                light = 0.18+0.4*shine+0.2*(1-y)/2
                if rim:
                    light += 0.15
                    glyph = '#%+'[(col+row)%3]
                else:
                    glyph = '.,:;=+'[min(5,int(light*6))]
                    # Engraved token mark, foreshortened with its face.
                    if face > 0.3 and ((abs(y+0.3)<0.17 and abs(x)<0.5) or (abs(x)<0.15 and -0.3<y<0.55)):
                        glyph, light = '@', 1.0
                grid[row][col] = (glyph,light)
        # Small coins travel along arcs around the main token.
        for i in range(3):
            t = (self.phase*0.22+i/3)%1
            col = int(t*(width-3))
            row = int(1+(height-3)*(1-t)**2)
            for offset,glyph in enumerate('($)'):
                if grid[row][col+offset][0]==' ':
                    grid[row][col+offset] = (glyph,0.25+0.4*math.sin(math.pi*t))
        return grid

    def render(self):
        result = Text(no_wrap=True, overflow='crop')
        wide = self.size.width >= 68
        grid = self.sculpture(width=16 if self.size.width < 82 else 23)
        for row in range(10):
            if wide:
                for glyph,light in grid[row]: result.append(glyph,green(light))
                result.append('   ')
            if 1 <= row <= 6:
                text = WORDMARK[row-1] if self.size.width >= 52 else ('tokonomy' if row==3 else '')
                for col,ch in enumerate(text):
                    # Continuous broad sheen; no hard palette steps or flashing.
                    light = 0.4+0.35*(0.5+0.5*math.sin(col*0.065-self.phase*0.8))
                    result.append(ch,green(light))
            elif row==8:
                result.append('Token observability for AI harnesses.', '#9aaa9b')
            elif row==9:
                pass
            result.append('\n' if row<9 else '')
        return result
