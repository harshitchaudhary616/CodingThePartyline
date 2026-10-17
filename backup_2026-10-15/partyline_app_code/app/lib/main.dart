import 'package:flutter/material.dart';
import 'state.dart';
import 'theme.dart';
import 'screens/sim_screen.dart';
import 'screens/data_screen.dart';
import 'screens/results_screen.dart';
import 'screens/method_screen.dart';

void main() => runApp(const PartyLineApp());

class PartyLineApp extends StatelessWidget {
  const PartyLineApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Party Line Lab',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(Brightness.light),
        darkTheme: buildTheme(Brightness.dark),
        themeMode: ThemeMode.system,
        home: const Shell(),
      );
}

class Shell extends StatefulWidget {
  const Shell({super.key});
  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  final AppState app = AppState();
  int tab = 0;

  @override
  void initState() {
    super.initState();
    app.connect().then((_) {
      if (app.connected) app.run();
    });
  }

  @override
  void dispose() {
    app.player?.dispose();
    app.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pages = [SimScreen(app: app), DataScreen(app: app, onSimulate: () {
      setState(() => tab = 0);
      app.run();
    }), ResultsScreen(app: app), const MethodScreen()];
    return Scaffold(
      appBar: AppBar(
        title: const Text('Party Line Lab', style: TextStyle(fontWeight: FontWeight.w700)),
        actions: [
          ListenableBuilder(
            listenable: app,
            builder: (c, _) => Padding(
              padding: const EdgeInsets.only(right: 14),
              child: Icon(app.connected ? Icons.cloud_done_outlined : Icons.cloud_off_outlined, color: app.connected ? Pal.of(c).good : Pal.of(c).bad),
            ),
          ),
        ],
      ),
      body: SafeArea(child: IndexedStack(index: tab, children: pages)),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.radar), label: 'Simulator'),
          NavigationDestination(icon: Icon(Icons.storage_outlined), label: 'Data'),
          NavigationDestination(icon: Icon(Icons.bar_chart), label: 'Results'),
          NavigationDestination(icon: Icon(Icons.info_outline), label: 'Method'),
        ],
      ),
    );
  }
}
