"""Generate the app icon: wireframe cube only."""
from PIL import Image, ImageDraw
import math
import os

OUTPUT_DIR = r"E:\jingming-yanhuan\jingming-yanhuan\apps\desktop\src-tauri\icons"

# Rose-gold / warm brown palette
LINE_COLOR = (180, 120, 100, 220)       # front edges
LINE_COLOR_LIGHT = (200, 150, 130, 160) # back edges

def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size / 2, size / 2
    half = size * 0.32

    angle_x = math.radians(25)
    angle_y = math.radians(30)

    verts_3d = []
    for x in [-1, 1]:
        for y in [-1, 1]:
            for z in [-1, 1]:
                verts_3d.append((x * half, y * half, z * half))

    def project(x, y, z):
        px = cx + x * math.cos(angle_y) - z * math.sin(angle_y)
        py = cy + y * math.cos(angle_x) - (x * math.sin(angle_y) + z * math.cos(angle_y)) * math.sin(angle_x) * 0.5
        return px, py

    verts_2d = [project(*v) for v in verts_3d]

    edges = [
        (0,1),(0,2),(0,4),
        (1,3),(1,5),
        (2,3),(2,6),
        (3,7),(4,5),(4,6),(5,7),(6,7)
    ]

    back_edges = [(0,1),(0,2),(0,4),(2,3),(2,6),(4,6)]
    for a, b in back_edges:
        draw.line([verts_2d[a], verts_2d[b]], fill=LINE_COLOR_LIGHT, width=max(1, size // 120))

    front_edges = [(1,3),(1,5),(3,7),(4,5),(5,7),(6,7)]
    for a, b in front_edges:
        draw.line([verts_2d[a], verts_2d[b]], fill=LINE_COLOR, width=max(1, size // 100))

    return img


def main():
    sizes = [
        (32, "32x32.png"),
        (64, "64x64.png"),
        (128, "128x128.png"),
        (256, "128x128@2x.png"),
        (512, "icon.png"),
    ]
    for size, name in sizes:
        icon = draw_icon(size)
        path = os.path.join(OUTPUT_DIR, name)
        icon.save(path, "PNG")
        print(f"Saved {path} ({size}x{size})")

    square_sizes = [
        (30, "Square30x30Logo.png"),
        (44, "Square44x44Logo.png"),
        (71, "Square71x71Logo.png"),
        (89, "Square89x89Logo.png"),
        (107, "Square107x107Logo.png"),
        (142, "Square142x142Logo.png"),
        (150, "Square150x150Logo.png"),
        (284, "Square284x284Logo.png"),
        (310, "Square310x310Logo.png"),
    ]
    for size, name in square_sizes:
        icon = draw_icon(size)
        path = os.path.join(OUTPUT_DIR, name)
        icon.save(path, "PNG")
        print(f"Saved {path} ({size}x{size})")

    # Generate .ico
    icon_512 = draw_icon(512)
    ico_path = os.path.join(OUTPUT_DIR, "icon.ico")
    icon_512.save(ico_path, format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    print(f"Saved {ico_path}")

if __name__ == "__main__":
    main()
