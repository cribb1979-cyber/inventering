#!/usr/bin/env python3
"""Ritar SYS.VVS-ikonen: en inventarielista med en skiftnyckel — samma stil
som sysassist/syspres (mörk rundad ruta, detaljer i färg)."""
import os
from PIL import Image, ImageDraw

MORK = (35, 38, 44, 255)
MORK2 = (43, 47, 54, 255)
VIT = (250, 251, 252, 255)
GRå = (150, 165, 180, 255)
TEAL = (63, 182, 168, 255)
TEAL_MORK = (43, 143, 132, 255)
KOPPAR = (196, 124, 78, 255)


def rita(sida=512):
    im = Image.new("RGBA", (sida, sida), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    S = 512
    d.rounded_rectangle([8, 8, S - 8, S - 8], radius=92, fill=MORK)
    d.rounded_rectangle([8, 8, S - 8, 8 + 155], radius=92, fill=MORK2)

    # klämman högst upp på listan
    d.rounded_rectangle([196, 74, 316, 130], radius=22, fill=TEAL_MORK)
    d.rounded_rectangle([216, 96, 296, 118], radius=11, fill=MORK2)

    # själva listan
    d.rounded_rectangle([96, 100, 416, 470], radius=26, fill=VIT)

    # tre rader: bock + text
    y = 178
    for i in range(3):
        d.rounded_rectangle([128, y, 168, y + 40], radius=11,
                            outline=TEAL, width=9)
        if i < 2:                       # två av tre är avbockade
            d.line([136, y + 21, 148, y + 33], fill=TEAL, width=9)
            d.line([148, y + 33, 163, y + 9], fill=TEAL, width=9)
        d.rounded_rectangle([190, y + 13, 384, y + 27], radius=7, fill=GRå)
        y += 66

    # skiftnyckeln diagonalt över nedre hörnet
    d.line([150, 424, 366, 330], fill=TEAL_MORK, width=30)
    d.ellipse([330, 288, 412, 356], fill=TEAL_MORK)
    d.ellipse([348, 306, 394, 338], fill=VIT)
    d.ellipse([166, 408, 214, 448], fill=TEAL_MORK)

    # en koppling till höger, så VVS-slagen syns
    d.rounded_rectangle([404, 404, 456, 456], radius=14, fill=KOPPAR)
    d.rounded_rectangle([412, 412, 448, 448], radius=10, fill=(232, 170, 120, 255))
    return im


if __name__ == "__main__":
    stor = rita()
    for n in (32, 48, 64, 128, 256, 512):
        mapp = os.path.expanduser("~/.local/share/icons/hicolor/%dx%d/apps" % (n, n))
        os.makedirs(mapp, exist_ok=True)
        stor.resize((n, n), Image.LANCZOS).save(os.path.join(mapp, "sysvvs.png"))
        print("sysvvs.png", n)
