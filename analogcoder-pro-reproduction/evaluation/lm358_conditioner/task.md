# LM358-class active signal conditioner

Design a single-supply, LM358-class non-inverting signal-conditioning circuit in PySpice.

Requirements:

- Supply: 0 V to 5 V.
- Quiescent output: 2.5 V for a 2.5 V input bias.
- Passband signal gain: 5 V/V, measured relative to the 2.5 V bias.
- Low-pass cutoff: 1 kHz, first-order response is acceptable.
- Input signal: 20 mV to 100 mV peak, 10 Hz to 10 kHz, superimposed on 2.5 V.
- At 100 mV peak and 100 Hz, output must remain between 0.2 V and 4.8 V and must not clip.
- Use only local PySpice/Ngspice components. Do not download a vendor model.

Return one complete Python code block. It must define, but not call:

```python
def build_circuit(input_dc=2.5, input_ac=1e-3, input_amplitude=0.0,
                  input_frequency=100.0, transient=False):
    ...
    return circuit
```

The circuit must expose nodes named `Vin` and `Vout`. For AC mode, the input source must have
AC magnitude `input_ac`. For transient mode, it must be sinusoidal with the supplied DC offset,
peak amplitude, and frequency. The testbench will call `configure_pyspice()` itself.

Use the following imports at module scope. Do not put imports inside `build_circuit`, do not import
`Circuit` from any other path, and do not use `SubCircuitFactory` or external macro-model files:

```python
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
```

PySpice 1.5 API constraints for this environment:

- The supported VCVS call is
  `circuit.VoltageControlledVoltageSource('op', 'Vout', circuit.gnd, 'Vplus', 'Vminus', 1e5)`.
- `circuit.E(...)`, `circuit.Node(...)`, `circuit.B(..., expression=...)`, and placeholder
  subcircuits are not supported here. Do not use them.
- The input already carries the required 2.5 V DC bias. Do not remove that bias with a series
  coupling capacitor or leave the op-amp input floating.
- A valid simple architecture is an RC low-pass feeding the non-inverting input, with a resistive
  feedback divider from `Vout` to the inverting input and then to a 2.5 V reference. Choose the
  component values yourself from the gain and cutoff requirements.
- The feedback resistor connected to the 2.5 V reference loads an unbuffered equal-resistor supply
  divider. Prior simulation produced only 3.65 V/V for that reason. Use an ideal 2.5 V reference
  source (or an equivalently stiff/buffered reference) so the feedback network actually realizes
  the calculated gain of 5 V/V.
