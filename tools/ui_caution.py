#!/usr/bin/env python3
"""開機注意畫面（caution1／caution2）重畫。

原圖是街景上直接壓白字黑框（重點字為紅字），沒有乾淨底圖可用，所以：
  1. 逐行找出文字像素（白／黑框／紅），膨脹後用 inpaint 修補。
  2. 修補區再做羽化模糊（街景原本就是柔焦），讓抹痕不明顯。
  3. 用相同樣式畫上中文：白（或紅）字＋黑框＋外圈細白邊。
  4. 標題【注意】與左下作品 Logo 不動。

用法：python3 ui_caution.py spec.json <src_dir> <font_dir> <out_dir>
spec = {"font":"msjhbd.ttc","size":32,"x":300,
        "frames":[{"name":"caution1#000","bands":[194,248,...],"lines":[[y,"文字{紅字}"],...]}]}
"""
import json, os, re, sys
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter

RED = (235, 0, 0)
METHOD = 'telea'
BLUR = 3


def clean_band(a, y0, y1, x0, x1):
    sub = a[y0:y1, x0:x1, :3].astype(int)
    r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
    black = ((r < 70) & (g < 70) & (b < 70)).astype(np.uint8)
    # 文字一定有黑框：黑框附近（含內部白／紅填色）就是文字
    m = cv2.dilate(black, np.ones((3, 3), np.uint8), iterations=4)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    bgr = cv2.cvtColor(np.ascontiguousarray(a[y0:y1, x0:x1, :3]), cv2.COLOR_RGB2BGR)
    if hasattr(cv2, 'xphoto') and METHOD.startswith('fsr'):
        # 以紋理合成修補（opencv-contrib），比 Telea 少抹痕
        fixed = np.zeros_like(bgr)
        alg = cv2.xphoto.INPAINT_FSR_BEST if METHOD == 'fsr_best' else cv2.xphoto.INPAINT_FSR_FAST
        cv2.xphoto.inpaint(bgr, (1 - m) * 255, fixed, alg)
    else:
        fixed = cv2.inpaint(bgr, m * 255, 7, cv2.INPAINT_TELEA)
    fixed = cv2.cvtColor(fixed, cv2.COLOR_BGR2RGB).astype(np.float32)
    orig = a[y0:y1, x0:x1, :3].astype(np.float32)
    # 修補處羽化模糊，且上下緣漸弱，避免出現帶狀邊界
    blur = cv2.GaussianBlur(fixed, (0, 0), BLUR) if BLUR > 0 else fixed
    w = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 3)
    w = np.clip(w * 1.3, 0, 1)
    h = y1 - y0; taper = np.minimum(1, np.minimum(np.arange(h), np.arange(h)[::-1]) / 6.0)[:, None]
    w = np.maximum(w * taper, m * 1.0)[..., None]
    out = blur * w + orig * (1 - w)
    a[y0:y1, x0:x1, :3] = np.clip(out, 0, 255).astype(np.uint8)


def draw_line(d, x, y, text, font, white=(255, 255, 255)):
    parts = re.split(r'(\{[^}]*\})', text)
    cx = x
    segs = []
    for p in parts:
        if not p: continue
        red = p.startswith('{')
        t = p[1:-1] if red else p
        segs.append((cx, t, red)); cx += font.getlength(t)
    # 三層：外圈白邊 → 黑框 → 填色
    for sx, t, red in segs:
        d.text((sx, y), t, font=font, fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=(255, 255, 255, 255))
    for sx, t, red in segs:
        d.text((sx, y), t, font=font, fill=(0, 0, 0, 255), stroke_width=3, stroke_fill=(0, 0, 0, 255))
    for sx, t, red in segs:
        d.text((sx, y), t, font=font, fill=(RED if red else white) + (255,))
    return cx


def main():
    spec_p, src, fonts, out = sys.argv[1:5]
    spec = json.load(open(spec_p, encoding='utf-8'))
    global METHOD, BLUR
    METHOD = spec.get('inpaint', 'telea'); BLUR = spec.get('blur', 3)
    font = ImageFont.truetype(os.path.join(fonts, spec.get('font', 'msjhbd.ttc')), spec.get('size', 32))
    half = spec.get('band_half', 26)
    x0, x1 = spec.get('clean_x', [285, 1175])
    os.makedirs(out, exist_ok=True)
    for fr in spec['frames']:
        a = np.array(Image.open(os.path.join(src, fr['name'] + '.png')).convert('RGBA'))
        for c in fr['bands']:
            clean_band(a, c - half, c + half, x0, x1)
        pn = spec.get('panel')
        if pn:
            # 整塊文字區統一柔焦＋略暗（羽化邊緣），蓋掉逐行修補的帶狀差異並提高可讀性
            bx0, by0, bx1, by1 = fr.get('panel_box', pn['box'])
            rgb = a[..., :3].astype(np.float32)
            bl = cv2.GaussianBlur(rgb, (0, 0), pn.get('blur', 5))
            w = np.zeros(a.shape[:2], np.float32); w[by0:by1, bx0:bx1] = 1
            w = cv2.GaussianBlur(w, (0, 0), pn.get('feather', 24))[..., None]
            dk = bl * (1 - pn.get('dark', 0.25))
            a[..., :3] = np.clip(dk * w + rgb * (1 - w), 0, 255).astype(np.uint8)
        img = Image.fromarray(a)
        d = ImageDraw.Draw(img)
        asc = font.getbbox('國')
        for c, text in fr['lines']:
            y = c - (asc[1] + asc[3]) // 2
            end = draw_line(d, spec.get('x', 300), y, text, font)
            if end > x1: print('WARNING: line too wide', fr['name'], text, end)
        img.save(os.path.join(out, fr['name'] + '.png'))
        print(fr['name'], 'ok')


if __name__ == '__main__':
    main()
