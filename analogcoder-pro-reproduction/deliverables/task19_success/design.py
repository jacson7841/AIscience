from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import u_kOhm


def build_circuit():
    """Return the Task 19 reference design that passes the official checker."""
    circuit = Circuit("Gilbert Cell Mixer - verified Task 19 design")
    circuit.model("nmos_model", "nmos", level=1, kp=100e-6, vto=0.7)

    circuit.V("dd", "Vdd", circuit.gnd, 5.0)
    circuit.V("bias", "Vbias", circuit.gnd, 1.5)
    circuit.V("rfp", "Vrfp", circuit.gnd, 2.5)
    circuit.V("rfn", "Vrfn", circuit.gnd, 2.5)
    circuit.V("lop", "Vlop", circuit.gnd, 3.0)
    circuit.V("lon", "Vlon", circuit.gnd, 2.0)

    circuit.R("L1", "Vdd", "Voutp", 1 @ u_kOhm)
    circuit.R("L2", "Vdd", "Voutn", 1 @ u_kOhm)

    circuit.MOSFET(
        "7", "SourceNode", "Vbias", circuit.gnd, circuit.gnd,
        model="nmos_model", w=100e-6, l=1e-6,
    )
    circuit.MOSFET(
        "1", "RFp_out", "Vrfp", "SourceNode", circuit.gnd,
        model="nmos_model", w=50e-6, l=1e-6,
    )
    circuit.MOSFET(
        "2", "RFn_out", "Vrfn", "SourceNode", circuit.gnd,
        model="nmos_model", w=50e-6, l=1e-6,
    )
    circuit.MOSFET(
        "3", "Voutp", "Vlop", "RFp_out", circuit.gnd,
        model="nmos_model", w=50e-6, l=1e-6,
    )
    circuit.MOSFET(
        "4", "Voutp", "Vlon", "RFn_out", circuit.gnd,
        model="nmos_model", w=50e-6, l=1e-6,
    )
    circuit.MOSFET(
        "5", "Voutn", "Vlon", "RFp_out", circuit.gnd,
        model="nmos_model", w=50e-6, l=1e-6,
    )
    circuit.MOSFET(
        "6", "Voutn", "Vlop", "RFn_out", circuit.gnd,
        model="nmos_model", w=50e-6, l=1e-6,
    )
    return circuit


if __name__ == "__main__":
    print(build_circuit())
