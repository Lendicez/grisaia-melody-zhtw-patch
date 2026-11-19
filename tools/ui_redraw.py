"""UI 圖片文字重繪：依 spec 把 HG-3 frame 內的日文換成繁中。

python ui_redraw.py SPEC.json SRC_PNG_DIR FONT_DIR OUT_DIR
SPEC：[{"file": "sys_dialog", "frame": 8, "zh": "要結束遊戲嗎？",
        "font": "msjh.ttc", "index": 0, "size": 26,            # 字型檔（FONT_DIR 內）、ttc 索引、字級(px)
        "color": "auto" | [r,g,b], "stroke": 0, "stroke_color": [r,g,b],
        "glow": 0, "glow_color": [r,g,b],                       # 外光暈半徑（白字藍光等）
        "align": "left"|"center"|"right",                       # 新寬度與原 offset 的對齊方式
        "keep_left": 0,                                         # 保留原圖左側像素（例：核取方塊）
        "region": [x0, y0, x1, y1] | null,                      # 只重繪 frame 內某區域（背景圖上的文字）；null＝整個 frame
        "fill": "transparent" | "sample",                       # region 底色：透明 或 取區域左側一欄像素延伸
        "width": null                                           # 指定新寬度；null＝依文字寬
       }]
輸出 OUT_DIR/<file>#NNN.png（＋尺寸變更時 .json 記錄新 offset），供 hg3.py enc 使用。
"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def ink_box(a):
    al = a[:, :, 3] if a.shape[2] == 4 else (a[:, :, :3].max(axis=2) > 0) * 255
    ys, xs = np.nonzero(al > 40)
    if len(xs) == 0: return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1

def auto_color(a):
    al = a[:, :, 3]; m = al > 200
    return tuple(int(v) for v in np.median(a[m][:, :3], axis=0)) if m.any() else (0, 0, 0)

def render_text(zh, font, color, stroke=0, stroke_color=(0, 0, 0), glow=0, glow_color=(255, 255, 255)):
    bbox = font.getbbox(zh, stroke_width=stroke)
    pad = glow * 2 + 2
    w, h = bbox[2] - bbox[0] + pad * 2, bbox[3] - bbox[1] + pad * 2
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((pad - bbox[0], pad - bbox[1]), zh, font=font, fill=tuple(color) + (255,), stroke_width=stroke, stroke_fill=tuple(stroke_color) + (255,))
    if glow:
        g = Image.new('RGBA', im.size, tuple(glow_color) + (0,))
        mask = im.split()[3].filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(glow))
        g.putalpha(mask.point(lambda v: min(255, int(v * 1.6))))
        g.alpha_composite(im); im = g
    return im, pad

def main():
    spec, src, fonts, out = sys.argv[1:5]
    os.makedirs(out, exist_ok=True)
    for it in json.load(open(spec, encoding='utf-8')):
        name = f"{it['file']}#{it['frame']:03d}"
        orig = Image.open(os.path.join(src, name + '.png')).convert('RGBA'); a = np.array(orig)
        meta = json.load(open(os.path.join(src, name + '.meta.json'))) if os.path.exists(os.path.join(src, name + '.meta.json')) else {}
        color = auto_color(a) if it.get('color', 'auto') == 'auto' else it['color']
        # 字高自動縮到放得進圖框（region 時以區域高為準）；不放大
        if it.get('region'): limit_h = it['region'][3] - it['region'][1]
        else:
            ib0 = ink_box(a[:, it.get('keep_left', 0):]) or (0, 0, 0, orig.height)
            limit_h = max(orig.height, (ib0[3] - ib0[1]) + 3)   # 中文字高可到原日文墨跡高；超出圖框時下方撐開圖框
        size = it.get('size', 24)
        while True:
            font = ImageFont.truetype(os.path.join(fonts, it.get('font', 'msjh.ttc')), size, index=it.get('index', 0))
            txt, pad = render_text(it['zh'], font, color, it.get('stroke', 0), it.get('stroke_color', [0, 0, 0]), it.get('glow', 0), it.get('glow_color', [255, 255, 255]))
            ink_h = txt.height - 2 * pad
            if ink_h <= limit_h - 2 or size <= 8: break
            size -= 1
        region = it.get('region')
        if region:  # 背景圖上的局部文字：清掉區域再貼上，尺寸不變
            x0, y0, x1, y1 = region
            res = orig.copy()
            if it.get('fill', 'transparent') == 'sample':
                col = a[y0:y1, max(0, x0 - 1):x0]
                patch = np.repeat(col, x1 - x0, axis=1)
                res.paste(Image.fromarray(patch, 'RGBA'), (x0, y0))
            else:
                res.paste(Image.new('RGBA', (x1 - x0, y1 - y0), (0, 0, 0, 0)), (x0, y0))
            ib = ink_box(a[y0:y1, x0:x1]) or (0, 0, x1 - x0, y1 - y0)
            cy = y0 + (ib[1] + ib[3]) // 2
            ax = {'left': x0 + ib[0] - pad, 'center': x0 + (ib[0] + ib[2]) // 2 - txt.width // 2, 'right': x0 + ib[2] - txt.width + pad}[it.get('align', 'left')]
            res.alpha_composite(txt, (max(0, ax), max(0, cy - txt.height // 2)))
            res.save(os.path.join(out, name + '.png')); continue
        h = orig.height; kl = it.get('keep_left', 0)
        ib = ink_box(a[:, kl:]) or (0, 0, orig.width - kl, h)
        tb = ink_box(np.array(txt)) or (0, 0, txt.width, txt.height)     # 新字的實際墨跡範圍
        ink_w = tb[2] - tb[0]
        grow = max(0, (tb[3] - tb[1]) + 2 - h)                          # 圖框需撐高的像素（上下平分）
        gt = grow // 2
        if grow:
            big = Image.new('RGBA', (orig.width, h + grow), (0, 0, 0, 0)); big.paste(orig, (0, gt)); orig = big
            a = np.array(orig); ib = (ib[0], ib[1] + gt, ib[2], ib[3] + gt); h += grow
        nw = it.get('width') or (kl + ib[0] + ink_w + max(2, orig.width - kl - ib[2]))
        nw = max(nw, kl + 4)
        res = Image.new('RGBA', (nw, h), (0, 0, 0, 0))
        if kl: res.paste(orig.crop((0, 0, kl, h)), (0, 0))
        cy = (ib[1] + ib[3]) / 2                                       # 原墨跡垂直中心
        y = int(round(cy - (tb[1] + tb[3]) / 2)); y = min(max(y, -tb[1] + 1), h - tb[3] - 1) if tb[3] - tb[1] <= h - 2 else -tb[1]
        x = kl + ib[0] - tb[0]
        res.alpha_composite(txt, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))
        res = res.crop((0, 0, nw, h))
        res.save(os.path.join(out, name + '.png'))
        if 'x' in meta and ((nw != orig.width and it.get('align', 'left') != 'left') or grow):
            shift = 0 if it.get('align', 'left') == 'left' else ((orig.width - nw) // 2 if it['align'] == 'center' else orig.width - nw)
            json.dump({'x': int(meta['x'] + shift), 'y': int(meta['y'] - gt)}, open(os.path.join(out, name + '.json'), 'w'))
    print('ok')

if __name__ == '__main__':
    main()
