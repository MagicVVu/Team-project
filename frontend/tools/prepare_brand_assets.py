"""Package approved raster artwork into Android resources; no artwork is redrawn.

Run with Python and Pillow. Sources live in docs/ui/branding/Mewstow.
"""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "docs/ui/branding/Mewstow"
RES = ROOT / "frontend/app/src/main/res"


def artwork(name):
    image = Image.open(BRAND / name).convert("RGBA")
    # The image export has nearly invisible pixels outside the actual artwork.
    alpha = image.getchannel("A").point(lambda value: value if value >= 16 else 0)
    image.putalpha(alpha)
    return image.crop(alpha.getbbox())


def fit(image, size, fraction):
    output = Image.new("RGBA", (size, size))
    scaled = image.copy()
    scaled.thumbnail((round(size * fraction), round(size * fraction)), Image.Resampling.LANCZOS)
    output.alpha_composite(scaled, ((size - scaled.width) // 2, (size - scaled.height) // 2))
    return output


def save(image, folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    image.save(folder / name)


def main():
    logo = artwork("wordmark-source.png")
    logo.thumbnail((1600, 400), Image.Resampling.LANCZOS)
    # Equal small transparent padding preserves all ear and tail tips.
    wordmark = Image.new("RGBA", (logo.width + 24, logo.height + 24))
    wordmark.alpha_composite(logo, (12, 12))
    save(wordmark, RES / "drawable-nodpi", "mewstow_wordmark.png")
    save(wordmark, BRAND, "mewstow-wordmark-v1.png")

    symbol = artwork("launcher-source.png")
    mark = fit(symbol, 512, .94)
    save(mark, RES / "drawable-nodpi", "mewstow_mark.png")
    # 60/108 dp fits inside Android's central 66 dp adaptive-icon safe area.
    foreground = fit(symbol, 432, 60 / 108)
    save(foreground, RES / "drawable-nodpi", "mewstow_launcher_foreground.png")
    save(foreground, BRAND, "mewstow-launcher-foreground.png")
    mono = Image.new("RGBA", foreground.size, "white")
    mono.putalpha(foreground.getchannel("A"))
    save(mono, RES / "drawable-nodpi", "mewstow_launcher_monochrome.png")

    for density, size in [("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)]:
        icon = Image.new("RGBA", (size, size), "#A4BF5A")
        icon.alpha_composite(fit(symbol, size, .78))
        save(icon, RES / f"mipmap-{density}", "ic_launcher.webp")
        mask = Image.new("L", (size, size))
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
        icon.putalpha(mask)
        save(icon, RES / f"mipmap-{density}", "ic_launcher_round.webp")

    print("Packaged V1 wordmark, symbol, adaptive layers, and ten legacy launcher resources.")


if __name__ == "__main__":
    main()
