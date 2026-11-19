#!/usr/bin/env python3
"""說明字列（壓在紋理底圖上的黑色小字）重畫。

做法：
  1. 在指定區域內以「亮度比局部背景暗」找出文字遮罩。
  2. 同一底圖的多張畫面互相補洞：某像素在其他畫面沒有文字時，直接借用該畫面的像素。
  3. 仍無法補的像素用 OpenCV inpaint 修補。
  4. 以原字的墨跡高度與顏色畫上中文。

用法：python3 ui_help.py spec.json <src_dir> <font_dir> <out_dir>
spec = {"region":[x0,y0,x1,y1], "font":"msjh.ttc", "groups":[[{"name":"sys_cg#057","zh":"..."}, ...], ...]}
"""
import json, os, sys
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont


LIGHT_TOO = None


def text_mask(rgb, region, thr, dil=1, absl=None, light=False):
    x0, y0, x1, y1 = region
    lum = rgb[..., :3].astype(np.float32).mean(-1)
    sub = lum[y0:y1, x0:x1]
    k = np.ones((9, 9), np.uint8)
    bg = cv2.morphologyEx(np.clip(sub, 0, 255).astype(np.uint8), cv2.MORPH_OPEN if light else cv2.MORPH_CLOSE, k).astype(np.float32)
    m = ((sub - bg) if light else (bg - sub)) > thr
    if absl is not None: m = sub < absl
    if LIGHT_TOO is not None: m = m | (sub > LIGHT_TOO)
    m = cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=dil).astype(bool)
    full = np.zeros(lum.shape, bool); full[y0:y1, x0:x1] = m
    return full


def ink_stats(rgb, mask, region, light=False):
    x0, y0, x1, y1 = region
    lum = rgb[..., :3].astype(np.float32).mean(-1)
    if light:
        core = mask & (lum > np.percentile(lum[mask], 70)) if mask.any() else mask
        strong = mask & (lum > 160)
    else:
        core = mask & (lum < np.percentile(lum[mask], 30)) if mask.any() else mask
        strong = mask & (lum < 110)
    ys, xs = np.where(strong if strong.any() else mask)
    color = tuple(int(c) for c in np.median(rgb[core][:, :3], axis=0)) if core.any() else (40, 40, 40)
    return (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1), color


