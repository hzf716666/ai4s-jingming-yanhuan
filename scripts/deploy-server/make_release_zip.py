"""Package the portable release dir (apps/desktop/src-tauri/target/release) into
one deployable zip for the cloud server.  Keeps exes, DLLs and the resource dirs
that tauri.jingming.json copies next to the binary; drops build/deps artifacts."""
import os
import zipfile

RELEASE = r"E:\tb\jingming-yanhuan\apps\desktop\src-tauri\target\release"
OUT = r"E:\tb\jingming-yanhuan-server.zip"

INCLUDE_TOPS = [
    "jingming-yanhuan.exe",
    "opencode.exe",
    "uv.exe",
    "agent-browser.exe",
    "examples",
    "goal-plugin",
    "harness",
    "qoder-sidecar",
    "skills",
    "skills-00",
    "skills-08",
    "skills-office",
]

count = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
    for top in INCLUDE_TOPS:
        p = os.path.join(RELEASE, top)
        if os.path.isfile(p):
            zf.write(p, top)
            count += 1
        elif os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                for f in files:
                    full = os.path.join(root, f)
                    arc = os.path.relpath(full, RELEASE)
                    zf.write(full, arc)
                    count += 1
        else:
            print("MISSING:", top)
    for f in os.listdir(RELEASE):
        if f.lower().endswith(".dll"):
            zf.write(os.path.join(RELEASE, f), f)
            count += 1

print("files:", count)
print("size MB:", round(os.path.getsize(OUT) / 1024 / 1024, 1))
