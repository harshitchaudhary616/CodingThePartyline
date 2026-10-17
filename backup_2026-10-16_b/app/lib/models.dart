import 'dart:math' as math;

double? _d(dynamic v) => v == null ? null : (v as num).toDouble();

int bisectRight(List<double> a, double x) {
  int lo = 0, hi = a.length;
  while (lo < hi) {
    final mid = (lo + hi) >> 1;
    if (a[mid] <= x) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return lo;
}

class Aircraft {
  final String id;
  final int first;
  final List<double?> x, y, z;
  Aircraft(this.id, this.first, this.x, this.y, this.z);

  factory Aircraft.fromJson(Map<String, dynamic> j) => Aircraft(
        j['id'] as String,
        (j['first'] as num).toInt(),
        (j['x'] as List).map(_d).toList(),
        (j['y'] as List).map(_d).toList(),
        (j['z'] as List).map(_d).toList(),
      );

  /// Position (NM) at grid index k, or null when the aircraft is not observed.
  (double, double)? at(int k) {
    final i = k - first;
    if (i < 0 || i >= x.length) return null;
    final a = x[i], b = y[i];
    return (a == null || b == null) ? null : (a, b);
  }

  double alt(int k) {
    final i = k - first;
    if (i < 0 || i >= z.length) return 0;
    return z[i] ?? 0;
  }
}

class Tx {
  final double t0, t1;
  final List<int> msgs;
  final int queue;
  final List<List<int>> res; // [msg, receiver, ok]
  Tx(this.t0, this.t1, this.msgs, this.queue, this.res);
  factory Tx.fromJson(List<dynamic> j) => Tx(
        (j[0] as num).toDouble(),
        (j[1] as num).toDouble(),
        (j[2] as List).map((e) => (e as num).toInt()).toList(),
        (j[3] as num).toInt(),
        (j[4] as List).map((r) => (r as List).map((e) => (e as num).toInt()).toList()).toList(),
      );
}

class PairRec {
  final int m, r;
  final double tIssue, deadline;
  final double? tDone, tEnd;
  PairRec(this.m, this.r, this.tIssue, this.deadline, this.tDone, this.tEnd);
  factory PairRec.fromJson(List<dynamic> j) => PairRec((j[0] as num).toInt(), (j[1] as num).toInt(), (j[2] as num).toDouble(),
      (j[3] as num).toDouble(), _d(j[4]), _d(j[5]));
  bool get onTime => tDone != null && tDone! <= deadline;
}

class SchemeLog {
  final String name;
  final int nTx, nPairs;
  final double miss;
  final double? meanLatency, p95Latency;
  final List<Tx> txs;
  final List<PairRec> pairs;
  late final List<double> txEnd, issueT, onTimeT, failT;
  late final double endT;

  SchemeLog(this.name, this.nTx, this.nPairs, this.miss, this.meanLatency, this.p95Latency, this.txs, this.pairs) {
    txEnd = txs.map((t) => t.t1).toList()..sort();
    issueT = pairs.map((p) => p.tIssue).toList()..sort();
    onTimeT = pairs.where((p) => p.onTime).map((p) => p.tDone!).toList()..sort();
    failT = pairs.where((p) => !p.onTime).map((p) => p.deadline).toList()..sort();
    endT = txs.isEmpty ? 0 : txs.last.t1;
  }

  factory SchemeLog.fromJson(String name, Map<String, dynamic> j) => SchemeLog(
        name,
        (j['n_tx'] as num).toInt(),
        (j['n_pairs'] as num).toInt(),
        (j['miss'] as num).toDouble(),
        _d(j['mean_latency']),
        _d(j['p95_latency']),
        (j['txs'] as List).map((e) => Tx.fromJson(e as List)).toList(),
        (j['pairs'] as List).map((e) => PairRec.fromJson(e as List)).toList(),
      );

  /// Index of first transmission finishing after time t.
  int txIndexAfter(double t) {
    int lo = 0, hi = txs.length;
    while (lo < hi) {
      final mid = (lo + hi) >> 1;
      if (txs[mid].t1 <= t) {
        lo = mid + 1;
      } else {
        hi = mid;
      }
    }
    return lo;
  }
}

class Meta {
  final String source, label;
  final bool isReal;
  final String? note;
  Meta(this.source, this.label, this.isReal, this.note);
  factory Meta.fromJson(Map<String, dynamic> j) => Meta(j['source'] as String? ?? 'synthetic', j['label'] as String? ?? '', j['is_real'] as bool? ?? false, j['note'] as String?);
}

class Playback {
  final double dt;
  final int k;
  final String kind;
  final List<double> bounds; // x0,y0,x1,y1
  final List<double> centre;
  final double rAlert, vsep;
  final List<List<List<double>>> routes;
  final List<Aircraft> aircraft;
  final List<Map<String, dynamic>> clearances;
  final Map<String, SchemeLog> schemes;
  final Meta meta;
  late final double endT;

  Playback(this.dt, this.k, this.kind, this.bounds, this.centre, this.rAlert, this.vsep, this.routes, this.aircraft, this.clearances, this.schemes, this.meta) {
    endT = schemes.values.map((s) => s.endT).fold<double>(60, math.max) + 20;
  }

  factory Playback.fromJson(Map<String, dynamic> j) {
    final sch = <String, SchemeLog>{};
    (j['schemes'] as Map<String, dynamic>).forEach((k, v) => sch[k] = SchemeLog.fromJson(k, v as Map<String, dynamic>));
    return Playback(
      (j['dt'] as num).toDouble(),
      (j['K'] as num).toInt(),
      j['kind'] as String,
      (j['bounds'] as List).map((e) => (e as num).toDouble()).toList(),
      (j['centre'] as List).map((e) => (e as num).toDouble()).toList(),
      (j['r_alert'] as num).toDouble(),
      (j['vsep'] as num).toDouble(),
      ((j['routes'] ?? []) as List).map((r) => (r as List).map((p) => (p as List).map((e) => (e as num).toDouble()).toList()).toList()).toList(),
      (j['aircraft'] as List).map((a) => Aircraft.fromJson(a as Map<String, dynamic>)).toList(),
      (j['clearances'] as List).map((c) => Map<String, dynamic>.from(c as Map)).toList(),
      sch,
      Meta.fromJson(j['meta'] as Map<String, dynamic>),
    );
  }

  String msgLabel(int m) {
    final c = clearances[m];
    final id = aircraft[c['ac'] as int].id;
    final tail = id.length > 3 ? id.substring(id.length - 3) : id;
    final v = c['v'] as int;
    return v > 0 ? '$tail.$v' : tail;
  }

  (double, double)? posAt(int i, double t) {
    final f = t / dt;
    final k = f.floor();
    final a = f - k;
    final p0 = aircraft[i].at(k);
    if (p0 == null) return null;
    final p1 = aircraft[i].at(k + 1);
    if (p1 == null) return p0;
    return (p0.$1 + (p1.$1 - p0.$1) * a, p0.$2 + (p1.$2 - p0.$2) * a);
  }
}
