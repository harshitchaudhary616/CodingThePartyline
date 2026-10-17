import 'dart:ui';
import 'package:flutter/foundation.dart';
import 'models.dart';

class Effect {
  final String kind; // ring | beam | label
  final double startMs;
  final String scheme;
  final bool multi;
  final int? receiver;
  final bool ok;
  final String text;
  Effect(this.kind, this.startMs, this.scheme, {this.multi = false, this.receiver, this.ok = true, this.text = ''});
  double get life => kind == 'ring' ? 1000 : kind == 'label' ? 1500 : 800;
}

const double kStartT = 700;

/// Playback clock + visual effects. Repaints are driven by notifyListeners() from a Ticker.
class Player extends ChangeNotifier {
  Playback pb;
  String scheme = 'coded';
  double t = kStartT;
  bool playing = true;
  double speed = 15;
  double wallMs = 0;
  int _ptr = 0;
  Duration? _last;
  final List<Effect> effects = [];

  Player(this.pb) {
    t = kStartT.clamp(0, pb.endT).toDouble();
    _ptr = log.txIndexAfter(t);
  }

  SchemeLog get log => pb.schemes[scheme]!;

  void load(Playback p) {
    pb = p;
    t = kStartT.clamp(0, p.endT).toDouble();
    effects.clear();
    _ptr = log.txIndexAfter(t);
    notifyListeners();
  }

  void setScheme(String s) {
    scheme = s;
    effects.clear();
    _ptr = log.txIndexAfter(t);
    notifyListeners();
  }

  void seek(double v) {
    t = v.clamp(0, pb.endT).toDouble();
    effects.clear();
    _ptr = log.txIndexAfter(t);
    notifyListeners();
  }

  void setSpeed(double v) {
    speed = v;
    notifyListeners();
  }

  void togglePlay() {
    playing = !playing;
    notifyListeners();
  }

  void tick(Duration d) {
    final dt = _last == null ? 0.0 : ((d - _last!).inMicroseconds / 1e6).clamp(0.0, 0.1);
    _last = d;
    wallMs += dt * 1000;
    if (playing) {
      t += dt * speed;
      if (t >= pb.endT) {
        seek(kStartT);
        return;
      }
    }
    final txs = log.txs;
    while (_ptr < txs.length && txs[_ptr].t1 <= t) {
      if (t - txs[_ptr].t1 < 12) _spawn(txs[_ptr]);
      _ptr++;
    }
    effects.removeWhere((e) => wallMs - e.startMs > e.life);
    notifyListeners();
  }

  void _spawn(Tx x) {
    final multi = x.msgs.length > 1;
    effects.add(Effect('ring', wallMs, scheme, multi: multi));
    effects.add(Effect('label', wallMs, scheme, text: x.msgs.map(pb.msgLabel).join(' ⊕ ')));
    for (final r in x.res) {
      effects.add(Effect('beam', wallMs + 160, scheme, multi: multi, receiver: r[1], ok: r[2] == 1));
    }
  }

  /// Open (still-missing) clearances per receiver at time t, and how many are past deadline.
  (List<int>, List<int>) openCounts() {
    final cnt = List<int>.filled(pb.aircraft.length, 0), late = List<int>.filled(pb.aircraft.length, 0);
    for (final p in log.pairs) {
      if (p.tIssue > t) continue;
      if (p.tDone != null && p.tDone! <= t) continue;
      if (p.tEnd != null && p.tEnd! <= t) continue;
      cnt[p.r]++;
      if (p.deadline < t) late[p.r]++;
    }
    return (cnt, late);
  }

  /// Scoreboard numbers for scheme s at time t.
  ({int tx, int issued, int ok, int fail, int open}) board(String s) {
    final L = pb.schemes[s]!;
    final tx = bisectRight(L.txEnd, t), issued = bisectRight(L.issueT, t), ok = bisectRight(L.onTimeT, t), fail = bisectRight(L.failT, t);
    return (tx: tx, issued: issued, ok: ok, fail: fail, open: (issued - ok - fail).clamp(0, 1 << 30));
  }
}

Offset lerpO(Offset a, Offset b, double t) => Offset(a.dx + (b.dx - a.dx) * t, a.dy + (b.dy - a.dy) * t);
