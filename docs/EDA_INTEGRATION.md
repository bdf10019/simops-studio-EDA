# EDA integration guide

SimOps Studio provides three adapters behind the same `SimulationAdapter` contract. Optional
tools are never downloaded, licensed, or executed unless selected in the project file.

## Built-in PDN adapter

`builtin-pdn` is the default and has no external executable dependency. It evaluates a
synthetic RLC lumped topology over a log-spaced frequency vector. It is deterministic and
suited to workflow demonstrations and regression tests, not production SI/PI sign-off.

```yaml
simulation:
  adapter: builtin-pdn
```

## ngspice adapter

The optional adapter creates a temporary one-amp AC injection deck and calls ngspice in batch
mode. The resulting voltage magnitude is interpreted as impedance magnitude. Install ngspice
separately, confirm its license and environment, then use:

```yaml
simulation:
  adapter: ngspice
  adapter_options:
    executable: ngspice
```

Run `python -m simops_studio doctor` before dispatch. The bundled environment and CI do not
require ngspice, so this integration remains an explicit local option.

## External-command adapter

This adapter is the stable boundary for a licensed solver wrapper or an internal simulation
service client. The command must be a YAML list. SimOps Studio replaces the exact tokens
`{input_json}` and `{output_csv}`, runs with `shell=False`, and requires a successful process
within 300 seconds.

```yaml
simulation:
  adapter: external-command
  adapter_options:
    command:
      - C:\Tools\solver-wrapper.exe
      - --input
      - "{input_json}"
      - --output
      - "{output_csv}"
```

The input contract is JSON:

```json
{
  "case_id": "case-...",
  "parameters": {
    "plane_resistance_ohm": 0.008,
    "plane_inductance_h": 8e-10,
    "capacitance_f": 4.7e-6,
    "capacitor_esr_ohm": 0.012,
    "capacitor_esl_h": 4e-10
  },
  "frequency": {"start_hz": 1000, "stop_hz": 100000000, "points": 401}
}
```

The wrapper must write UTF-8 CSV containing at least:

```csv
frequency_hz,impedance_ohm
1000,0.0081
100000000,0.1392
```

Never put license credentials in the project file. Configure them through the vendor-approved
local environment or license server, and keep machine-specific settings outside Git.

## KiCad PCB analysis

The parser reads the text-based `.kicad_pcb` file directly and reports nets, copper layers,
segments, vias, footprints, total/per-net track length, minimum track width, minimum via drill,
and focused width/drill/annular-ring violations. It does not call `kicad-cli` and does not
replace native clearance, connectivity, stackup, or fabrication DRC.

Commercial board tools can be integrated through an authorized export step that emits a
neutral JSON/CSV contract. Proprietary board files, installation paths, credentials, and tool
binaries should remain outside this repository.
