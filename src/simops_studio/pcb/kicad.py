"""Focused KiCad PCB text parser.

This parser extracts the metadata needed by the bundled workflow. It is not a
replacement for KiCad's complete parser or native DRC engine.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from simops_studio.hashing import hash_file
from simops_studio.models import PcbRules


@dataclass(frozen=True)
class PcbViolation:
    rule: str
    severity: str
    message: str


def _numbers(pattern: str, text: str) -> list[tuple[str, ...]]:
    return re.findall(pattern, text, flags=re.MULTILINE)


def analyze_kicad_pcb(path: str | Path, rules: PcbRules) -> dict[str, Any]:
    pcb_path = Path(path)
    text = pcb_path.read_text(encoding="utf-8")
    if "(kicad_pcb" not in text:
        raise ValueError("file is not a KiCad PCB document")

    net_entries = _numbers(r'\(net\s+(\d+)\s+"([^"]*)"\)', text)
    nets = {int(number): name for number, name in net_entries}
    segment_pattern = (
        r'\(segment\s+\(start\s+([\d.+-]+)\s+([\d.+-]+)\)\s+'
        r'\(end\s+([\d.+-]+)\s+([\d.+-]+)\)\s+'
        r'\(width\s+([\d.+-]+)\)\s+\(layer\s+"([^"]+)"\)\s+\(net\s+(\d+)\)'
    )
    segments = _numbers(segment_pattern, text)
    via_pattern = (
        r'\(via\s+\(at\s+([\d.+-]+)\s+([\d.+-]+)\)\s+'
        r'\(size\s+([\d.+-]+)\)\s+\(drill\s+([\d.+-]+)\)'
        r'.*?\(net\s+(\d+)\)'
    )
    vias = re.findall(via_pattern, text, flags=re.MULTILINE)
    footprint_count = len(re.findall(r'^\s*\(footprint\s+"', text, flags=re.MULTILINE))
    copper_layers = sorted(
        set(re.findall(r'^\s*\(\d+\s+"([FB]|In\d+)\.Cu"', text, flags=re.MULTILINE))
    )

    track_lengths_by_net: dict[str, float] = {}
    track_widths: list[float] = []
    violations: list[PcbViolation] = []
    for x1, y1, x2, y2, width_text, _layer, net_number in segments:
        width = float(width_text)
        track_widths.append(width)
        name = nets.get(int(net_number), f"net-{net_number}")
        length = math.hypot(float(x2) - float(x1), float(y2) - float(y1))
        track_lengths_by_net[name] = track_lengths_by_net.get(name, 0.0) + length
        if width < rules.min_track_width_mm:
            violations.append(
                PcbViolation(
                    "MIN_TRACK_WIDTH",
                    "error",
                    f"{name} track width {width:.3f} mm is below {rules.min_track_width_mm:.3f} mm",
                )
            )

    via_drills: list[float] = []
    for _x, _y, size_text, drill_text, net_number in vias:
        size = float(size_text)
        drill = float(drill_text)
        via_drills.append(drill)
        name = nets.get(int(net_number), f"net-{net_number}")
        if drill < rules.min_via_drill_mm:
            violations.append(
                PcbViolation(
                    "MIN_VIA_DRILL",
                    "error",
                    f"{name} via drill {drill:.3f} mm is below {rules.min_via_drill_mm:.3f} mm",
                )
            )
        annular = (size - drill) / 2
        if annular < rules.min_annular_ring_mm:
            violations.append(
                PcbViolation(
                    "MIN_ANNULAR_RING",
                    "error",
                    f"{name} annular ring {annular:.3f} mm is below {rules.min_annular_ring_mm:.3f} mm",
                )
            )

    return {
        "source": str(pcb_path.resolve()),
        "sha256": hash_file(pcb_path),
        "net_count": len([name for name in nets.values() if name]),
        "nets": sorted(name for name in nets.values() if name),
        "copper_layer_count": len(copper_layers),
        "segment_count": len(segments),
        "via_count": len(vias),
        "footprint_count": footprint_count,
        "total_track_length_mm": round(sum(track_lengths_by_net.values()), 6),
        "track_lengths_by_net_mm": {
            key: round(value, 6) for key, value in sorted(track_lengths_by_net.items())
        },
        "minimum_track_width_mm": min(track_widths) if track_widths else None,
        "minimum_via_drill_mm": min(via_drills) if via_drills else None,
        "status": "PASS" if not violations else "FAIL",
        "violations": [asdict(item) for item in violations],
        "limitations": [
            "Focused metadata checks do not replace native clearance or connectivity DRC.",
            "Manufacturing sign-off requires the actual stackup and fabricator rules.",
        ],
    }

