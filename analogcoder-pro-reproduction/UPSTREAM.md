# 上游来源与引用

本目录中的 `run.py`、官方任务描述、提示模板和 Task 19 测试台基于 AnalogCoder-Pro 公开仓库：

- Repository: https://github.com/laiyao1/AnalogCoderPro
- AnalogCoder: https://arxiv.org/abs/2405.14918
- AnalogCoder-Pro paper DOI: https://doi.org/10.1109/TCAD.2026.3673493

本复现保留了论文代码的核心生成/仿真/反馈逻辑，并为本地 Python 3.13、Ngspice 46、百炼接口、
结构化实验记录、LM358 迁移测试和原理图导出进行了工程适配。详细差异见
[相对论文代码修改说明](docs/相对论文代码修改说明.md)。

公开下载副本未包含论文所述的完整 `optimize/`、`mosfet_model/` 和若干检索资源，因此本仓库
不补造或声称复现这些未发布功能。
