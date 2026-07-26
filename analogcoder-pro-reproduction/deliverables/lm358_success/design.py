from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *

def build_circuit(input_dc=2.5, input_ac=1e-3, input_amplitude=0.0,
                  input_frequency=100.0, transient=False):
    circuit = Circuit('LM358 Signal Conditioner')

    # Power supplies
    circuit.V('supply', 'Vcc', circuit.gnd, 5 @ u_V)

    # Input signal
    if transient:
        circuit.V('in', 'Vin', circuit.gnd,
                 f'sin({input_dc} {input_amplitude} {input_frequency})')
    else:
        circuit.V('in', 'Vin', circuit.gnd,
                 f'dc {input_dc} ac {input_ac}')

    # RC low-pass filter at the non-inverting input
    # Cutoff frequency fc = 1/(2*pi*R*C) = 1kHz
    r_input = 15.9 @ u_kΩ  # Approximately 15.9kΩ to get 1kHz with 10nF
    c_input = 10 @ u_nF    # 10nF capacitor
    circuit.R('input', 'Vin', 'Vplus', r_input)
    circuit.C('input', 'Vplus', circuit.gnd, c_input)

    # Create a voltage reference using a dedicated voltage source
    circuit.V('ref', 'Vref_node', circuit.gnd, 2.5 @ u_V)

    # Op-amp (modeling LM358 with high gain VCVS)
    circuit.VoltageControlledVoltageSource('op', 'Vout', circuit.gnd, 'Vplus', 'Vminus', 1e5)

    # Feedback network: Non-inverting amplifier configuration
    # Gain = 1 + (Rf/Rg), where Rf is feedback resistor and Rg connects to reference
    # For gain of 5 V/V, we need Rf/Rg = 4
    # Using Rf = 40kΩ and Rg = 10kΩ
    rf = 40 @ u_kΩ
    rg = 10 @ u_kΩ
    circuit.R('feedback', 'Vout', 'Vminus', rf)
    circuit.R('ground', 'Vminus', 'Vref_node', rg)

    # Add small load resistance to prevent floating nodes
    circuit.R('load', 'Vout', circuit.gnd, 10 @ u_kΩ)

    # Add small capacitances to avoid singular matrix issues
    circuit.C('comp_minus', 'Vminus', circuit.gnd, 1 @ u_pF)

    return circuit
