# -*- coding: utf-8 -*-
"""Build lightweight outline layers for the 3D data map.

Sources:
  world:      echarts world map (English names -> Chinese via mapping)
  china:      geo.datav.aliyun.com 100000_full.json (provinces)
  hubei:      火炬数据地图/web/data/hubei.geojson (cities)
  districts:  火炬数据地图/web/data/hubei_districts.geojson (all Hubei districts)

Output: server_data/geo/{world,china,hubei,districts}.json
  [{name, lon, lat, rings: [[[lon,lat],...],...]}]  (rings closed, sampled)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEO = ROOT / "server_data" / "geo"
TORCH = ROOT.parent.parent.parent / "火炬数据地图" / "web" / "data"

# world.json country name -> Chinese (fallback keeps English)
ZH = {
    "China": "中国", "Afghanistan": "阿富汗", "Albania": "阿尔巴尼亚", "Algeria": "阿尔及利亚",
    "Angola": "安哥拉", "Argentina": "阿根廷", "Armenia": "亚美尼亚", "Australia": "澳大利亚",
    "Austria": "奥地利", "Azerbaijan": "阿塞拜疆", "Bangladesh": "孟加拉国", "Belarus": "白俄罗斯",
    "Belgium": "比利时", "Benin": "贝宁", "Bhutan": "不丹", "Bolivia": "玻利维亚",
    "Bosnia and Herz.": "波黑", "Botswana": "博茨瓦纳", "Brazil": "巴西", "Bulgaria": "保加利亚",
    "Burkina Faso": "布基纳法索", "Burundi": "布隆迪", "Cambodia": "柬埔寨", "Cameroon": "喀麦隆",
    "Canada": "加拿大", "C. African Rep.": "中非", "Chad": "乍得", "Chile": "智利",
    "Colombia": "哥伦比亚", "Congo": "刚果（布）", "Costa Rica": "哥斯达黎加",
    "Côte d'Ivoire": "科特迪瓦", "Croatia": "克罗地亚", "Cuba": "古巴", "Cyprus": "塞浦路斯",
    "Czech Rep.": "捷克", "Dem. Rep. Congo": "刚果（金）", "Denmark": "丹麦", "Djibouti": "吉布提",
    "Dominican Rep.": "多米尼加", "Ecuador": "厄瓜多尔", "Egypt": "埃及", "El Salvador": "萨尔瓦多",
    "Eq. Guinea": "赤道几内亚", "Eritrea": "厄立特里亚", "Estonia": "爱沙尼亚", "Ethiopia": "埃塞俄比亚",
    "Finland": "芬兰", "Fr. S. Antarctic Lands": "法属南极领地", "France": "法国", "Gabon": "加蓬",
    "Gambia": "冈比亚", "Georgia": "格鲁吉亚", "Germany": "德国", "Ghana": "加纳",
    "Greece": "希腊", "Guatemala": "危地马拉", "Guinea": "几内亚", "Guinea-Bissau": "几内亚比绍",
    "Guyana": "圭亚那", "Haiti": "海地", "Honduras": "洪都拉斯", "Hungary": "匈牙利",
    "Iceland": "冰岛", "India": "印度", "Indonesia": "印度尼西亚", "Iran": "伊朗",
    "Iraq": "伊拉克", "Ireland": "爱尔兰", "Israel": "以色列", "Italy": "意大利",
    "Jamaica": "牙买加", "Japan": "日本", "Jordan": "约旦", "Kazakhstan": "哈萨克斯坦",
    "Kenya": "肯尼亚", "Korea": "韩国", "Kuwait": "科威特", "Kyrgyzstan": "吉尔吉斯斯坦",
    "Laos": "老挝", "Latvia": "拉脱维亚", "Lebanon": "黎巴嫩", "Lesotho": "莱索托",
    "Liberia": "利比里亚", "Libya": "利比亚", "Lithuania": "立陶宛", "Luxembourg": "卢森堡",
    "Macedonia": "北马其顿", "Madagascar": "马达加斯加", "Malawi": "马拉维", "Malaysia": "马来西亚",
    "Mali": "马里", "Mauritania": "毛里塔尼亚", "Mexico": "墨西哥", "Moldova": "摩尔多瓦",
    "Mongolia": "蒙古", "Montenegro": "黑山", "Morocco": "摩洛哥", "Mozambique": "莫桑比克",
    "Myanmar": "缅甸", "Namibia": "纳米比亚", "Nepal": "尼泊尔", "Netherlands": "荷兰",
    "New Zealand": "新西兰", "Nicaragua": "尼加拉瓜", "Niger": "尼日尔", "Nigeria": "尼日利亚",
    "North Korea": "朝鲜", "Norway": "挪威", "Oman": "阿曼", "Pakistan": "巴基斯坦",
    "Palestine": "巴勒斯坦", "Panama": "巴拿马", "Papua New Guinea": "巴布亚新几内亚",
    "Paraguay": "巴拉圭", "Peru": "秘鲁", "Philippines": "菲律宾", "Poland": "波兰",
    "Portugal": "葡萄牙", "Qatar": "卡塔尔", "Romania": "罗马尼亚", "Russia": "俄罗斯",
    "Rwanda": "卢旺达", "Saudi Arabia": "沙特阿拉伯", "Senegal": "塞内加尔", "Serbia": "塞尔维亚",
    "Sierra Leone": "塞拉利昂", "Slovakia": "斯洛伐克", "Slovenia": "斯洛文尼亚",
    "Solomon Is.": "所罗门群岛", "Somalia": "索马里", "South Africa": "南非", "South Korea": "韩国",
    "South Sudan": "南苏丹", "Spain": "西班牙", "Sri Lanka": "斯里兰卡", "Sudan": "苏丹",
    "Suriname": "苏里南", "Sweden": "瑞典", "Switzerland": "瑞士", "Syria": "叙利亚",
    "Tajikistan": "塔吉克斯坦", "Tanzania": "坦桑尼亚", "Thailand": "泰国", "Timor-Leste": "东帝汶",
    "Togo": "多哥", "Trinidad and Tobago": "特立尼达和多巴哥", "Tunisia": "突尼斯",
    "Turkey": "土耳其", "Turkmenistan": "土库曼斯坦", "Uganda": "乌干达", "Ukraine": "乌克兰",
    "United Arab Emirates": "阿联酋", "United Kingdom": "英国", "United States of America": "美国",
    "Uruguay": "乌拉圭", "Uzbekistan": "乌兹别克斯坦", "Venezuela": "委内瑞拉", "Vietnam": "越南",
    "W. Sahara": "西撒哈拉", "Yemen": "也门", "Zambia": "赞比亚", "Zimbabwe": "津巴布韦",
    "Falkland Is.": "福克兰群岛", "New Caledonia": "新喀里多尼亚", "Puerto Rico": "波多黎各",
    "Dominica": "多米尼克", "Antigua and Barbuda": "安提瓜和巴布达", "Bahamas": "巴哈马",
    "Barbados": "巴巴多斯", "Belize": "伯利兹", "Brunei": "文莱", "Cape Verde": "佛得角",
    "Comoros": "科摩罗", "Eswatini": "斯威士兰", "Fiji": "斐济", "Grenada": "格林纳达",
    "Maldives": "马尔代夫", "Marshall Is.": "马绍尔群岛", "Mauritius": "毛里求斯",
    "Micronesia": "密克罗尼西亚", "N. Cyprus": "北塞浦路斯", "S. Sudan": "南苏丹",
    "Sao Tome and Principe": "圣多美和普林西比", "Seychelles": "塞舌尔", "Singapore": "新加坡",
    "St. Vin. and Gren.": "圣文森特和格林纳丁斯", "Taiwan": "台湾", "Vanuatu": "瓦努阿图",
    "Kosovo": "科索沃", "Lebanon*": "黎巴嫩", "Macedonia*": "北马其顿", "eSwatini": "斯威士兰",
    "Bosnia and Herzegovina": "波黑", "Central African Republic": "中非", "Czech Republic": "捷克",
    "Democratic Republic of the Congo": "刚果（金）", "Dominican Republic": "多米尼加",
    "Equatorial Guinea": "赤道几内亚", "Papua New Guinea*": "巴布亚新几内亚", "Côte d'Ivoire*": "科特迪瓦",
    "Somaliland": "索马里兰", "Western Sahara": "西撒哈拉", "French Southern and Antarctic Lands": "法属南部领地",
    "United States": "美国", "UK": "英国", "DR Congo": "刚果（金）", "Rep. of Congo": "刚果（布）",
    "S. Korea": "韩国", "N. Korea": "朝鲜", "UAE": "阿联酋", "USA": "美国",
}

_CN_FIX = {"South Korea": "韩国", "Korea": "朝鲜"}


def _rings(feature: dict) -> list[list[list[float]]]:
    """Flatten any polygon geometry into closed rings of [lon, lat]."""
    geom = feature.get("geometry")
    if not geom:
        return []
    gtype = geom.get("type")
    out: list[list[list[float]]] = []
    if gtype == "Polygon":
        polys = [geom["coordinates"]]
    elif gtype == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return []
    for poly in polys:
        for ring in poly:
            if len(ring) < 3:
                continue
            pts = [(float(p[0]), float(p[1])) for p in ring]
            if pts[0] != pts[-1]:
                pts.append(pts[0])
            out.append(pts)
    return out


def _simplify(rings: list[list[list[float]]], budget: int) -> list[list[list[float]]]:
    """Downsample rings so total points stay within budget."""
    total = sum(len(r) for r in rings)
    if total <= budget:
        return rings
    step = max(1, math.ceil(total / budget))
    out = []
    for r in rings:
        nr = r[::step]
        if nr[-1] != nr[0]:
            nr.append(nr[0])
        out.append(nr)
    return out


def _center(feature: dict) -> list[float] | None:
    props = feature.get("properties", {})
    for key in ("center", "centroid", "cp"):
        v = props.get(key)
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            return [float(v[0]), float(v[1])]
    # fallback: mean of ring points
    rings = _rings(feature)
    pts = [p for r in rings[:8] for p in r]
    if not pts:
        return None
    return [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]


def build(name: str, raw: dict, budget: int, translate: bool = False) -> list[dict]:
    items = []
    for f in raw["features"]:
        props = f.get("properties", {})
        cname = props.get("name", "")
        if not cname:
            continue
        if translate:
            zh = ZH.get(cname)
            if zh is None:
                zh = ZH.get(cname.strip())
            # prefer Chinese; unmapped English names get dropped from labels
            name_zh = zh if zh else None
        else:
            name_zh = cname
        rings = _simplify(_rings(f), budget)
        if not rings:
            continue
        c = _center(f)
        items.append({"name": name_zh or cname, "zh": bool(name_zh), "lon": c[0] if c else 0, "lat": c[1] if c else 0, "rings": rings})
    return items


def main() -> None:
    GEO.mkdir(parents=True, exist_ok=True)

    raw_world = json.load(open(GEO / "_world_raw.json", encoding="utf-8"))
    world = build("world", raw_world, budget=90000, translate=True)
    json.dump(world, open(GEO / "world.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("world:", len(world), "features")

    raw_china = json.load(open(GEO / "_china_raw.json", encoding="utf-8"))
    china = build("china", raw_china, budget=30000)
    json.dump(china, open(GEO / "china.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("china:", len(china), "features")

    for key, fn, budget in (("hubei", "hubei.geojson", 9000), ("districts", "hubei_districts.geojson", 22000)):
        raw = json.load(open(TORCH / fn, encoding="utf-8"))
        items = build(key, raw, budget)
        json.dump(items, open(GEO / f"{key}.json", "w", encoding="utf-8"), ensure_ascii=False)
        print(key, ":", len(items), "features")

    # cleanup raw downloads
    for f in ("_world_raw.json", "_china_raw.json"):
        (GEO / f).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
