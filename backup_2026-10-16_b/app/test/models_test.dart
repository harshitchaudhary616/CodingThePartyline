import 'package:flutter_test/flutter_test.dart';
import 'package:party_line_lab/models.dart';

void main() {
  test('bisectRight counts elements <= x', () {
    expect(bisectRight([1, 2, 2, 5], 2), 3);
    expect(bisectRight([1, 2, 2, 5], 0), 0);
    expect(bisectRight(<double>[], 3), 0);
  });

  test('Playback parses a minimal payload', () {
    final pb = Playback.fromJson({
      'dt': 5, 'K': 4, 'kind': 'synthetic', 'bounds': [0, 0, 10, 10], 'centre': [5, 5], 'r_alert': 4, 'vsep': 2000, 'routes': [],
      'aircraft': [
        {'id': 'AC000', 'first': 0, 'x': [1.0, 2.0, null], 'y': [1.0, 2.0, null], 'z': [0, 0, null]},
        {'id': 'AC001', 'first': 0, 'x': [3.0, 4.0, 5.0], 'y': [3.0, 4.0, 5.0], 'z': [0, 0, 0]},
      ],
      'clearances': [
        {'id': 0, 'ac': 0, 'v': 0, 't': 0.0},
        {'id': 1, 'ac': 1, 'v': 1, 't': 0.0},
      ],
      'schemes': {
        'coded': {
          'n_tx': 1, 'n_pairs': 2, 'miss': 0.0, 'mean_latency': 1.0, 'p95_latency': 1.0,
          'txs': [[0.0, 1.0, [0, 1], 2, [[1, 0, 1], [0, 1, 1]]]],
          'pairs': [[1, 0, 0.0, 50.0, 1.0, null], [0, 1, 0.0, 50.0, 1.0, null]],
        },
      },
      'meta': {'source': 'synthetic', 'label': 'x', 'is_real': false},
    });
    expect(pb.aircraft.length, 2);
    expect(pb.msgLabel(1), '001.1');
    expect(pb.posAt(0, 2.5)!.$1, closeTo(1.5, 1e-9));
    expect(pb.posAt(0, 10.0), isNull);
    final L = pb.schemes['coded']!;
    expect(L.onTimeT.length, 2);
    expect(L.txIndexAfter(0.5), 0);
    expect(L.txIndexAfter(1.0), 1);
  });
}
