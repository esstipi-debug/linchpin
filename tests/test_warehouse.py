import json

from warehouse.model import Aisle, Building, Dock, Gate, Layout, Rack, Site, Slot, TruckPath, Yard


def _sample_layout() -> Layout:
    return Layout(
        site=Site(width_m=200.0, depth_m=150.0),
        building=Building(x=60.0, y=70.0, width_m=80.0, depth_m=80.0, height_m=12.0, levels=4),
        yard=Yard(depth_m=40.0, polygon=((60.0, 30.0), (140.0, 30.0), (140.0, 70.0), (60.0, 70.0))),
        gates=(Gate(id="G1", x=100.0, y=0.0, width_m=6.0),),
        docks=(Dock(id="D1", x=80.0, y=70.0, face="south"),),
        aisles=(Aisle(id="A1", x=70.0, y=72.0, length_m=76.0, width_m=3.5, orientation="y"),),
        racks=(Rack(id="R1", x=66.0, y=72.0, width_m=1.2, depth_m=76.0, orientation="y", bays=20, levels=4),),
        slots=(Slot(rack_id="R1", bay=0, level=0, capacity_units=100.0),),
        truck_paths=(TruckPath(kind="in", points=((100.0, 0.0), (80.0, 70.0))),),
        params={"note": "sample"},
    )


def test_layout_round_trips_through_dict():
    layout = _sample_layout()
    assert Layout.from_dict(layout.to_dict()) == layout


def test_layout_dict_is_json_serializable_and_round_trips():
    layout = _sample_layout()
    restored = Layout.from_dict(json.loads(json.dumps(layout.to_dict())))
    assert restored == layout
    assert restored.yard.polygon == layout.yard.polygon  # tuples preserved, not lists
