import 'package:flutter/material.dart';
import '../api.dart';
import '../painters.dart';
import '../state.dart';
import '../theme.dart';

class ResultsScreen extends StatefulWidget {
  final AppState app;
  const ResultsScreen({super.key, required this.app});
  @override
  State<ResultsScreen> createState() => _ResultsScreenState();
}

class _ResultsScreenState extends State<ResultsScreen> {
  Map<String, dynamic>? data;
  String? err;
  bool loading = false;

  @override
  void initState() {
    super.initState();
    widget.app.addListener(_maybeLoad);
    _maybeLoad();
  }

  @override
  void dispose() {
    widget.app.removeListener(_maybeLoad);
    super.dispose();
  }

  Future<void> _maybeLoad() async {
    if (data != null || loading || !widget.app.connected) return;
    loading = true;
    try {
      final d = await widget.app.api.results();
      if (mounted) setState(() => data = d);
    } on ApiException catch (e) {
      if (mounted) setState(() => err = e.message);
    }
    loading = false;
  }

  List<double> _col(List l, String k) => l.map((r) => (r[k] as num).toDouble()).toList();

  String _nice(String s) {
    final m = RegExp(r'rate([\d.]+)(?:_loss([\d.]+))?').firstMatch(s);
    if (m == null) return s;
    final loss = m.group(2);
    return '${m.group(1)}/min${loss != null ? ', ${(double.parse(loss) * 100).round()}% loss' : ''}';
  }

  @override
  Widget build(BuildContext context) {
    final pal = Pal.of(context);
    if (data == null) {
      return Center(child: err != null ? Padding(padding: const EdgeInsets.all(20), child: Text(err!, style: TextStyle(color: pal.bad))) : (widget.app.connected ? const CircularProgressIndicator() : const Padding(padding: EdgeInsets.all(20), child: Text('Connect to the backend on the Data tab to load the 20-seed results.'))));
    }
    final load = data!['load'] as List, loss = data!['loss'] as List, paired = data!['paired'] as List;
    final ck = data!['checkpoint'] as Map<String, dynamic>;
    Widget chart(String title, Widget child) => Panel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [SectionTitle(title), const SizedBox(height: 8), SizedBox(height: 260, child: child)]));
    return ListView(padding: const EdgeInsets.all(14), children: [
      Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(color: pal.chip, border: Border(left: BorderSide(color: pal.uni, width: 4))),
        child: Text('20 seeds on synthetic traffic. Coded transmission is nearly tied with plain broadcast at moderate load and gains a few percent under heavy load with a lossy channel. Addressed messaging needs several times more transmissions.', style: TextStyle(color: pal.ink, height: 1.4)),
      ),
      const SizedBox(height: 12),
      chart('Transmissions vs traffic (log)', CustomPaint(painter: LinePainter(load.map((r) => (r['value'] as num).toString()).toList(), [Series('Addressed', _col(load, 'unicast'), pal.uni), Series('Broadcast', _col(load, 'broadcast'), pal.bc), Series('Coded', _col(load, 'coded'), pal.cod, dashed: true)], true, 'aircraft arriving per minute', pal))),
      const SizedBox(height: 12),
      chart('Transmissions vs packet loss (log)', CustomPaint(painter: LinePainter(loss.map((r) => (r['value'] as num).toString()).toList(), [Series('Addressed', _col(loss, 'unicast'), pal.uni), Series('Broadcast', _col(loss, 'broadcast'), pal.bc), Series('Coded', _col(loss, 'coded'), pal.cod, dashed: true)], true, 'packet loss probability', pal))),
      const SizedBox(height: 12),
      chart('Coded saving over broadcast (%)', CustomPaint(painter: BarPainter(paired.map((r) => _nice(r['setting'] as String)).toList(), _col(paired, 'saving_pct'), _col(paired, 'saving_ci'), [pal.cod], 1, 'mean ± 95% CI, paired by seed', pal))),
      const SizedBox(height: 12),
      chart('Exact optimum on small snapshots', CustomPaint(painter: BarPainter(['Broadcast', 'Greedy XOR', 'Exact optimum'], [(ck['broadcast'] as num).toDouble(), (ck['greedy'] as num).toDouble(), (ck['exact'] as num).toDouble()], null, [pal.bc, pal.cod, pal.cod], 2, 'avg transmissions, ${ck['snapshots']} snapshots', pal))),
      const SizedBox(height: 12),
      Panel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionTitle('Paired difference, 20 seeds each'),
          const SizedBox(height: 8),
          for (final r in paired)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Text('${_nice(r['setting'] as String).padRight(18)} saving ${(r['saving_pct'] as num).toStringAsFixed(2)}% ±${(r['saving_ci'] as num).toStringAsFixed(2)} · fewer misses ${(r['miss_diff_pts'] as num).toStringAsFixed(2)} pts', style: mono(pal.ink, 12)),
            ),
          const SizedBox(height: 8),
          Text('Fewer misses = broadcast miss rate minus coded miss rate in percentage points. Positive means coding missed fewer deadlines.', style: TextStyle(color: pal.muted, fontSize: 12.5)),
        ]),
      ),
      const SizedBox(height: 12),
      Panel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionTitle('Caveats'),
          const SizedBox(height: 6),
          for (final t in [
            'Traffic is synthetic; clearances come from a simple controller model.',
            'About a third of pairs miss their deadline under every scheme, mostly because the conflict is already inside the response margin at issue time.',
            'The channel is a queueing model, not a full VDL Mode 2 simulation.',
            'Side information is limited to own clearance plus what an aircraft has decoded.',
          ])
            Padding(padding: const EdgeInsets.only(bottom: 4), child: Text('• $t', style: TextStyle(color: pal.ink, height: 1.35))),
        ]),
      ),
      const SizedBox(height: 24),
    ]);
  }
}
