"""Integridad de la cartografía local, sin consultas de red."""
import copy
import json
import math
from pathlib import Path

import pytest

from scripts.update_river_geometry import RIVERS, build_geojson


def test_local_river_courses_preserve_detailed_separate_segments():
    path = Path(__file__).resolve().parent.parent / 'app/static/data/rivers.geojson'
    collection = json.loads(path.read_text())
    assert collection['type'] == 'FeatureCollection'
    assert collection['source_timestamp']
    assert collection['license']['name'] == 'Open Database License (ODbL) 1.0'
    assert len(collection['source_sha256']) == 64
    features = collection['features']
    assert {item['properties']['id'] for item in features} == {'chillon'}
    assert {item['properties']['osm_relation_id'] for item in features} == set(RIVERS)
    for feature in features:
        properties = feature['properties']
        assert feature['geometry']['type'] == 'MultiLineString'
        lines = feature['geometry']['coordinates']
        assert len(lines) == len(set(properties['osm_way_ids']))
        points = [point for line in lines for point in line]
        assert properties['vertex_count'] == len(points) > 1000
        assert properties['view_center'] in points
        for line in lines:
            assert len(line) >= 2
            for longitude, latitude in line:
                assert math.isfinite(longitude) and math.isfinite(latitude)
                assert -78 < longitude < -75 and -13 < latitude < -10
        # Each way must meet another way; disconnected imports need investigation.
        endpoints = [tuple(point) for line in lines for point in (line[0], line[-1])]
        assert sum(endpoints.count(point) == 1 for point in endpoints) == 2


@pytest.fixture
def source():
    elements = []
    for relation_id, (_, name, _) in RIVERS.items():
        def member(ref, role, start):
            return {'type': 'way', 'ref': ref, 'role': role,
                    'geometry': [{'lon': start, 'lat': -12}, {'lon': start + .01, 'lat': -12.01}]}
        elements.append({'type': 'relation', 'id': relation_id,
                         'tags': {'type': 'waterway', 'waterway': 'river', 'name': name},
                         'members': [member(1, 'main_stream', -77.1), member(2, '', -76.9),
                                     member(3, 'side_stream', -77.2), member(1, 'main_stream', -77.1)]})
    return {'elements': elements}


def test_import_keeps_exact_coordinates_and_does_not_join_disconnected_ways(source):
    for feature in build_geojson(source)['features']:
        assert feature['properties']['osm_way_ids'] == [1, 2]
        assert feature['geometry']['coordinates'] == [
            [[-77.1, -12], [-77.1 + .01, -12.01]],
            [[-76.9, -12], [-76.9 + .01, -12.01]],
        ]


@pytest.mark.parametrize('failure', ['missing', 'partial', 'wrong_river', 'invalid_point', 'missing_geometry'])
def test_import_rejects_incomplete_or_wrong_source(source, failure):
    document = copy.deepcopy(source)
    if failure == 'missing':
        document['elements'].pop()
    elif failure == 'partial':
        document['remark'] = 'Query timed out'
    elif failure == 'wrong_river':
        document['elements'][0]['tags']['name'] = 'Otro río'
    elif failure == 'invalid_point':
        document['elements'][0]['members'][0]['geometry'][0]['lon'] = float('nan')
    else:
        document['elements'][0]['members'][0]['geometry'] = []
    with pytest.raises(ValueError):
        build_geojson(document)
