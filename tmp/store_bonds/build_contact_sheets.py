from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SOURCE = Path(r'C:\Users\Xylitol\Desktop\chess开发文件\store')
OUTPUT = Path(__file__).resolve().parent
COLS = 4
CELL_WIDTH = 320
CARD_HEIGHT = 269
TRAIT_TOP = 145
TRAIT_BOTTOM = 235
SCALE = 2


def font(size: int):
    for path in (
        r'C:\Windows\Fonts\msyh.ttc',
        r'C:\Windows\Fonts\simhei.ttf',
        r'C:\Windows\Fonts\arial.ttf',
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


for cost_dir in sorted(SOURCE.glob('cost*')):
    files = sorted(cost_dir.glob('*.png'))
    rows = (len(files) + COLS - 1) // COLS
    cell_height = 230
    sheet = Image.new('RGB', (COLS * CELL_WIDTH, rows * cell_height), '#202020')
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(files):
        image = Image.open(path).convert('RGB')
        crop = image.crop((0, TRAIT_TOP, image.width, min(TRAIT_BOTTOM, image.height)))
        crop = crop.resize((crop.width * SCALE, crop.height * SCALE), Image.Resampling.NEAREST)
        x = (index % COLS) * CELL_WIDTH
        y = (index // COLS) * cell_height
        sheet.paste(crop, (x, y + 36))
        label = path.stem.removeprefix('store_')
        draw.text((x + 4, y + 4), label, fill='white', font=font(20))
    sheet.save(OUTPUT / f'{cost_dir.name}_traits.png')
