"""Generate sample test data for end-to-end pipeline testing."""
import csv
import json
from pathlib import Path

from openpyxl import Workbook

OUTPUT_DIR = Path(__file__).parent / "data_samples"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def create_gdp_xlsx():
    """Create a sample xlsx with provincial GDP data (time series)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "GDP"

    header = ["年份", "GDP(亿元)", "第一产业增加值(亿元)", "第二产业增加值(亿元)", "第三产业增加值(亿元)"]
    ws.append(header)

    data = [
        ("2018", 900309.5, 64745.0, 333617.0, 501947.5),
        ("2019", 986515.2, 70173.8, 380971.0, 535370.4),
        ("2020", 1015986.2, 77749.0, 384249.6, 553987.6),
        ("2021", 1149237.0, 83068.6, 450904.3, 615264.1),
        ("2022", 1210207.2, 88345.2, 482502.1, 639360.0),
        ("2023", 1260582.1, 89710.8, 483592.8, 687278.5),
    ]
    for row in data:
        ws.append(row)

    ws2 = wb.create_sheet("Regional GDP")
    ws2.append(["地区", "GDP(亿元)", "人口(万人)"])
    regional_data = [
        ("北京市", 41610.9, 2189.3),
        ("上海市", 43248.5, 2487.1),
        ("广东省", 135673.0, 12684.0),
        ("江苏省", 122875.6, 8526.0),
        ("山东省", 87435.0, 10162.8),
        ("浙江省", 77715.0, 6577.4),
        ("河南省", 58787.0, 9937.0),
        ("四川省", 53850.8, 8367.5),
    ]
    for row in regional_data:
        ws2.append(row)

    filepath = OUTPUT_DIR / "gdp_2018_2023.xlsx"
    wb.save(filepath)
    print(f"Created: {filepath}")


def create_population_csv():
    """Create a sample CSV with population data."""
    filepath = OUTPUT_DIR / "population_2018_2023.csv"
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["year", "region", "population"])
        data = [
            ("2018", "北京", 2154.2),
            ("2018", "上海", 2426.5),
            ("2018", "广东", 11346.0),
            ("2018", "全国", 139538.0),
            ("2019", "北京", 2170.5),
            ("2019", "上海", 2428.1),
            ("2019", "广东", 11526.0),
            ("2019", "全国", 140005.0),
            ("2020", "北京", 2189.3),
            ("2020", "上海", 2487.1),
            ("2020", "广东", 12684.0),
            ("2020", "全国", 141212.0),
            ("2021", "北京", 2188.6),
            ("2021", "上海", 2487.5),
            ("2021", "广东", 12684.0),
            ("2021", "全国", 141260.0),
            ("2022", "北京", 2184.3),
            ("2022", "上海", 2475.0),
            ("2022", "广东", 12657.0),
            ("2022", "全国", 141175.0),
            ("2023", "北京", 2185.8),
            ("2023", "上海", 2487.5),
            ("2023", "广东", 12706.0),
            ("2023", "全国", 140967.0),
        ]
        for row in data:
            writer.writerow(row)
    print(f"Created: {filepath}")


def create_investment_csv():
    """Create a sample CSV with fixed asset investment data."""
    filepath = OUTPUT_DIR / "investment_2020_2023.csv"
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["year", "region", "fixed_asset_investment"])
        data = [
            ("2020", "北京市", 3253.5),
            ("2020", "上海市", 4234.2),
            ("2020", "广东省", 4234.5),
            ("2020", "全国", 527167.0),
            ("2021", "北京市", 3494.0),
            ("2021", "上海市", 4557.0),
            ("2021", "广东省", 4567.8),
            ("2021", "全国", 552884.0),
            ("2022", "北京市", 3550.0),
            ("2022", "上海市", 4650.0),
            ("2022", "广东省", 4789.0),
            ("2022", "全国", 577543.0),
            ("2023", "北京市", 3630.0),
            ("2023", "上海市", 4730.0),
            ("2023", "广东省", 4900.0),
            ("2023", "全国", 595000.0),
        ]
        for row in data:
            writer.writerow(row)
    print(f"Created: {filepath}")


def create_requirement_config():
    """Create a sample requirement config JSON."""
    config = {
        "research_question": "收集2018-2023年中国GDP、人口、固定资产投资数据",
        "indicators": ["GDP", "人口", "固定资产投资"],
        "time_range": ["2018", "2023"],
        "regions": ["全国", "北京", "上海", "广东"],
        "data_types": ["xlsx", "csv"],
        "llm_enabled": False,
    }
    filepath = OUTPUT_DIR / "requirement.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"Created: {filepath}")


if __name__ == "__main__":
    create_gdp_xlsx()
    create_population_csv()
    create_investment_csv()
    create_requirement_config()
    print("\nAll sample data created in:", OUTPUT_DIR)
