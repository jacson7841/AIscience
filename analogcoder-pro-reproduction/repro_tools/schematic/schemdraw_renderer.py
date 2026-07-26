from pathlib import Path

import schemdraw
import schemdraw.elements as elm


def _element_map(parsed):
    return {element["name"].lower(): element for element in parsed["elements"]}


def _label(element, fallback):
    if element is None:
        return fallback
    return f"{element['name']}\n{element['value_or_model']}"


def render_vcvs_frontend(parsed, svg_path, png_path):
    """Render the supported RC + VCVS signal-conditioner topology."""
    by_name = _element_map(parsed)
    required = {
        "rinput", "cinput", "eop", "rfeedback", "rground", "rload", "vref",
        "ccomp_minus",
    }
    missing = sorted(required - set(by_name))
    if missing:
        raise ValueError(f"Unsupported VCVS topology; missing: {', '.join(missing)}")

    svg_path = Path(svg_path)
    png_path = Path(png_path)
    svg_path.parent.mkdir(parents=True, exist_ok=True)

    drawing = schemdraw.Drawing(show=False)
    drawing.config(unit=2.0, fontsize=11, lw=1.5)

    # Input source and 1 kHz RC low-pass stage.
    source = drawing.add(elm.SourceV().at((-2.5, -1.4)).up().length(2.0)
                         .label("Vin", loc="left"))
    drawing.add(elm.Label().at((-3.6, -1.75)).label("DC 2.5 V\nAC 1 mV"))
    drawing.add(elm.Ground().at(source.start))
    drawing.add(elm.Line().at(source.end).to((-1.7, 0.6)))
    rin = drawing.add(elm.Resistor().at((-1.7, 0.6)).right().length(3.0)
                      .label(_label(by_name["rinput"], "Rinput")))
    vplus = rin.end
    drawing.add(elm.Dot().at(vplus).label("Vplus", loc="bottom"))
    drawing.add(elm.Capacitor().at(vplus).down().length(2.0))
    drawing.add(elm.Label().at((0.35, -0.55)).label(
        _label(by_name["cinput"], "Cinput")))
    drawing.add(elm.Ground())

    # High-gain VCVS used as the LM358-class op-amp abstraction.
    opamp = drawing.add(elm.Opamp().at((3.0, -0.025)).right().flip()
                         .label("Eop: ideal VCVS, A = 100000", loc="top"))
    drawing.add(elm.Line().at(vplus).to(opamp.in2))
    drawing.add(elm.Dot().at(opamp.in1).label("Vminus", loc="left"))
    drawing.add(elm.Line().at(opamp.out).right().length(2.0))
    vout = drawing.here
    drawing.add(elm.Dot().at(vout).label("Vout", loc="right"))

    # Feedback network: 40 kohm / 10 kohm gives a non-inverting gain near five.
    drawing.add(elm.Line().at(vout).down().length(1.45))
    drawing.add(elm.Resistor().left().length(2.5))
    drawing.add(elm.Label().at((5.9, -0.95)).label(
        _label(by_name["rfeedback"], "Rfeedback")))
    drawing.add(elm.Line().to((opamp.in1[0], opamp.in1[1] - 0.82)))
    drawing.add(elm.Line().to(opamp.in1))

    drawing.add(elm.Resistor().at(opamp.in1).down().length(2.2))
    drawing.add(elm.Label().at((3.95, -1.75)).label(
        _label(by_name["rground"], "Rground")))
    vref_top = drawing.here
    drawing.add(elm.SourceV().at(vref_top).down().length(1.7))
    drawing.add(elm.Label().at((4.05, -3.75)).label("Vref\n2.5 V"))
    drawing.add(elm.Ground())

    drawing.add(elm.Line().at(opamp.in1).left().length(1.3))
    drawing.add(elm.Capacitor().down().length(2.0))
    drawing.add(elm.Label().at((0.75, -1.75)).label(
        _label(by_name["ccomp_minus"], "Ccomp")))
    drawing.add(elm.Ground())

    drawing.add(elm.Resistor().at(vout).down().length(2.0)
                .label(_label(by_name["rload"], "Rload"), loc="right"))
    drawing.add(elm.Ground())

    drawing.add(elm.SourceV().at((9.0, -1.4)).up().length(2.0)
                .label("Vsupply\n5 V", loc="right"))
    drawing.add(elm.Ground().at((9.0, -1.4)))
    drawing.add(elm.Label().at((-2.5, 3.0)).label(
        "LM358-class active signal conditioner\nGenerated from parsed SPICE connectivity"))

    drawing.save(str(svg_path), transparent=False)
    drawing.save(str(png_path), transparent=False, dpi=180)
