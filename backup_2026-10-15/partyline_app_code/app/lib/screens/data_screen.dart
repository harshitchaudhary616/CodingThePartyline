import 'dart:async';
import 'package:flutter/material.dart';
import '../api.dart';
import '../state.dart';
import '../theme.dart';

class DataScreen extends StatefulWidget {
  final AppState app;
  final VoidCallback onSimulate;
  const DataScreen({super.key, required this.app, required this.onSimulate});
  @override
  State<DataScreen> createState() => _DataScreenState();
}

class _DataScreenState extends State<DataScreen> {
  final urlC = TextEditingController(text: 'http://10.0.2.2:8000');
  final keyC = TextEditingController();
  final latMin = TextEditingController(text: '12.0'), lonMin = TextEditingController(text: '79.3'), latMax = TextEditingController(text: '14.0'), lonMax = TextEditingController(text: '81.0');
  final minutesC = TextEditingController(text: '45');
  final csvC = TextEditingController();
  Map<String, dynamic>? job;
  int? jobId;
  Timer? poll;
  String? msg;
  bool msgBad = false;

  AppState get app => widget.app;

  @override
  void initState() {
    super.initState();
    urlC.text = app.api.baseUrl;
    app.addListener(_r);
  }

  void _r() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    app.removeListener(_r);
    poll?.cancel();
    for (final c in [urlC, keyC, latMin, lonMin, latMax, lonMax, minutesC, csvC]) {
      c.dispose();
    }
    super.dispose();
  }

  void _say(String m, {bool bad = false}) => setState(() {
        msg = m;
        msgBad = bad;
      });

  Future<void> _guard(Future<void> Function() f) async {
    try {
      await f();
    } on ApiException catch (e) {
      _say(e.message, bad: true);
    }
  }

  Future<void> _connect() => _guard(() async {
        app.api.baseUrl = urlC.text.trim();
        app.api.apiKey = keyC.text.trim();
        await app.connect();
        _say(app.connected ? 'Connected.' : (app.error ?? 'Could not connect.'), bad: !app.connected);
      });

  Future<void> _record() => _guard(() async {
        final bb = [latMin, lonMin, latMax, lonMax].map((c) => double.tryParse(c.text.trim())).toList();
        final mins = double.tryParse(minutesC.text.trim());
        if (bb.any((v) => v == null) || mins == null) {
          _say('Enter numbers for the bounding box and minutes.', bad: true);
          return;
        }
        final r = await app.api.record(bb.cast<double>(), mins, 10, 'OpenSky ${DateTime.now().toIso8601String().substring(0, 16)}');
        jobId = r['job_id'] as int;
        _say('Recording started. Keep the backend running until it finishes.');
        poll?.cancel();
        poll = Timer.periodic(const Duration(seconds: 3), (_) => _poll());
        await app.refreshDatasets();
      });

  Future<void> _poll() async {
    if (jobId == null) return;
    try {
      final j = await app.api.job(jobId!);
      if (!mounted) return;
      setState(() => job = j);
      if (j['state'] != 'running') {
        poll?.cancel();
        await app.refreshDatasets();
        _say(j['state'] == 'done' ? 'Recording finished: ${j['rows']} position reports.' : 'Recording failed: ${j['message']}', bad: j['state'] != 'done');
      }
    } on ApiException catch (e) {
      _say(e.message, bad: true);
    }
  }

  Future<void> _import() => _guard(() async {
        if (csvC.text.trim().isEmpty) {
          _say('Paste CSV or JSON first.', bad: true);
          return;
        }
        final d = await app.api.uploadText('Imported tracks', csvC.text);
        await app.refreshDatasets();
        csvC.clear();
        _say('Imported ${d['n_rows']} rows as dataset #${d['id']}. Provenance of user files is not verified.');
      });

  @override
  Widget build(BuildContext context) {
    final pal = Pal.of(context);
    return ListView(padding: const EdgeInsets.all(14), children: [
      Panel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionTitle('Server'),
          const SizedBox(height: 8),
          TextField(controller: urlC, decoration: const InputDecoration(labelText: 'Backend address', hintText: 'http://10.0.2.2:8000 (Android emulator) · http://localhost:8000 (iOS sim / desktop)', border: OutlineInputBorder(), isDense: true), keyboardType: TextInputType.url),
          const SizedBox(height: 8),
          TextField(controller: keyC, decoration: const InputDecoration(labelText: 'API key (only if the server sets PL_API_KEY)', border: OutlineInputBorder(), isDense: true), obscureText: true),
          const SizedBox(height: 10),
          FilledButton(onPressed: _connect, child: const Text('Connect')),
          if (msg != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(msg!, style: TextStyle(color: msgBad ? pal.bad : pal.good))),
        ]),
      ),
      const SizedBox(height: 12),
      Panel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionTitle('Datasets'),
          const SizedBox(height: 4),
          Text('Choose one to replay its aircraft paths. Clearances are always simulated.', style: TextStyle(color: pal.muted, fontSize: 13)),
          const SizedBox(height: 8),
          Material(type: MaterialType.transparency, child: RadioListTile<int?>(value: null, groupValue: app.selectedDataset, onChanged: (v) => app.select(v), dense: true, title: const Text('Synthetic traffic (built-in generator)'))),
          for (final d in app.datasets) _datasetTile(d, pal),
          const SizedBox(height: 6),
          Wrap(spacing: 8, children: [
            OutlinedButton.icon(onPressed: () => _guard(() async { await app.api.createDemo(); await app.refreshDatasets(); }), icon: const Icon(Icons.science_outlined), label: const Text('Add synthetic demo file')),
            OutlinedButton.icon(onPressed: () => app.refreshDatasets(), icon: const Icon(Icons.refresh), label: const Text('Refresh')),
            FilledButton.icon(onPressed: widget.onSimulate, icon: const Icon(Icons.play_arrow), label: const Text('Simulate selected')),
          ]),
        ]),
      ),
      const SizedBox(height: 12),
      Panel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionTitle('Record real traffic from OpenSky'),
          const SizedBox(height: 4),
          Text('The backend polls OpenSky every 10 s and stores ADS-B positions. Needs internet on the server and follows OpenSky terms of use.', style: TextStyle(color: pal.muted, fontSize: 13)),
          const SizedBox(height: 10),
          Row(children: [for (final e in [('Lat min', latMin), ('Lon min', lonMin), ('Lat max', latMax), ('Lon max', lonMax)]) Expanded(child: Padding(padding: const EdgeInsets.only(right: 6), child: TextField(controller: e.$2, decoration: InputDecoration(labelText: e.$1, border: const OutlineInputBorder(), isDense: true), keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true))))]),
          const SizedBox(height: 8),
          Row(children: [
            SizedBox(width: 130, child: TextField(controller: minutesC, decoration: const InputDecoration(labelText: 'Minutes', border: OutlineInputBorder(), isDense: true), keyboardType: TextInputType.number)),
            const SizedBox(width: 10),
            FilledButton.icon(onPressed: _record, icon: const Icon(Icons.fiber_manual_record, size: 16), label: const Text('Start recording')),
          ]),
          if (job != null) Padding(padding: const EdgeInsets.only(top: 10), child: Text('job #${job!['id']} · ${job!['state']} · polls ${job!['polls']} · failures ${job!['failures']} · rows ${job!['rows']}${job!['message'] != null ? '\n${job!['message']}' : ''}', style: mono(pal.muted, 12))),
        ]),
      ),
      const SizedBox(height: 12),
      Panel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const SectionTitle('Import a file'),
          const SizedBox(height: 4),
          Text('Paste the CSV from fetch_opensky.py, an OpenSky export (time, icao24, lat, lon), or /states/all JSON.', style: TextStyle(color: pal.muted, fontSize: 13)),
          const SizedBox(height: 8),
          TextField(controller: csvC, maxLines: 6, style: mono(pal.ink, 12), decoration: const InputDecoration(border: OutlineInputBorder(), hintText: 'time,icao24,callsign,lat,lon,velocity,heading,baroaltitude,onground\n…')),
          const SizedBox(height: 8),
          FilledButton(onPressed: _import, child: const Text('Import')),
          const SizedBox(height: 6),
          Text('For large files, use: curl -X POST --data-binary @file.csv "SERVER/api/datasets/upload?name=my+file"', style: mono(pal.muted, 11)),
        ]),
      ),
      const SizedBox(height: 24),
    ]);
  }

  Widget _datasetTile(Map<String, dynamic> d, Pal pal) {
    final real = d['is_real'] == true;
    final status = d['status'] as String;
    final id = d['id'] as int;
    return Material(
      type: MaterialType.transparency,
      child: RadioListTile<int?>(
      value: id,
      groupValue: app.selectedDataset,
      onChanged: status == 'recording' ? null : (v) => app.select(v),
      dense: true,
      title: Text(d['name'] as String),
      subtitle: Wrap(spacing: 8, children: [
        _pill(real ? 'REAL' : 'SYNTHETIC', real ? pal.good : pal.uni),
        _pill(status.toUpperCase(), status == 'ready' ? pal.muted : (status == 'failed' ? pal.bad : pal.uni)),
        Text('${d['n_rows']} rows · ${d['source']}', style: mono(pal.muted, 11)),
      ]),
      secondary: IconButton(
        icon: const Icon(Icons.delete_outline),
        tooltip: 'Delete dataset',
        onPressed: () => _guard(() async {
          await app.api.deleteDataset(id);
          await app.refreshDatasets();
        }),
      ),
    ));
  }

  Widget _pill(String t, Color c) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
        decoration: BoxDecoration(border: Border.all(color: c), borderRadius: BorderRadius.circular(3)),
        child: Text(t, style: TextStyle(color: c, fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 0.6)),
      );
}