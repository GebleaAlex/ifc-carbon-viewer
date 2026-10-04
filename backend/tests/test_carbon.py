from __future__ import annotations

import pytest

from app.carbon.estimate import (
    apply_estimates,
    classify_material,
    classify_name,
    estimate_element,
    factor_index,
    material_usage,
    summarize,
)
from app.schemas import ElementSummary, MaterialLayer


@pytest.mark.parametrize(
    ("names", "category", "expected"),
    [
        (["Concrete C30/37"], None, "concrete"),
        (["Structural steel S355"], None, "steel"),
        (["Clay brick masonry"], None, "masonry"),
        (["CLT timber panel"], None, "timber"),
        (["Double glazing unit"], None, "glass"),
        (["Something exotic"], "steel", "steel"),
        (["Something exotic"], None, None),
        ([], None, None),
    ],
)
def test_classify_material(names, category, expected):
    assert classify_material(names, category) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # keywords must be whole words: v0.1 read "pipe" as IPE steel and "heating" as HEA steel
        ("HDPE pipe", "plastic"),
        ("Underfloor heating screed", "mortar"),
        ("IPE 300", "steel"),
        ("HEA200", "steel"),
        ("C30/37", "concrete"),
        # the most specific keyword wins
        ("Glass wool", "insulation"),
        ("EPS insulation board", "foam_insulation"),
        ("Cement screed", "mortar"),
        ("Concrete block", "concrete"),
        ("Aluminium window frame", "aluminium"),
        # weak keywords only apply when nothing else matches
        ("Window", "glass"),
        ("Insulation", "insulation"),
        # local spellings
        ("Cărămidă plină", "masonry"),
        ("Vată minerală", "insulation"),
        ("Sto Silent acoustic panel", None),
    ],
)
def test_classify_name(name, expected):
    assert classify_name(name) == expected


def test_estimate_uses_density_and_factor():
    steel = factor_index()["steel"]
    mass, carbon = estimate_element("steel", 2.0)
    assert mass == pytest.approx(2.0 * steel.density_kg_m3)
    assert carbon == pytest.approx(mass * steel.factor_kgco2e_per_kg)


def test_estimate_is_none_without_inputs():
    assert estimate_element(None, 1.0) == (None, None)
    assert estimate_element("steel", None) == (None, None)
    assert estimate_element("unobtainium", 1.0) == (None, None)


def _el(i: int, layers: list[tuple[str, float | None]] | None = None, **kw) -> ElementSummary:
    base = dict(
        express_id=i,
        global_id=f"g{i}",
        ifc_class="IfcWall",
        storey="L0",
        volume_m3=1.0,
        layers=[MaterialLayer(material=m, fraction=f) for m, f in (layers or [("Concrete", 1.0)])],
    )
    base.update(kw)
    return ElementSummary(**base)


def test_layers_split_the_volume():
    [wall] = apply_estimates([_el(1, [("Brick", 0.25), ("Mineral wool", 0.5), ("Concrete", 0.25)])])
    assert [layer.volume_m3 for layer in wall.layers] == [0.25, 0.5, 0.25]
    assert wall.carbon_kgco2e == pytest.approx(sum(layer.carbon_kgco2e for layer in wall.layers), rel=1e-3)
    assert wall.material_category == "insulation"  # the largest classified layer by volume


def test_air_gaps_keep_their_share():
    # 40% of the wall is a ventilated cavity with no material: only 60% of the volume is counted.
    [wall] = apply_estimates([_el(1, [("Brick", 0.3), ("Concrete", 0.3)])])
    assert sum(layer.volume_m3 for layer in wall.layers) == pytest.approx(0.6)


def test_unknown_fractions_go_to_the_first_classifiable_material():
    [window] = apply_estimates([_el(1, [("Mystery seal", None), ("Float glass", None)])])
    assert [layer.volume_m3 for layer in window.layers] == [None, 1.0]
    assert window.material_category == "glass"


def test_partially_classified_elements_are_flagged():
    [wall] = apply_estimates([_el(1, [("Concrete", 0.5), ("Mystery board", 0.5)])])
    assert wall.partially_classified
    assert wall.carbon_kgco2e == pytest.approx(0.5 * 2400 * 0.13)


def test_overrides_change_the_category():
    [panel] = apply_estimates([_el(1, [("Sto Silent acoustic panel", 1.0)])], {"Sto Silent acoustic panel": "gypsum"})
    assert panel.material_category == "gypsum"
    [concrete] = apply_estimates([_el(1)], {"Concrete": "unclassified"})
    assert concrete.material_category is None
    assert concrete.carbon_kgco2e is None


def test_summary_skips_assemblies_and_adds_up():
    elements = apply_estimates(
        [
            _el(1),
            _el(2, [("Steel", 1.0)], volume_m3=0.5, storey="L1"),
            _el(3, [("Mystery", 1.0)]),
            _el(4, [], volume_m3=None, is_assembly=True, ifc_class="IfcCurtainWall"),
        ]
    )
    summary = summarize(elements, floor_area_m2=100.0, floor_area_source="spaces")
    concrete = 2400 * 0.13
    steel = 0.5 * 7850 * 1.55
    assert summary.total_kgco2e == pytest.approx(concrete + steel, abs=0.1)
    assert summary.estimated_elements == 2
    assert summary.unclassified_elements == 1
    assert summary.assembly_elements == 1
    assert summary.intensity_kgco2e_m2 == pytest.approx((concrete + steel) / 100, abs=0.1)
    assert [b.key for b in summary.by_material_category] == ["steel", "concrete", "unclassified"]
    assert sum(b.share_percent for b in summary.by_storey) == pytest.approx(100.0)
    assert "IfcCurtainWall" not in {b.key for b in summary.by_ifc_class}
    assert summary.top_elements[0].global_id == "g2"


def test_material_usage_lists_unclassified_first():
    elements = apply_estimates([_el(1), _el(2, [("Mystery", 1.0)]), _el(3)])
    rows = material_usage(elements, {"Concrete": "concrete"})
    assert [r.material for r in rows] == ["Mystery", "Concrete"]
    assert rows[1].element_count == 2
    assert rows[1].overridden
    assert rows[0].auto_category is None
