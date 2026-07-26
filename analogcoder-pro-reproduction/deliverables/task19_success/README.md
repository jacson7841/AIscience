# Task 19 成功设计与原理图导出

本目录提供一份已经通过原仓库 `problem_check/Mixer.py` 的 PySpice Gilbert 混频器设计。
它来自仓库参考设计的可复用整理版，不是 `qwen3-coder-plus` 三次实验的成功输出。

## 文件

- `design.py`：只定义 `build_circuit()`，便于复用和导出。
- `verify_official.py`：以原官方测试台执行 DC 搜索、瞬态仿真和 FFT。
- `task19_gilbert_mixer.cir`：从 `str(circuit)` 导出的 SPICE 网表。
- `netlist_structure.json`：解析后的元件、节点、模型和连接关系。
- `schematic_layout.json`：自动布局坐标。
- `task19_gilbert_mixer_schematic.svg`：矢量原理图。
- `task19_gilbert_mixer_schematic.png`：位图原理图。
- `official_verification_waveform.png`：官方测试台波形与 FFT。

## 重新生成

```powershell
python deliverables\task19_success\verify_official.py
python deliverables\task19_success\export_artifacts.py
```

通用导出命令可用于后续成功的 PySpice 文件：

```powershell
python repro_tools\schematic\export_from_pyspice.py 成功代码.py `
  --output-dir 原理图输出目录
```

输入文件必须在全局提供 `circuit`，或定义无必需参数的 `build_circuit()`。解析器目前正式支持
电阻、电容、电感、电压/电流源、二极管、BJT 和 MOSFET；当前自动符号布局重点验证了
Task 19 使用的电阻、电压源和四端 MOSFET。对运放子电路、受控源和层次化子电路需要继续扩展符号布局。

## 自动闭环

`run.py` 的复杂任务通过官方判据后，会对保存的 `_op.py` 自动调用上述通用导出命令，并在
该次运行目录生成 `schematic_retryN/`。原理图导出属于交付后处理；即使它失败，也不会把一个
已经通过电气测试的设计改判为失败，而是保存 `schematic_export_error.txt`。
