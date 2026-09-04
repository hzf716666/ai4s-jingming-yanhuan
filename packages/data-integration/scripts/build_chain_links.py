# -*- coding: utf-8 -*-
"""数据地图·产业链连线（链图层）构建
从知识图谱 fkg_graph_view.json 的 Cluster 节点 + co_mentioned/co_located 边，
把"同产业链集群"解析到所属高新区(zone)经纬度，写进 integration.db 的 chain_links 表，
供 /api/map/chains 读取，绘制球面上的"各区间产业连线"。

解析口径：集群名前 2-5 个汉字取作城市 token，与 zone_facts 的 city(去"市")前缀匹配，
匹配到 zone 则取该 zone 的 lon/lat。解析不到的集群边丢弃（不伪造数据）。
"""
import json
import pathlib
import re
import sqlite3

SCRIPT = pathlib.Path(__file__).resolve()
PKG = SCRIPT.parents[1]                       # packages/data-integration
ROOT = SCRIPT.parents[3]                      # jingming-yanhuan
DB = PKG / "server_data" / "integration.db"
FKG = ROOT / "apps" / "desktop" / "public" / "data" / "fkg_graph_view.json"


def zone_geo(conn) -> dict[str, tuple[str, float, float]]:
    """zone -> (city, lon, lat)"""
    out = {}
    for r in conn.execute("SELECT DISTINCT zone, city, lon, lat FROM zone_facts"):
        if r[0] and r[2] is not None:
            out[r[0]] = (r[1] or "", r[2], r[3])
    return out


def resolve(cluster_id: str, zc: dict) -> tuple[str, float, float] | None:
    nm = (cluster_id or "").replace("clu_", "")
    for suf in ("创新型产业集群", "产业集群"):
        nm = nm.replace(suf, "")
    nm = nm.replace("国家级", "")
    m = re.match(r"^([\u4e00-\u9fa5]{2,5})", nm)
    if not m:
        return None
    tok = m.group(1)
    for zone, (city, lon, lat) in zc.items():
        ccity = city.replace("市", "").replace("自治州", "")
        if ccity and (tok.startswith(ccity) or ccity.startswith(tok) or tok in ccity):
            return (zone, lon, lat)
    return None


def main() -> int:
    fkg = json.loads(FKG.read_text(encoding="utf-8"))
    # 只取"集群↔集群"的共现/同位边（KG 里 co_* 也连过集群↔区域，如"北京市"，
    # 那不是产业链节点；集群节点 id 以 clu_ 开头）
    edges = [
        l for l in fkg.get("links", [])
        if l.get("edge_type") in ("co_mentioned", "co_located")
        and str(l.get("source", "")).startswith("clu_")
        and str(l.get("target", "")).startswith("clu_")
    ]

    conn = sqlite3.connect(str(DB))
    # 派生表，每次重建；端点存集群名(集群才是产业链节点，高新区只是坐标落点)
    conn.execute("DROP TABLE IF EXISTS chain_links")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS chain_links ("
        "cluster_from TEXT, zone_from TEXT, lon_from REAL, lat_from REAL, "
        "cluster_to TEXT, zone_to TEXT, lon_to REAL, lat_to REAL, "
        "chain TEXT, weight INTEGER, UNIQUE(zone_from, zone_to, chain))"
    )
    zc = zone_geo(conn)
    rows = []
    seen = set()
    for e in edges:
        src = (e.get("source", "") or "").replace("clu_", "").replace("国家级", "")
        dst = (e.get("target", "") or "").replace("clu_", "").replace("国家级", "")
        a = resolve(e.get("source", ""), zc)
        b = resolve(e.get("target", ""), zc)
        if not a or not b or a[0] == b[0]:
            continue
        # 保留 KG 方向：从集群A(源) → 集群B(目标)；去重按集群对
        sig = (src, dst)
        if sig in seen:
            continue
        seen.add(sig)
        rows.append((src, a[0], a[1], a[2], dst, b[0], b[1], b[2], src, 1))
    conn.executemany(
        "INSERT OR IGNORE INTO chain_links (cluster_from, zone_from, lon_from, lat_from, "
        "cluster_to, zone_to, lon_to, lat_to, chain, weight) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM chain_links").fetchone()[0]
    conn.close()
    print(f"chain_links: 写入 {len(rows)} 条(重建), 表内 {n} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
