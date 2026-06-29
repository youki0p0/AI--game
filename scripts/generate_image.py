#!/usr/bin/env python3
"""GPT Image Gen 2 (gpt-image-2) を使った画像生成スクリプト。

使い方:
    python scripts/generate_image.py "プロンプト文字列" \
        --size 1024x1536 --quality high --outdir ./out --prefix kagura_fullbody

環境変数:
    OPENAI_API_KEY  OpenAI API キー（必須）

出力:
    <outdir>/<prefix>_<timestamp>.png を保存し、保存先パスを標準出力に表示する。
"""
from __future__ import annotations

import argparse
import base64
import datetime as _dt
import os
import sys
import time

import requests

API_URL = "https://api.openai.com/v1/images/generations"
DEFAULT_MODEL = "gpt-image-2"
MAX_RETRIES = 4


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GPT Image Gen 2 で画像を生成する")
    p.add_argument("prompt", help="画像生成プロンプト")
    p.add_argument("--model", default=DEFAULT_MODEL, help="使用モデル (既定: gpt-image-2)")
    p.add_argument("--size", default="1024x1536",
                   help="画像サイズ 例: 1024x1536 / 1536x1024 / 1024x1024 / auto")
    p.add_argument("--quality", default="high",
                   choices=["low", "medium", "high", "auto"], help="生成品質")
    p.add_argument("--outdir", default="./out", help="出力ディレクトリ")
    p.add_argument("--prefix", default="image", help="出力ファイル名の接頭辞")
    p.add_argument("-n", "--num", type=int, default=1, help="生成枚数")
    return p.parse_args(argv)


def generate(args: argparse.Namespace, api_key: str) -> list[bytes]:
    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "size": args.size,
        "quality": args.quality,
        "n": args.num,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body = None
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(API_URL, json=payload, headers=headers, timeout=600)
        except requests.RequestException as e:  # ネットワーク／読み取り中断など
            last_err = e
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt
                print(f"通信エラー（{attempt}回目）: {e} -> {wait}秒後に再試行", file=sys.stderr)
                time.sleep(wait)
                continue
            raise SystemExit(f"通信に失敗しました: {e}") from e

        if resp.status_code != 200:
            raise SystemExit(f"APIエラー ({resp.status_code}): {resp.text[:1000]}")
        body = resp.json()
        break

    if body is None:
        raise SystemExit(f"応答を取得できませんでした: {last_err}")

    images: list[bytes] = []
    for item in body.get("data", []):
        b64 = item.get("b64_json")
        if b64:
            images.append(base64.b64decode(b64))
    if not images:
        raise SystemExit(f"画像データが返りませんでした: {str(body)[:500]}")
    return images


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("環境変数 OPENAI_API_KEY が設定されていません")

    os.makedirs(args.outdir, exist_ok=True)
    images = generate(args, api_key)

    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    for i, data in enumerate(images):
        suffix = f"_{i}" if len(images) > 1 else ""
        path = os.path.join(args.outdir, f"{args.prefix}_{stamp}{suffix}.png")
        with open(path, "wb") as f:
            f.write(data)
        print(f"保存しました: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
