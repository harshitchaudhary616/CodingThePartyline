import 'dart:ui' show FontFeature;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import '../painters.dart';
import '../player.dart';
import '../state.dart';
import '../theme.dart';

class SimScreen extends StatefulWidget {
  final AppState app;
  const SimScreen({super.key, required this.app});
  @override
  State<SimScreen> createState() => _SimScreenState();
}

class _SimScreenState extends State<SimScreen> with TickerProviderStateMixin {
  Ticker? _ticker;
  bool logY = false;
  Player? _boundPlayer;

  AppState get app => widget.app;

  @override
  void initState() {
    super.initState();
    app.addListener(_onApp);
    _onApp();
  }

  void _onApp() {
    if (app.player != null && app.player != _boundPlayer) {
      _boundPlayer = app.player;
      _ticker?.dispose();
      _ticker = createTicker(_boundPlayer!.tick)..start();
    }
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    app.removeListener(_onApp);
    _ticker?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pal = Pal.of(context);
    final pl = app.player;
    return LayoutBuilder(builder: (context, box) {
      final wide = box.maxWidth > 980;
      final children = <Widget>[
        _banner(pal),
        if (app.error != null) _errorBox(pal),
        const SizedBox(height: 12),
        if (pl == null) _empty(pal) else if (wide) Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(flex: 16, child: Column(children: [_radar(pl, pal), const SizedBox(height: 12), _timeline(pl, pal)])),
          const SizedBox(width: 12),
          Expanded(flex: 10, child: _side(pl, pal)),
        ]) else Column(children: [_radar(pl, pal), const SizedBox(height: 12), _side(pl, pal), const SizedBox(height: 12), _timeline(pl, pal)]),
        const SizedBox(height: 12),
        _paramsPanel(pal),
        const SizedBox(height: 24),
      ];
      return ListView(padding: const EdgeInsets.all(14), children: children);
    });
  }

  Widget _banner(Pal pal) {
    final meta = app.pb?.meta;
    final real = meta?.isReal ?? false;
    final save = app.summary?['coded_saving_vs_broadcast_pct'];
    final text = StringBuffer();
    if (meta == null) {
      text.write('Simulation. ');
    } else if (real) {
      text.write('Recorded aircraft paths (${meta.label}); clearances are simulated. ');
    } else {
      text.write('Synthetic traffic, not real aircraft. ');
    }
    text.write('Coded transmission saves only a few percent of transmissions compared with plain broadcast (20-seed range 0.3% to 3.4%)');
    if (save != null) text.write('; this run: $save%');
    text.write('. The large saving is against sending every clearance as a separate addressed message.');
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: pal.chip, border: Border(left: BorderSide(color: real ? pal.good : pal.uni, width: 4)), borderRadius: BorderRadius.circular(4)),
      child: Text(text.toString(), style: TextStyle(color: pal.ink, fontSize: 13.5, height: 1.4)),
    );
  }

  Widget _errorBox(Pal pal) => Padding(
        padding: const EdgeInsets.only(top: 10),
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: pal.bad.withOpacity(0.12), border: Border.all(color: pal.bad), borderRadius: BorderRadius.circular(4)),
          child: Row(children: [
            Icon(Icons.error_outline, color: pal.bad),
            const SizedBox(width: 10),
            Expanded(child: Text(app.error!, style: TextStyle(color: pal.ink))),
            TextButton(onPressed: app.busy ? null : () => app.connect().then((_) => app.connected ? app.run() : null), child: const Text('Retry')),
          ]),
        ),
      );

  Widget _empty(Pal pal) => Panel(
        child: SizedBox(
          height: 220,
          child: Center(
            child: app.busy
                ? const CircularProgressIndicator()
                : Column(mainAxisSize: MainAxisSize.min, children: [
                    Text('No simulation yet', style: TextStyle(color: pal.ink, fontSize: 18, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 6),
                    Text('Set the server address on the Data tab, then run a scenario.', style: TextStyle(color: pal.muted)),
                    const SizedBox(height: 12),
                    FilledButton(onPressed: () => app.connect().then((_) => app.connected ? app.run() : null), child: const Text('Connect and run')),
                  ]),
          ),
        ),
      );

  Widget _radar(Player pl, Pal pal) {
    return Panel(
      padding: const EdgeInsets.all(10),
      child: Column(children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: AspectRatio(
            aspectRatio: 1 / 0.82,
            child: Stack(children: [
              Positioned.fill(child: CustomPaint(painter: RadarPainter(pl, pal))),
              Positioned(
                left: 8,
                top: 6,
                right: 8,
                child: ListenableBuilder(
                  listenable: pl,
                  builder: (_, __) => Text(
                    '${pl.pb.kind == 'recorded' ? (pl.pb.meta.isReal ? 'RECORDED PATHS' : 'SYNTHETIC FILE') : 'SYNTHETIC'} · t = ${pl.t.round()} s · ${pl.scheme.toUpperCase()} · amber ring = clearances still missing',
                    style: mono(pal.scopeInk, 11),
                  ),
                ),
              ),
              if (app.busy) Positioned.fill(child: Container(color: pal.scope.withOpacity(0.8), child: const Center(child: CircularProgressIndicator()))),
            ]),
          ),
        ),
        const SizedBox(height: 8),
        ListenableBuilder(listenable: pl, builder: (_, __) => _controls(pl, pal)),
      ]),
    );
  }

  Widget _controls(Player pl, Pal pal) {
    return Wrap(spacing: 10, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
      IconButton.filled(onPressed: pl.togglePlay, icon: Icon(pl.playing ? Icons.pause : Icons.play_arrow), tooltip: pl.playing ? 'Pause' : 'Play'),
      IconButton.outlined(onPressed: () => pl.seek(kStartT), icon: const Icon(Icons.replay), tooltip: 'Restart'),
      DropdownButton<double>(
        value: pl.speed,
        underline: const SizedBox.shrink(),
        items: [2, 6, 15, 40, 100].map((s) => DropdownMenuItem(value: s.toDouble(), child: Text('${s}×'))).toList(),
        onChanged: (v) {
          if (v != null) pl.setSpeed(v);
        },
      ),
      SegmentedButton<String>(
        showSelectedIcon: false,
        segments: const [
          ButtonSegment(value: 'unicast', label: Text('Addressed')),
          ButtonSegment(value: 'broadcast', label: Text('Broadcast')),
          ButtonSegment(value: 'coded', label: Text('Coded')),
        ],
        selected: {pl.scheme},
        onSelectionChanged: (s) => pl.setScheme(s.first),
      ),
      SizedBox(
        width: 260,
        child: Slider(value: pl.t.clamp(0, pl.pb.endT).toDouble(), min: 0, max: pl.pb.endT, onChanged: (v) => pl.seek(v)),
      ),
    ]);
  }

  Widget _timeline(Player pl, Pal pal) => Panel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionTitle('Channel timeline'),
          const SizedBox(height: 4),
          Text('blocks = transmissions, line = clearances waiting', style: mono(pal.muted, 11)),
          const SizedBox(height: 6),
          SizedBox(height: 110, child: CustomPaint(painter: TimelinePainter(pl, pal), size: Size.infinite)),
        ]),
      );

  Widget _side(Player pl, Pal pal) {
    return Column(children: [
      ListenableBuilder(
        listenable: pl,
        builder: (_, __) => Column(children: [
          for (final s in ['unicast', 'broadcast', 'coded']) ...[_scheme(pl, pal, s), const SizedBox(height: 10)],
        ]),
      ),
      Panel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            const SectionTitle('Cumulative transmissions'),
            Row(children: [
              Text('log', style: TextStyle(color: pal.muted, fontSize: 12)),
              Switch(value: logY, onChanged: (v) => setState(() => logY = v)),
            ]),
          ]),
          SizedBox(height: 150, child: CustomPaint(painter: CumPainter(pl, pal, logY), size: Size.infinite)),
        ]),
      ),
      const SizedBox(height: 10),
      Panel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionTitle('Latest transmissions'),
          const SizedBox(height: 6),
          ListenableBuilder(listenable: pl, builder: (_, __) => _log(pl, pal)),
        ]),
      ),
    ]);
  }

  Widget _scheme(Player pl, Pal pal, String s) {
    final b = pl.board(s);
    final L = pl.pb.schemes[s]!;
    final base = pl.pb.schemes['broadcast']!;
    final name = {'unicast': 'Addressed', 'broadcast': 'Broadcast', 'coded': 'Coded'}[s]!;
    final sub = {'unicast': 'one message per aircraft', 'broadcast': 'everyone hears everything', 'coded': 'XOR of clearances, deadline-aware'}[s]!;
    final col = pal.scheme(s);
    final den = b.issued == 0 ? 1 : b.issued;
    String fin = 'final: ${L.nTx} tx · ${(L.miss * 100).toStringAsFixed(1)}% missed';
    if (s == 'coded' && base.nTx > 0) fin += ' · ${(100 * (base.nTx - L.nTx) / base.nTx).toStringAsFixed(1)}% fewer than broadcast';
    return GestureDetector(
      onTap: () => pl.setScheme(s),
      child: Panel(
        border: pl.scheme == s ? col : null,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text(name.toUpperCase(), style: TextStyle(color: col, fontSize: 17, fontWeight: FontWeight.w800, letterSpacing: 0.8)),
            Flexible(child: Text(sub, textAlign: TextAlign.right, style: TextStyle(color: pal.muted, fontSize: 12))),
          ]),
          Row(crossAxisAlignment: CrossAxisAlignment.baseline, textBaseline: TextBaseline.alphabetic, children: [
            Text('${b.tx}', style: TextStyle(color: pal.ink, fontSize: 40, fontWeight: FontWeight.w700, fontFeatures: const [FontFeature.tabularFigures()])),
            const SizedBox(width: 6),
            Text('transmissions', style: TextStyle(color: pal.muted, fontSize: 13)),
          ]),
          const SizedBox(height: 4),
          ClipRRect(
            borderRadius: BorderRadius.circular(2),
            child: SizedBox(
              height: 8,
              child: Row(children: _barParts(pal, b.ok * 1000 ~/ den, b.fail * 1000 ~/ den, (den - b.ok - b.fail).clamp(0, den) * 1000 ~/ den)),
            ),
          ),
          const SizedBox(height: 4),
          Text('on time ${b.ok}  missed ${b.fail}  waiting ${b.open}  of ${b.issued}', style: mono(pal.muted, 11)),
          Text(fin, style: mono(pal.muted, 11)),
        ]),
      ),
    );
  }

  List<Widget> _barParts(Pal pal, int ok, int fail, int rest) {
    final out = <Widget>[];
    if (ok > 0) out.add(Expanded(flex: ok, child: Container(color: pal.good)));
    if (fail > 0) out.add(Expanded(flex: fail, child: Container(color: pal.bad)));
    if (rest > 0 || out.isEmpty) out.add(Expanded(flex: rest > 0 ? rest : 1, child: Container(color: pal.chip)));
    return out;
  }

  Widget _log(Player pl, Pal pal) {
    final L = pl.log;
    final i = L.txIndexAfter(pl.t);
    final rows = <Widget>[];
    for (var q = i - 1; q >= 0 && q >= i - 7; q--) {
      final x = L.txs[q];
      final okN = x.res.where((r) => r[2] == 1).length;
      final col = x.msgs.length > 1 ? pal.cod : (okN < x.res.length ? pal.bad : pal.muted);
      rows.add(Text('${x.t1.round().toString().padLeft(5)}s  ${x.msgs.map(pl.pb.msgLabel).join('⊕')}  → $okN/${x.res.length} decoded', style: mono(col, 11), overflow: TextOverflow.ellipsis));
    }
    if (rows.isEmpty) rows.add(Text('waiting for first transmission…', style: mono(pal.muted, 11)));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: rows);
  }

  Widget _paramsPanel(Pal pal) {
    final p = app.params;
    Widget slider(String label, double v, double lo, double hi, int div, String Function(double) f, void Function(double) set) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text(label, style: TextStyle(color: pal.muted, fontSize: 13)), Text(f(v), style: mono(pal.cod, 12))]),
          Slider(value: v, min: lo, max: hi, divisions: div, onChanged: (x) => setState(() => set(x))),
        ]);
    return Panel(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          const SectionTitle('Scenario'),
          Text(app.selectedDataset == null ? 'source: synthetic traffic' : 'source: dataset #${app.selectedDataset}', style: mono(pal.muted, 11)),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 8, children: [
          OutlinedButton(onPressed: () => setState(() { p.rate = 0.5; p.loss = 0.05; }), child: const Text('Light traffic')),
          OutlinedButton(onPressed: () => setState(() { p.rate = 3; p.loss = 0.05; }), child: const Text('Rush hour')),
          OutlinedButton(onPressed: () => setState(() { p.rate = 1.5; p.loss = 0.3; }), child: const Text('Lossy channel')),
          OutlinedButton(onPressed: () => setState(() { p.rate = 3; p.loss = 0.3; }), child: const Text('Heavy + lossy')),
        ]),
        const SizedBox(height: 8),
        if (app.selectedDataset == null) slider('Arrivals per minute', p.rate, 0.5, 4, 7, (v) => v.toStringAsFixed(1), (v) => p.rate = v),
        slider('Packet loss', p.loss, 0, 0.4, 8, (v) => '${(v * 100).round()}%', (v) => p.loss = v),
        slider('Look-ahead horizon (s)', p.horizon, 120, 600, 8, (v) => v.round().toString(), (v) => p.horizon = v),
        slider('Relevance radius (NM)', p.rRel, 6, 20, 14, (v) => v.round().toString(), (v) => p.rRel = v),
        slider('Response margin (s)', p.margin, 30, 150, 4, (v) => v.round().toString(), (v) => p.margin = v),
        slider('Other channel traffic', p.bg, 0, 0.7, 7, (v) => '${(v * 100).round()}%', (v) => p.bg = v),
        Row(children: [
          FilledButton.icon(onPressed: app.busy ? null : app.run, icon: const Icon(Icons.play_circle_outline), label: Text(app.busy ? 'Running…' : 'Run scenario')),
          const SizedBox(width: 12),
          if (app.summary != null)
            Expanded(child: Text('${app.summary!['n_aircraft']} aircraft · ${app.summary!['n_clearances']} clearances · computed in ${app.summary!['compute_s']} s', style: mono(pal.muted, 11))),
        ]),
      ]),
    );
  }
}