def main():
    spec_p, src, fonts, out = sys.argv[1:5]
    spec = json.load(open(spec_p, encoding='utf-8'))
    thr = spec.get('thr', 14)
    cache = {}
    font_p = os.path.join(fonts, spec.get('font', 'msjh.ttc'))
    os.makedirs(out, exist_ok=True)
    for group in spec['groups']:
        region = group[0].get('region', spec.get('region'))
        imgs = [cache[it['name']].copy() if it['name'] in cache else
                np.array(Image.open(os.path.join(src, it['name'] + '.png')).convert('RGBA')) for it in group]
        gopt = group[0].get('opt', {})
        global LIGHT_TOO
        LIGHT_TOO = gopt.get('light_too')
        masks = [text_mask(a, region, gopt.get('thr', thr), gopt.get('dilate', 1), gopt.get('abs'), gopt.get('light', False)) for a in imgs]
        for k, it in enumerate(group):
            a = imgs[k].copy(); m = masks[k].copy()
            # 借用其他畫面同位置（且那邊沒有字）的像素
            for j, b in enumerate(imgs):
                if j == k: continue
                use = m & ~masks[j]
                # 只在兩張底圖於遮罩外近似一致時借用
                x0, y0, x1, y1 = region
                ring = ~(masks[k] | masks[j]); ring[:y0] = ring[y1:] = False; ring[:, :x0] = ring[:, x1:] = False
                if ring.any() and np.abs(a[ring][:, :3].astype(int) - b[ring][:, :3].astype(int)).mean() > 6:
                    continue
                a[use] = b[use]; m &= ~use
            if m.any() and gopt.get('white_bg'):
                # 底層是「白色＋alpha 花紋」：RGB 直接補白，只修補 alpha
                rx0, ry0, rx1, ry1 = region
                mm = m[ry0:ry1, rx0:rx1]
                sub = a[ry0:ry1, rx0:rx1]
                sub[mm, :3] = 255
                al = np.ascontiguousarray(sub[..., 3])
                sub[..., 3] = cv2.inpaint(al, mm.astype(np.uint8) * 255, gopt.get('radius', 3), cv2.INPAINT_TELEA)
                a[ry0:ry1, rx0:rx1] = sub
                m[:] = False
            if m.any():
                # 只在區域內修補，避免把區域外的分隔線等深色像素抹進來
                rx0, ry0, rx1, ry1 = region
                bgr = cv2.cvtColor(np.ascontiguousarray(a[ry0:ry1, rx0:rx1, :3]), cv2.COLOR_RGB2BGR)
                meth = cv2.INPAINT_NS if gopt.get('ns') else cv2.INPAINT_TELEA
                fixed = cv2.inpaint(bgr, m[ry0:ry1, rx0:rx1].astype(np.uint8) * 255, gopt.get('radius', 3), meth)
                a[ry0:ry1, rx0:rx1, :3] = cv2.cvtColor(fixed, cv2.COLOR_BGR2RGB)
                al = np.ascontiguousarray(a[ry0:ry1, rx0:rx1, 3])
                if al.min() < 255:
                    a[ry0:ry1, rx0:rx1, 3] = cv2.inpaint(al, m[ry0:ry1, rx0:rx1].astype(np.uint8) * 255, gopt.get('radius', 3), meth)
            (ix0, iy0, ix1, iy1), color = ink_stats(imgs[k], masks[k], region, gopt.get('light', False))
            # 字高：原字（含遮罩膨脹 1px）高度 -2
            target_h = (iy1 - iy0) + spec.get('h_adj', 0)
            size = target_h; img = Image.fromarray(a)
            probe = spec.get('probe', '鑑賞點選')
            for s in ([] if it.get('size', spec.get('size')) else range(target_h + 8, 6, -1)):
                f = ImageFont.truetype(font_p, s)
                bb = f.getbbox(probe)
                if bb[3] - bb[1] <= target_h: size = s; break
            if it.get('size', spec.get('size')): size = it.get('size', spec.get('size'))
            maxw = it.get('maxw', region[2] - ix0)
            fp = os.path.join(fonts, it['font']) if it.get('font') else font_p
            while True:
                f = ImageFont.truetype(fp, size)
                bb = f.getbbox(it['zh'])
                if bb[2] - bb[0] <= maxw or size <= 9: break
                size -= 1
            pb = f.getbbox(probe)
            d = ImageDraw.Draw(img)
            x = ix0 - bb[0]
            if it.get('align') == 'center': x = (ix0 + ix1) // 2 - (bb[0] + bb[2]) // 2
            if 'color' in it: color = tuple(it['color'])
            y = iy0 - pb[1] + ((target_h - (pb[3] - pb[1])) // 2) + it.get('dy', spec.get('dy', 0))
            if it.get('glow'):
                gr, gs = it['glow']
                lay = Image.new('L', img.size, 0)
                ImageDraw.Draw(lay).text((x, y), it['zh'], font=f, fill=255, stroke_width=max(1, gr // 2), stroke_fill=255)
                from PIL import ImageFilter
                lay = lay.filter(ImageFilter.GaussianBlur(gr))
                ga = np.clip(np.array(lay, np.float32) * gs, 0, 255) / 255.0
                arr = np.array(img).astype(np.float32)
                al0 = arr[..., 3:4] / 255.0; gaa = ga[..., None]
                outa = gaa + al0 * (1 - gaa)
                rgb = (255 * gaa + arr[..., :3] * al0 * (1 - gaa)) / np.maximum(outa, 1e-6)
                arr[..., :3] = rgb; arr[..., 3:4] = outa * 255
                img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
                d = ImageDraw.Draw(img)
            d.text((x, y), it['zh'], font=f, fill=color + (255,))
            cache[it['name']] = np.array(img)
            print(it['name'], 'ink', (ix0, iy0, ix1, iy1), 'size', size, 'color', color, 'left-unfilled', int(m.sum()))

    for name, arr in cache.items():
        Image.fromarray(arr).save(os.path.join(out, name + '.png'))


if __name__ == '__main__':
    main()
