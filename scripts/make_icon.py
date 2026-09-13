"""Rasterize the simple application mark for native Windows icon sizes."""
from pathlib import Path
from PIL import Image,ImageDraw

def make_icon(destination):
    image=Image.new("RGBA",(256,256),(0,0,0,0)); draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((0,0,255,255),52,fill="#141e2d")
    draw.line([(128,28),(210,60),(210,124),(195,160),(163,198),(128,229),(93,198),(61,160),(46,124),(46,60),(128,28)],fill="#e8edf5",width=11,joint="curve")
    draw.line([(67,163),(105,115),(139,129),(187,74)],fill="#32b7c9",width=15,joint="curve")
    draw.line([(161,74),(188,72),(186,99)],fill="#32b7c9",width=12)
    Path(destination).parent.mkdir(parents=True,exist_ok=True)
    image.save(destination,sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])

if __name__ == "__main__":
    make_icon("build_assets/jailwatch.ico")
