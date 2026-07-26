from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import u_Hz, u_V


def build_circuit(input_dc=2.5, input_ac=1e-3, input_amplitude=0.0,
                  input_frequency=100.0, transient=False):
    circuit = Circuit("LM358-class signal conditioner reference")
    circuit.V("dd", "Vdd", circuit.gnd, 5 @ u_V)
    circuit.V("ref", "Vref", circuit.gnd, 2.5 @ u_V)

    if transient:
        circuit.SinusoidalVoltageSource(
            "in", "Vin", circuit.gnd,
            dc_offset=input_dc @ u_V,
            offset=input_dc @ u_V,
            amplitude=input_amplitude @ u_V,
            frequency=input_frequency @ u_Hz,
        )
    else:
        circuit.V("in", "Vin", circuit.gnd, f"dc {input_dc} ac {input_ac}")

    # 15.915 kOhm and 10 nF give a first-order pole at approximately 1 kHz.
    circuit.R("filter", "Vin", "Vfilt", 15.915e3)
    circuit.C("filter", "Vfilt", circuit.gnd, 10e-9)

    # High-gain VCVS models the closed-loop behavior of an LM358-class op amp.
    circuit.VoltageControlledVoltageSource(
        "op", "Vout", circuit.gnd, "Vfilt", "Vminus", 1e5
    )
    circuit.R("feedback", "Vout", "Vminus", 40e3)
    circuit.R("gain", "Vminus", "Vref", 10e3)
    circuit.R("load", "Vout", circuit.gnd, 10e3)
    return circuit
