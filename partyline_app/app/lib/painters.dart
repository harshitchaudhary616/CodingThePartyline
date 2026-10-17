import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'models.dart';
import 'player.dart';
import 'theme.dart';

void _text(Canvas c, String s, Offset o, TextStyle st, {bool center = false, bool right = false}) {
  final tp = TextPainter(text: TextSpan(text: s, style: st), textDirection: TextDirection.ltr)..layout();
  var dx = o.dx;
  if (center) dx -= tp.width / 2;
  if (right) dx -= tp.width;
  tp.paint(c, Offset(dx, o.dy - tp.height / 2));
}

/// Animated radar scope: aircraft, trails, conflict links, awareness halos and transmission effects.
class RadarPainter extends CustomPainter {
  final Player pl;
  final Pal pal;
  RadarPainter(this.pl, this.pal) : super(repaint: pl);

  @override
  void paint(Canvas canvas, Size size) {
    final pb = pl.pb;
    final w = size.width, h = size.height;
    canvas.drawRect(Offset.zero & size, Paint()..color = pal.scope);
    final b = pb.bounds, bw = b[2] - b[0], bh = b[3] - b[1];
    const pad = 22.0;
    final sc = math.min((w - 2 * pad) / bw, (h - 2 * pad) / bh);
    final ox = (w - bw * sc) / 2, oy = (h - bh * sc) / 2;
    Offset W(double x, double y) => Offset(ox + (x - b[0]) * sc, h - (oy + (y - b[1]) * sc));
    final ctr = W(pb.centre[0], pb.centre[1]);
    final line = Paint()..color = pal.scopeLine..style = PaintingStyle.stroke..strokeWidth = 1;
    final dim = TextStyle(color: pal.scopeDim, fontSize: 9, fontFamily: 'monospace');
    final maxR = math.sqrt(bw * bw + bh * bh) / 2;
    for (double r = 20; r <= maxR; r += 20) {
      canvas.drawCircle(ctr, r * sc, line);
      _text(canvas, '${r.toInt()} NM', ctr + Offset(r * sc * 0.707 + 3, -r * sc * 0.707 - 3), dim);
    }
    for (final r in pb.routes) {
      final path = Path();
      for (var i = 0; i < r.length; i++) {
        final p = W(r[i][0], r[i][1]);
        i == 0 ? path.moveTo(p.dx, p.dy) : path.lineTo(p.dx, p.dy);
      }
      canvas.drawPath(path, line);
    }
    final n = pb.aircraft.length;
    final P = List<Offset?>.generate(n, (i) {
      final p = pb.posAt(i, pl.t);
      return p == null ? null : W(p.$1, p.$2);
    });
    final k = (pl.t / pb.dt).floor();
    // conflict links
    final bad = Paint()..color = pal.bad.withOpacity(0.6)..strokeWidth = 1.2;
    final worldPos = List<(double, double)?>.generate(n, (i) => pb.posAt(i, pl.t));
    for (var i = 0; i < n; i++) {
      final a = worldPos[i];
      if (a == null) continue;
      for (var j = i + 1; j < n; j++) {
        final c = worldPos[j];
        if (c == null) continue;
        final dx = a.$1 - c.$1, dy = a.$2 - c.$2;
        if (dx * dx + dy * dy < pb.rAlert * pb.rAlert && (pb.aircraft[i].alt(k) - pb.aircraft[j].alt(k)).abs() <= pb.vsep) {
          canvas.drawLine(P[i]!, P[j]!, bad);
        }
      }
    }
    // trails
    final trail = Paint()..color = pal.scopeDim..style = PaintingStyle.stroke..strokeWidth = 1;
    for (var i = 0; i < n; i++) {
      if (P[i] == null) continue;
      final path = Path();
      var started = false;
      for (var q = math.max(0, k - 14); q <= k; q++) {
        final p = pb.aircraft[i].at(q);
        if (p == null) continue;
        final o = W(p.$1, p.$2);
        if (!started) {
          path.moveTo(o.dx, o.dy);
          started = true;
        } else {
          path.lineTo(o.dx, o.dy);
        }
      }
      canvas.drawPath(path, trail);
    }
    // halos + aircraft
    final (cnt, late) = pl.openCounts();
    for (var i = 0; i < n; i++) {
      final o = P[i];
      if (o == null) continue;
      if (cnt[i] > 0) {
        canvas.drawCircle(o, 6 + math.min(cnt[i], 8) * 1.4, Paint()..style = PaintingStyle.stroke..strokeWidth = late[i] > 0 ? 2 : 1.4..color = late[i] > 0 ? pal.bad : pal.uni);
      }
      canvas.drawCircle(o, 3, Paint()..color = pal.scopeInk);
      final id = pb.aircraft[i].id;
      _text(canvas, id.length > 4 ? id.substring(id.length - 4) : id, o + const Offset(8, -6), dim);
      if (cnt[i] > 0) _text(canvas, '×${cnt[i]}', o + const Offset(8, 6), TextStyle(color: late[i] > 0 ? pal.bad : pal.uni, fontSize: 9, fontFamily: 'monospace'));
    }
    // tower
    final col = pal.scheme(pl.scheme);
    canvas.save();
    canvas.translate(ctr.dx, ctr.dy);
    canvas.rotate(math.pi / 4);
    canvas.drawRect(const Rect.fromLTWH(-4, -4, 8, 8), Paint()..color = col);
    canvas.restore();
    _text(canvas, 'TWR', ctr + const Offset(9, 14), TextStyle(color: pal.scopeInk, fontSize: 9, fontFamily: 'monospace'));
    // effects
    for (final e in pl.effects) {
      final age = pl.wallMs - e.startMs;
      if (age < 0 || age > e.life) continue;
      final u = age / e.life;
      final c = pal.scheme(e.scheme);
      if (e.kind == 'ring') {
        final st = Paint()..style = PaintingStyle.stroke..strokeWidth = e.multi ? 3 : 2..color = c.withOpacity(1 - u);
        canvas.drawCircle(ctr, 10 + u * math.min(w, h) * 0.5, st);
        if (e.multi) canvas.drawCircle(ctr, 10 + u * math.min(w, h) * 0.38, st);
      } else if (e.kind == 'beam') {
        final o = e.receiver != null && e.receiver! < n ? P[e.receiver!] : null;
        if (o == null) continue;
        final reach = math.min(1.0, u * 2.2);
        final st = Paint()..style = PaintingStyle.stroke..strokeWidth = e.multi ? 2.2 : 1.4..color = (e.ok ? c : pal.bad).withOpacity(1 - u * 0.7);
        canvas.drawLine(ctr, lerpO(ctr, o, reach), st);
        if (reach >= 1) {
          canvas.drawCircle(o, 5 + u * 10, st);
          if (!e.ok) _text(canvas, 'lost', o + const Offset(10, 16), TextStyle(color: pal.bad, fontSize: 9, fontFamily: 'monospace'));
        }
      } else if (e.kind == 'label') {
        final st = TextStyle(color: c.withOpacity(math.min(1.0, 2 * (1 - u))), fontSize: 13, fontWeight: FontWeight.w600, fontFamily: 'monospace');
        _text(canvas, e.text, ctr + Offset(0, -22 - u * 12), st, center: true);
      }
    }
  }

