"""標題選單文字（sys_title）專用重繪：粗明體、上黑下暗紅垂直漸層，停留狀態加白色光暈；維持原中心點。
python ui_title.py SRC_DIR FONT_DIR OUT_DIR
"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ITEMS = ['開始遊戲', '繼續遊戲', '環境設定', 'CG鑑賞', '結束遊戲']   # 原：はじめから／つづきから／環境設定／CGギャラリー／ゲーム終了
NORMAL = [11, 12, 13, 14, 15]
HOVER = [6, 7, 8, 9, 10]
STOPS = [(0.0, (3, 7, 8)), (0.35, (24, 13, 20)), (0.7, (110, 24, 50)), (1.0, (165, 24, 62))]

def grad(h):
    ys = np.linspace(0, 1, h); out = np.zeros((h, 3))
    for c in range(3):
        out[:, c] = np.interp(ys, [s for s, _ in STOPS], [col[c] for _, col in STOPS])
    return out.astype(np.uint8)

def text_layer(txt, font):
    bb = font.getbbox(txt); w, h = bb[2] - bb[0], bb[3] - bb[1]
    mask = Image.new('L', (w + 4, h + 4), 0)
    ImageDraw.Draw(mask).text((2 - bb[0], 2 - bb[1]), txt, font=font, fill=255)
    g = grad(mask.height)
    rgb = np.repeat(g[:, None, :], mask.width, axis=1)
    im = Image.fromarray(np.dstack([rgb, np.array(mask)]), 'RGBA')
    return im

def glow(im, radius=7, gain=2.2):
    pad = radius * 3
    base = Image.new('RGBA', (im.width + pad * 2, im.height + pad * 2), (255, 255, 255, 0))
    a = Image.new('L', base.size, 0); a.paste(im.split()[3], (pad, pad))
    a = a.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(radius)).point(lambda v: min(255, int(v * gain)))
    base.putalpha(a); base.alpha_composite(im, (pad, pad))
    return base

def main():
    src, fonts, out = sys.argv[1:4]; os.makedirs(out, exist_ok=True)
    font = ImageFont.truetype(os.path.join(fonts, 'NotoSerifTC-VF.ttf'), 24)
    try: font.set_variation_by_axes([900])
    except Exception: pass
    for k, txt in enumerate(ITEMS):
        for idx, hover in ((NORMAL[k], False), (HOVER[k], True)):
            meta = json.load(open(os.path.join(src, f'sys_title#{idx:03d}.meta.json')))
            im = text_layer(txt, font)
            if hover: im = glow(im)
            cx = meta['x'] + meta['w'] / 2; cy = meta['y'] + meta['h'] / 2
            nx, ny = int(round(cx - im.width / 2)), int(round(cy - im.height / 2))
            name = f'sys_title#{idx:03d}'
            im.save(os.path.join(out, name + '.png'))
            json.dump({'x': nx, 'y': ny}, open(os.path.join(out, name + '.json'), 'w'))
    # 副標「グリザイアの旋律」(frame 16) → 「灰色的旋律」：銀色漸層＋柔和陰影
    meta = json.load(open(os.path.join(src, 'sys_title#016.meta.json')))
    f2 = ImageFont.truetype(os.path.join(fonts, 'NotoSerifTC-VF.ttf'), 46)
    try: f2.set_variation_by_axes([700])
    except Exception: pass
    txt = '灰色的旋律'; bb = f2.getbbox(txt); w, h = bb[2] - bb[0], bb[3] - bb[1]
    pad = 12
    mask = Image.new('L', (w + pad * 2, h + pad * 2), 0); ImageDraw.Draw(mask).text((pad - bb[0], pad - bb[1]), txt, font=f2, fill=255)
    ys = np.linspace(0, 1, mask.height)
    silver = np.stack([np.interp(ys, [0, .45, .55, 1], [250, 238, 196, 168]) for _ in range(3)], axis=1).astype(np.uint8)
    rgb = np.repeat(silver[:, None, :], mask.width, axis=1)
    face = Image.fromarray(np.dstack([rgb, np.array(mask)]), 'RGBA')
    sh = Image.new('RGBA', face.size, (60, 60, 70, 0)); sa = mask.filter(ImageFilter.GaussianBlur(4)).point(lambda v: int(v * 0.75)); sh.putalpha(sa)
    im = Image.new('RGBA', face.size, (0, 0, 0, 0)); im.alpha_composite(sh, (2, 3)); im.alpha_composite(face)
    cx = meta['x'] + meta['w'] / 2; cy = meta['y'] + meta['h'] / 2
    im.save(os.path.join(out, 'sys_title#016.png'))
    json.dump({'x': int(round(cx - im.width / 2)), 'y': int(round(cy - im.height / 2))}, open(os.path.join(out, 'sys_title#016.json'), 'w'))
    print('ok')

if __name__ == '__main__':
    main()
