from pathlib import Path
from PIL import Image

src = Path("apollo_logo.png")
dst = Path("apollo_logo.ico")

img = Image.open(src).convert("RGBA")
w, h = img.size
size = max(w, h)
canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
canvas.paste(img, ((size - w) // 2, (size - h) // 2), img)
canvas.save(dst, format="ICO", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])

print(f"Created {dst.resolve()}")