  @override
  bool shouldRepaint(covariant RadarPainter old) => true;
}

/// Channel timeline: transmissions (blocks) and number of clearances waiting (line).
class TimelinePainter extends CustomPainter {
  final Player pl;
  final Pal pal;
  TimelinePainter(this.pl, this.pal) : super(repaint: pl);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    final t1 = pl.t + 20, t0 = t1 - 150;
    double X(double t) => (t - t0) / (t1 - t0) * w;
    final grid = Paint()..color = pal.line..strokeWidth = 1;
    final lab = mono(pal.muted, 9);
    const padB = 16.0;
    for (var s = (t0 / 30).ceil() * 30; s <= t1; s += 30) {
      canvas.drawLine(Offset(X(s.toDouble()), 0), Offset(X(s.toDouble()), h - padB), grid);
      _text(canvas, '${s}s', Offset(X(s.toDouble()) + 2, h - 6), lab);
    }
    final txs = pl.log.txs;
    var maxQ = 1;
    for (final x in txs) {
      if (x.queue > maxQ) maxQ = x.queue;
    }
    final qp = Path();
    var started = false;
    for (final x in txs) {
      if (x.t1 < t0 || x.t0 > t1) continue;
      final yy = h - padB - (x.queue / maxQ) * (h - padB - 30);
      if (!started) {
        qp.moveTo(X(x.t0), yy);
        started = true;
      }
      qp.lineTo(X(x.t0), yy);
      qp.lineTo(X(x.t1), yy);
    }
    canvas.drawPath(qp, Paint()..style = PaintingStyle.stroke..color = pal.muted.withOpacity(0.6)..strokeWidth = 1.2);
    final col = pal.scheme(pl.scheme);
    for (final x in txs) {
      if (x.t1 < t0 || x.t0 > t1) continue;
      final a = X(x.t0), b = math.max(a + 2, X(x.t1));
      canvas.drawRect(Rect.fromLTRB(a, 4, b, 26), Paint()..color = col.withOpacity(x.msgs.length > 1 ? 1 : 0.55));
      if (x.msgs.length > 1) _text(canvas, '⊕${x.msgs.length}', Offset(a + 2, 15), TextStyle(color: pal.panel, fontSize: 9, fontFamily: 'monospace'));
    }
    canvas.drawLine(Offset(X(pl.t), 0), Offset(X(pl.t), h - padB), Paint()..color = pal.ink..strokeWidth = 1);
    _text(canvas, 'max waiting: $maxQ', Offset(4, h - padB - 6), lab);
  }

  @override
  bool shouldRepaint(covariant TimelinePainter old) => true;
}

