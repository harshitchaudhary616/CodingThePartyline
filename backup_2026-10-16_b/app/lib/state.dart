import 'package:flutter/foundation.dart';
import 'api.dart';
import 'models.dart';
import 'player.dart';

class SimParams {
  double rate = 1.5, loss = 0.05, horizon = 300, rRel = 15, margin = 90, bg = 0.3;
  int seed = 3;
  Map<String, double> get scen => {'rate': rate, 'H': horizon, 'r_rel': rRel, 'r_alert': (rRel * 0.55).roundToDouble().clamp(3, 30).toDouble(), 'margin': margin};
  Map<String, double> get channel => {'loss': loss, 'bg': bg};
}

class AppState extends ChangeNotifier {
  final Api api = Api();
  final SimParams params = SimParams();
  List<Map<String, dynamic>> datasets = [];
  int? selectedDataset; // null = synthetic
  Playback? pb;
  Player? player;
  Map<String, dynamic>? summary;
  String? error;
  bool busy = false;
  bool connected = false;

  Future<void> connect() async {
    try {
      await api.health();
      connected = true;
      error = null;
      await refreshDatasets(notify: false);
    } on ApiException catch (e) {
      connected = false;
      error = e.message;
    }
    notifyListeners();
  }

  Future<void> refreshDatasets({bool notify = true}) async {
    try {
      datasets = await api.datasets();
      if (selectedDataset != null && !datasets.any((d) => d['id'] == selectedDataset)) selectedDataset = null;
    } on ApiException catch (e) {
      error = e.message;
    }
    if (notify) notifyListeners();
  }

  void select(int? id) {
    selectedDataset = id;
    notifyListeners();
  }

  Future<void> run() async {
    busy = true;
    error = null;
    notifyListeners();
    try {
      final j = await api.simulate(datasetId: selectedDataset, params: params.scen, channel: params.channel, seed: params.seed);
      final p = Playback.fromJson(Map<String, dynamic>.from(j['playback'] as Map));
      summary = Map<String, dynamic>.from(j['summary'] as Map);
      pb = p;
      if (player == null) {
        player = Player(p);
      } else {
        player!.load(p);
      }
      connected = true;
    } on ApiException catch (e) {
      error = e.message;
    } catch (e) {
      error = 'Could not read the simulation result: $e';
    }
    busy = false;
    notifyListeners();
  }
}
