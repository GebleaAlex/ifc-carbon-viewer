"""Command line entry point: parse an IFC file and print a carbon summary, optionally writing the GLB.

python -m app.cli samples/sample-building.ifc --glb out.glb
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.ifc.parse import parse_ifc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse an IFC file and estimate embodied carbon.")
    parser.add_argument("ifc", type=Path, help="path to the .ifc file")
    parser.add_argument("--glb", type=Path, help="write the tessellated geometry to this .glb file")
    parser.add_argument("--top", type=int, default=5, help="how many top emitting elements to list")
    args = parser.parse_args(argv)

    parsed = parse_ifc(args.ifc)
    print(f"{args.ifc.name}: {parsed.schema_version}, {len(parsed.elements)} elements, {parsed.parse_seconds}s")
    print(f"storeys: {', '.join(parsed.storeys) or '-'}")
    print(f"total embodied carbon (indicative): {parsed.carbon.total_kgco2e / 1000:.1f} tCO2e")
    print("by material category:")
    for bucket in parsed.carbon.by_material_category:
        print(
            f"  {bucket.label:<14} {bucket.carbon_kgco2e / 1000:>8.1f} tCO2e  "
            f"{bucket.share_percent:>5.1f}%  ({bucket.element_count} elements)"
        )
    print(f"top {args.top} elements:")
    for el in parsed.carbon.top_elements[: args.top]:
        print(f"  {el.ifc_class:<14} {el.name or el.global_id:<28} {(el.carbon_kgco2e or 0) / 1000:>7.2f} tCO2e")
    if args.glb:
        args.glb.write_bytes(parsed.glb)
        print(f"wrote {args.glb} ({len(parsed.glb) / 1024:.1f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