/// Cumulative transmissions per scheme with playhead.
class CumPainter extends CustomPainter {
  final Player pl;
  final Pal pal;
  final bool logY;
  CumPainter(this.pl, this.pal, this.logY) : super(repaint: pl);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    const padL = 34.0, padB = 18.0, padT = 8.0, padR = 8.0;
    final pb = pl.pb;
    final maxN = math.max(1, pb.schemes.values.map((s) => s.nTx).fold<int>(0, math.max));
    final T = pb.endT;
    double yv(num n) => logY ? math.log(n + 1) / math.log(maxN + 1) : n / maxN;
    double X(double t) => padL + t / T * (w - padL - padR);
    double Y(num n) => h - padB - yv(n) * (h - padB - padT);
    final grid = Paint()..color = pal.line..strokeWidth = 1;
    final lab = mono(pal.muted, 9);
    final ticks = logY ? [1, 10, 100, 1000].where((v) => v <= maxN * 1.2).toList() : [0, .25, .5, .75, 1].map((f) => (f * maxN).round()).toList();
    for (final v in ticks) {
      canvas.drawLine(Offset(padL, Y(v)), Offset(w - padR, Y(v)), grid);
      _text(canvas, '$v', Offset(2, Y(v)), lab);
    }
    _text(canvas, '${T.round()} s', Offset(w - padR, h - 6), lab, right: true);
    for (final s in ['unicast', 'broadcast', 'coded']) {
      final e = pb.schemes[s]!.txEnd;
      final path = Path()..moveTo(X(0), Y(0));
      final stepN = math.max(1, e.length ~/ 400);
      for (var i = 0; i < e.length; i += stepN) {
        path.lineTo(X(e[i]), Y(i));
      }
      if (e.isNotEmpty) path.lineTo(X(e.last), Y(e.length));
      canvas.drawPath(path, Paint()..style = PaintingStyle.stroke..strokeWidth = s == pl.scheme ? 2.6 : 1.5..color = pal.scheme(s).withOpacity(s == pl.scheme ? 1 : 0.75));
    }
    canvas.drawLine(Offset(X(pl.t), padT), Offset(X(pl.t), h - padB), Paint()..color = pal.ink..strokeWidth = 1);
  }

  @override
  bool shouldRepaint(covariant CumPainter old) => true;
}

class Series {
  final String name;
  final List<double> y;
  final Color color;
  final bool dashed;
  Series(this.name, this.y, this.color, {this.dashed = false});
}

