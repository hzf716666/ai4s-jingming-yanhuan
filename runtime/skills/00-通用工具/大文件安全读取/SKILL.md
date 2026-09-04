---
name: 大文件安全读取
type: executor
description: 大数据文件(CSV/Parquet/HDF5/FITS/NetCDF/FASTQ/FASTA/VCF/BAM/CRAM/GRIB/ROOT/日志)读取前安全探测与采样: large_file_probe.py 输出小指针(schema+样本+关键数字, 恒定小内存), 禁止整读避免内存溢出与幻觉; 含 VASP/OSZICAR 数值提取。
version: "2.0.0"
stage: 60
stages: [60]
sub_skills: ["大文件安全读取"]
source: econ
---

# 大文件安全读取 — 只读指针，不整读

> 科学数据文件的体积普遍远超上下文窗口（90 GB FASTQ、多 GB HDF5/FITS 快照、
> 20 GB+ NetCDF 栅格、超长 VASP 日志）。整读既会内存溢出又会诱发幻觉——
> 一个材料案例整读消耗 2000 万 token 且**失败**，改用"指针法"后 ~1200 token 即成功。
>
> **铁律：绝不 `cat`/Read 整个数据文件进上下文。** 先探测，从返回的指针
> （schema + 样本 + 关键数字）出发，再用真实库读你需要的具体行/列/列区间。

## 探测一个文件

对**任何**数据文件，在打开前先跑探针（脚本随本技能分发）：

```bash
python "$XDG_CONFIG_HOME/opencode/skills/大文件安全读取/large_file_probe.py" DATA_FILE [--sample N]
```

它在 stdout 输出一行紧凑 JSON 指针——无论文件多大都保持很小
（13 MB CSV → 约 800 字节；16 MB HDF5 → 约 450 字节）。

## 返回什么

- **表格（CSV/TSV）** — 列名 + 推断 dtype、近似行数（流式统计，恒定内存）、
  头部与尾部样本。
- **Parquet** — 仅元数据：schema、行/列/行组计数（不读列数据）。
- **HDF5** — 数据集树 + 形状与 dtype（不读数组数据）。
- **FITS** — HDU 列表 + 维度 + 表头键（mmap 表头）。
- **NetCDF** — 维度与变量及 dtype。
- **NDJSON** — 键并集、记录数、样本。
- **基因组（stdlib，自动穿透 `.gz`，无需库）**：
  - FASTQ（`.fastq/.fq`，含 .fastq.gz）— read 计数、读长 min/max/mean（有界扫描）、
    样本 read id（不吐完整序列）；90 GB FASTQ 直接流式计数；
  - FASTA（`.fasta/.fa/.fna`）— 序列数、总残基数、样本 id；
  - VCF（含 .vcf.gz）— 变异数、`#CHROM` 表头中的样本名、contigs、变异行样本。
- **BAM/CRAM** — 经 `pysam` 读引用列表 + 表头（只读表头，不读比对记录）。
- **GRIB** — 经 `cfgrib`（或 `pygrib` 消息样本）取变量/坐标。
- **ROOT** — 经 `uproot` 列树/分支与条目数（仅元数据）。
- **文本/日志** — 行数与头/尾；VASP `OUTCAR`/`OSZICAR` 做确定性数值提取
  （如最终 `free energy TOTEN`、`energy(sigma->0)`、收敛标志）——只要数字，不要叙述。

**降级行为**：二进制格式如果缺库（pyarrow/h5py/astropy/netCDF4/pysam/cfgrib/uproot），
指针会明确说明并给出安装提示，绝不倒原始字节；FASTQ/FASTA/VCF 完全不需要库。

## 使用模式

1. `json=$(python "…/large_file_probe.py" big.csv)` 先取指针；
2. 在指针上工作：选定列/行号 → 用 pandas/arctic 等真实库只读需要的切片；
3. 写代码/叙述时引用指针里的数字（计数/schema/head/tail），不要凭记忆描述文件内容；
4. 指针里没有的问题（如某行某单元格），二次定向读取该行，仍不整读。
