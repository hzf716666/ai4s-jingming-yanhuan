# 经管论文图与表规范（econ-plot style guide）

> 融合三来源：science-plotting 的学术图画风（style-guide/palettes 全文要点）、
> paperbanana 的四维评估与打磨闭环、经管/社会科学顶刊惯例（系数图/事件研究/安慰剂）。
> 工具入口：`econ-write/assets/econ_plots.py`（matplotlib 纯实现，函数见文末）。

## 一、视觉特征（照抄 science-plotting style-guide）

- 白底、**无网格**（读数值需要时才加）；细框线（axes.linewidth 0.7，深灰 #333）。
- **serif 轴标签**（Times New Roman / STIX / DejaVu Serif 回退）；轴标签 9pt、刻度 7.5pt、图例 7pt。
- 图例无边框、短 handle（handlelength 1.6）；默认 `loc="best"`，遮挡数据再移出轴。
- 线宽：主曲线 1.5–2.2 pt，参照系 1.0–1.3 pt；标记点 3.5–4.5。
- 单栏图 3.35×2.55 英寸（报告/幻灯片 5.2×3.8）；导出 `bbox_inches="tight"`。
- **单位用圆括号** `Quantity (unit)`，如 `集群营收增速 (分)`——禁止斜杠写法 `增速/分`。
- 论文图不加标题（说明放图注）；避免 3D/渐变/厚重填充/粗网格线。

## 二、调色板（抄 science-plotting palettes）

`econ_plots.PALETTES` 内置 5 套；默认 **okabe-ito**（色盲安全、投屏友好）：

- `okabe-ito` #E69F00 #56B4E9 #009E73 #F0E442 #0072B2 #D55E00 #CC79A7 #999999 —— 最优默认
- `science-muted` 低饱和出版风；`nature-muted` 柔和；`npg` Nature 生物医学风；`aaas` Science 风
- 处理组/对照组：黑深灰作参照（对照组 #747474 或黑虚线），处理组用暖色第一色（#E69F00）

## 三、经管图类型（econ_plots.py 函数，均对应 12 张方法卡）

| 函数 | 图 | 配套方法卡 | 要点 |
|---|---|---|---|
| `coefficient_plot` | 系数图（点±CI+零线+星号） | m04/m06/m07 | 顶刊基准回归标准图；p→* 标注；零线虚线 |
| `event_study` | 事件研究动态系数+竖CI | m05 | 参考期灰带标记，0 线虚线 |
| `parallel_trend` | 平行趋势（处理/对照组均值） | m06 | 政策时点竖点线；干预前应平行 |
| `placebo_density` | 安慰剂估计分布+实际系数 | m06/m07 | 直方图密度坐标；实际系数竖虚线 |
| `scatter_fit` | 散点+拟合线（R² 优先） | m03 | 细线、小标记；方程+R² 可入图例 |
| `density_hist` | 分布直方图+正态/对数拟合 | m01/m02 | 10–20 bins；`density=True` 时 Y 标 Density |
| `region_timeseries` | 多地区时序 | 描述统计 | 图例 2 列；单位圆括号 |
| `panel_heatmap` | 地区×年份热力图 | P3 盘点 | 数值写在格内；色带不宜花哨 |
| `from_results_json` | results.json → 系数图 DataFrame | runner.py | P4 后直接出图 |

### 常用（P4→P6 衔接）

```python
import sys; sys.path.append("…/econ-write/assets")
import econ_plots as ep
ep.coefficient_plot(ep.from_results_json("results/run_01"),
                    unit="分", out=paper_dir / "fig1_coef")
```

## 四、三线表

- 表格用 `booktabs_latex(df, caption, label, digits)` 生成 `\toprule/\midrule/\bottomrule`；
- 变量表/描述统计表以 booktabs 规范；括号内放标准误（`(…)`），星号表注 `* p<0.1 ** p<0.05 *** p<0.01`。

## 五、四维评估（抄 paperbanana）+ 打磨闭环

自评（任意图，出图后必做）：

1. **Faithfulness**：图是否如实反映数据（不隐藏掉点/尖峰；ro bustness 与主图并存）
2. **Readability**：每轴有单位；图例不遮挡；黑白/投影可辨
3. **Conciseness**：无装饰性网格/渐变/无义标注；`bbox_inches="tight"` 无白边
4. **Aesthetics**：serif、调色板与图注一致；与全文其他图统一尺寸

打磨闭环：出图 → 自评 → 修改（≤2 轮）→ 定稿；矢量 PDF 先行，PNG 只作预览/幻灯片。

## 六、数据格式约定（抄 science-plotting data-format.md）

- **宽表**：1 个 x 列 + 多个 y 列（模型/变量各一列）；示例 `examples/nasa-gistemp-global-annual.csv`；
- **长表**：每行一个观测（`x,y,group`）；示例 `examples/palmer-penguins-*-.csv`；
- **Excel**：仅当环境有 pandas+openpyxl；缺依赖让用户导 CSV；
- **bar**：每 replicate 一行（`group,value`；分组条形加 `hue` 列）；误差 SEM/SD；
- **hist**：每观测一行（`value`）；**scatter**：每观测一行（`x,y[,group]`）；
- 全部示例数据与上游参考成品图（2000px+）在 `assets/examples/`（reference_figs/ 为 Science 风基准，可目检对照）。