/// Static line chart (optionally log-y) for the Results tab.
class LinePainter extends CustomPainter {
  final List<String> xs;
  final List<Series> series;
  final bool logY;
  final String xLabel;
  final Pal pal;
  LinePainter(this.xs, this.series, this.logY, this.xLabel, this.pal);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    const l = 46.0, r = 12.0, t = 28.0, b = 40.0;
    final ymax = series.expand((s) => s.y).fold<double>(1, math.max);
    double py(double v) => logY ? h - b - math.log(math.max(v, 1)) / math.log(ymax * 1.15) * (h - t - b) : h - b - v / (ymax * 1.08) * (h - t - b);
    double px(int i) => l + (xs.length == 1 ? 0 : i / (xs.length - 1)) * (w - l - r);
    final grid = Paint()..color = pal.line..strokeWidth = 1;
    final lab = mono(pal.muted, 10);
    final ticks = logY ? [1, 10, 100, 1000].where((v) => v <= ymax * 1.15).map((e) => e.toDouble()).toList() : [0, .25, .5, .75, 1].map((f) => (f * ymax).roundToDouble()).toList();
    for (final v in ticks) {
      canvas.drawLine(Offset(l, py(v)), Offset(w - r, py(v)), grid);
      _text(canvas, v.toStringAsFixed(0), Offset(l - 6, py(v)), lab, right: true);
    }
    for (var i = 0; i < xs.length; i++) {
      _text(canvas, xs[i], Offset(px(i), h - b + 14), lab, center: true);
    }
    _text(canvas, xLabel, Offset(w / 2, h - 8), lab, center: true);
    var lx = l;
    for (final s in series) {
      canvas.drawRect(Rect.fromLTWH(lx, 6, 10, 10), Paint()..color = s.color);
      _text(canvas, s.name, Offset(lx + 14, 11), lab);
      lx += 28 + s.name.length * 7.0;
      final pts = [for (var i = 0; i < s.y.length; i++) Offset(px(i), py(s.y[i]))];
      final path = Path()..moveTo(pts.first.dx, pts.first.dy);
      for (final p in pts.skip(1)) {
        path.lineTo(p.dx, p.dy);
      }
      canvas.drawPath(path, Paint()..style = PaintingStyle.stroke..strokeWidth = s.dashed ? 2 : 2.6..color = s.color);
      for (final p in pts) {
        canvas.drawCircle(p, 3.2, Paint()..color = s.color);
      }
    }
  }

  @override
  bool shouldRepaint(covariant LinePainter old) => true;
}

/// Static bar chart with optional error bars.
class BarPainter extends CustomPainter {
  final List<String> labels;
  final List<double> values;
  final List<double>? errs;
  final List<Color> colors;
  final int dec;
  final String yLabel;
  final Pal pal;
  BarPainter(this.labels, this.values, this.errs, this.colors, this.dec, this.yLabel, this.pal);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    const l = 46.0, r = 12.0, t = 30.0, b = 46.0;
    var ymax = 1.0;
    for (var i = 0; i < values.length; i++) {
      ymax = math.max(ymax, values[i] + (errs == null ? 0 : errs![i]));
    }
    ymax *= 1.15;
    double py(double v) => h - b - v / ymax * (h - t - b);
    final grid = Paint()..color = pal.line..strokeWidth = 1;
    final lab = mono(pal.muted, 10);
    for (var k = 0; k <= 4; k++) {
      final v = ymax * k / 4;
      canvas.drawLine(Offset(l, py(v)), Offset(w - r, py(v)), grid);
      _text(canvas, v.toStringAsFixed(dec), Offset(l - 6, py(v)), lab, right: true);
    }
    _text(canvas, yLabel, Offset(l, 12), lab);
    final bw = (w - l - r) / values.length;
    for (var i = 0; i < values.length; i++) {
      final x = l + i * bw + bw * 0.2, ww = bw * 0.6;
      canvas.drawRRect(RRect.fromRectAndRadius(Rect.fromLTRB(x, py(values[i]), x + ww, py(0)), const Radius.circular(2)), Paint()..color = colors[i % colors.length]);
      final top = errs == null ? values[i] : values[i] + errs![i];
      if (errs != null) {
        final st = Paint()..color = pal.ink..strokeWidth = 1.6;
        final cx = x + ww / 2;
        canvas.drawLine(Offset(cx, py(math.max(0, values[i] - errs![i]))), Offset(cx, py(top)), st);
        canvas.drawLine(Offset(cx - 6, py(top)), Offset(cx + 6, py(top)), st);
        canvas.drawLine(Offset(cx - 6, py(math.max(0, values[i] - errs![i]))), Offset(cx + 6, py(math.max(0, values[i] - errs![i]))), st);
      }
      _text(canvas, values[i].toStringAsFixed(dec), Offset(x + ww / 2, py(top) - 9), mono(pal.ink, 10), center: true);
      _text(canvas, labels[i], Offset(x + ww / 2, h - b + 16), lab, center: true);
    }
  }

  @override
  bool shouldRepaint(covariant BarPainter old) => true;
}
