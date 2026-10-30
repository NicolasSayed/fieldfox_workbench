"""Render the project's own simple vector mark into PNG and Windows ICO."""
from pathlib import Path
from PIL import Image, ImageDraw


def main():
    directory = Path(__file__).resolve().parents[1] / "assets"
    image = Image.new("RGBA", (256, 256)); draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 255, 255), radius=56, fill="#245fd3")
    points = [(10, 38), (19, 38), (25, 20), (34, 49), (41, 27), (48, 38), (54, 38)]
    points = [(x*4, y*4) for x,y in points]
    draw.line(points, fill="white", width=16, joint="curve")
    for x,y in points: draw.ellipse((x-8,y-8,x+8,y+8), fill="white")
    package_assets = directory.parent / "fieldfox_workbench" / "assets"; package_assets.mkdir(exist_ok=True)
    image.resize((64,64), Image.Resampling.LANCZOS).save(package_assets / "workbench.png")
    image.save(directory / "workbench.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])


if __name__ == "__main__": main()
