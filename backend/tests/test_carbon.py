from __future__ import annotations

import pytest

from app.carbon.estimate import classify_material, estimate_element, factor_index, summarize
from app.schemas import ElementSummary


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


def test_estimate_uses_density_and_factor():
    steel = factor_index()["steel"]
    mass, carbon = estimate_element("steel", 2.0)
    assert mass == pytest.approx(2.0 * steel.density_kg_m3)
    assert carbon == pytest.approx(mass * steel.factor_kgco2e_per_kg)


def test_estimate_is_none_without_inputs():
    assert estimate_element(None, 1.0) == (None, None)
    assert estimate_element("steel", None) == (None, None)
    assert estimate_element("unobtainium", 1.0) == (None, None)


def _el(i: int, **kw) -> ElementSummary:
    base = dict(express_id=i, global_id=f"g{i}", ifc_class="IfcWall", storey="L0", material_category="concrete")
    base.update(kw)
    return ElementSummary(**base)


def test_summarize_shares_add_up():
    elements = [
        _el(1, carbon_kgco2e=300.0, volume_m3=1.0, mass_kg=2400.0),
        _el(2, carbon_kgco2e=100.0, volume_m3=0.5, mass_kg=1200.0, material_category="steel", storey="L1"),
        _el(3, material_category=None),
    ]
    summary = summarize(elements)
    assert summary.total_kgco2e == 400.0
    assert summary.estimated_elements == 2
    assert summary.unclassified_elements == 1
    assert summary.missing_volume_elements == 1
    assert [b.key for b in summary.by_material_category] == ["concrete", "steel", "unclassified"]
    assert summary.by_material_category[0].share_percent == 75.0
    assert sum(b.share_percent for b in summary.by_storey) == pytest.approx(100.0)
    assert summary.top_elements[0].global_id == "g1"
