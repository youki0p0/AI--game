#!/usr/bin/env python3
"""画像をコードで「本物のドット絵」に変換するスクリプト。

AI が描く「ドット絵風イラスト」と違い、実際に低解像度グリッドへ間引き、
限定パレットへ減色し、アンチエイリアスのないベタ塗りのピクセルにする。
透過 PNG（アルファ）にも対応し、縁のフリンジを抑える。

使い方:
    python scripts/pixelate.py 入力.png --grid 64 --colors 24 \
        --outdir ./out --prefix kagura_dot --scale 8

主なオプション:
    --grid    ドットの解像度（縦横の最大セル数）。小さいほど粗い。既定 64
    --colors  パレット色数。小さいほどレトロ。既定 24
    --scale   プレビュー(拡大版)の倍率。既定 8（= grid*scale px）
    --dither  減色時にディザを使う（既定オフ＝ベタ塗り）
    --alpha-threshold  この値未満のアルファは完全透過に。既定 128
    --trim    不透明領域の外接矩形でトリミングしてから処理する
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np
from PIL import Image


def load_rgba(path: str) -> Image.Image:
    return Image.open(path).convert("RGBA")


def trim_to_content(im: Image.Image, alpha_threshold: int) -> Image.Image:
    a = np.asarray(im)[:, :, 3]
    ys, xs = np.where(a >= alpha_threshold)
    if len(xs) == 0:
        return im
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    return im.crop((x0, y0, x1, y1))


def downscale_grid(im: Image.Image, grid: int) -> Image.Image:
    """アスペクト比を保ったまま、長辺が grid セルになるよう縮小。

    プリマルチプライド・アルファで縮小し、透過縁の色にじみを防ぐ。
    """
    w, h = im.size
    if w >= h:
        nw, nh = grid, max(1, round(grid * h / w))
    else:
        nw, nh = max(1, round(grid * w / h)), grid

    arr = np.asarray(im).astype(np.float32)
    rgb, a = arr[:, :, :3], arr[:, :, 3:4] / 255.0
    prem = rgb * a  # 透過部の色を持ち込まない
    prem_img = Image.fromarray(np.dstack([prem, arr[:, :, 3]]).astype(np.uint8), "RGBA")
    small = prem_img.resize((nw, nh), Image.BOX)

    s = np.asarray(small).astype(np.float32)
    sa = s[:, :, 3:4] / 255.0
    with np.errstate(divide="ignore", invalid="ignore"):
        unprem = np.where(sa > 0, s[:, :, :3] / sa, 0.0)  # アンプリマルチプライ
    out = np.dstack([np.clip(unprem, 0, 255), s[:, :, 3]]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def quantize(im: Image.Image, colors: int, dither: bool, alpha_threshold: int) -> Image.Image:
    """アルファを2値化し、不透明部のみ限定パレットへ減色する。"""
    arr = np.asarray(im).copy()
    alpha = np.where(arr[:, :, 3] >= alpha_threshold, 255, 0).astype(np.uint8)

    rgb = Image.fromarray(arr[:, :, :3], "RGB")
    d = Image.FLOYDSTEINBERG if dither else Image.NONE
    pal = rgb.quantize(colors=colors, method=Image.MEDIANCUT, dither=d).convert("RGB")

    out = np.dstack([np.asarray(pal), alpha]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="画像をコードで本物のドット絵に変換する")
    p.add_argument("input", help="入力画像（PNG/JPG、透過対応）")
    p.add_argument("--grid", type=int, default=64, help="ドット解像度（長辺セル数）。既定64")
    p.add_argument("--colors", type=int, default=24, help="パレット色数。既定24")
    p.add_argument("--scale", type=int, default=8, help="プレビュー拡大倍率。既定8")
    p.add_argument("--dither", action="store_true", help="ディザを使う（既定オフ）")
    p.add_argument("--alpha-threshold", type=int, default=128, help="透過しきい値。既定128")
    p.add_argument("--trim", action="store_true", help="不透明領域でトリミングしてから処理")
    p.add_argument("--outdir", default=".", help="出力先")
    p.add_argument("--prefix", default="pixel", help="ファイル名プレフィックス")
    args = p.parse_args(argv)

    im = load_rgba(args.input)
    if args.trim:
        im = trim_to_content(im, args.alpha_threshold)

    small = downscale_grid(im, args.grid)
    dot = quantize(small, args.colors, args.dither, args.alpha_threshold)

    os.makedirs(args.outdir, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    base = os.path.join(args.outdir, f"{args.prefix}-{ts}")

    native = f"{base}_g{args.grid}_c{args.colors}.png"
    dot.save(native)  # 等倍（本物の解像度）
    print(native)

    if args.scale > 1:
        big = dot.resize((dot.width * args.scale, dot.height * args.scale), Image.NEAREST)
        preview = f"{base}_x{args.scale}.png"
        big.save(preview)  # ニアレスト拡大プレビュー
        print(preview)

    print(f"完了: grid={dot.size} colors<= {args.colors} -> {native}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
