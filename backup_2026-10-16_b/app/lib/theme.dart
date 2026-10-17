import 'dart:ui' show FontFeature;
import 'package:flutter/material.dart';

class Pal {
  final Color bg, panel, ink, muted, line, chip, scope, scopeInk, scopeDim, scopeLine, uni, bc, cod, bad, good;
  const Pal._(this.bg, this.panel, this.ink, this.muted, this.line, this.chip, this.scope, this.scopeInk, this.scopeDim, this.scopeLine, this.uni, this.bc, this.cod, this.bad, this.good);

  static const light = Pal._(Color(0xFFE9EDF1), Color(0xFFFFFFFF), Color(0xFF13202B), Color(0xFF566676), Color(0xFFD3DBE2), Color(0xFFEEF2F5),
      Color(0xFF0D1A24), Color(0xFFBCD0DE), Color(0xFF3A5568), Color(0xFF1B3142), Color(0xFFC27A00), Color(0xFF4A6FA5), Color(0xFF00846F), Color(0xFFC43D3D), Color(0xFF2F8F4E));
  static const dark = Pal._(Color(0xFF0A1218), Color(0xFF111D27), Color(0xFFE3ECF3), Color(0xFF8BA0B1), Color(0xFF223441), Color(0xFF172733),
      Color(0xFF070F15), Color(0xFFBCD0DE), Color(0xFF3A5568), Color(0xFF15283A), Color(0xFFF2B035), Color(0xFF8FB0E0), Color(0xFF2FD4B8), Color(0xFFFF7070), Color(0xFF5FD48A));

  static Pal of(BuildContext c) => Theme.of(c).brightness == Brightness.dark ? dark : light;
  Color scheme(String s) => s == 'unicast' ? uni : s == 'broadcast' ? bc : cod;
}

ThemeData buildTheme(Brightness b) {
  final p = b == Brightness.dark ? Pal.dark : Pal.light;
  return ThemeData(
    brightness: b,
    useMaterial3: true,
    scaffoldBackgroundColor: p.bg,
    colorScheme: ColorScheme.fromSeed(seedColor: p.cod, brightness: b).copyWith(surface: p.panel),
    navigationBarTheme: NavigationBarThemeData(backgroundColor: p.panel, indicatorColor: p.cod.withOpacity(0.18)),
    appBarTheme: AppBarTheme(backgroundColor: p.bg, foregroundColor: p.ink, elevation: 0, centerTitle: false),
  );
}

TextStyle mono(Color c, [double s = 12]) => TextStyle(fontFamily: 'monospace', fontSize: s, color: c, fontFeatures: const [FontFeature.tabularFigures()]);


/// Bordered panel used instead of Card so it works the same across Flutter versions.
class Panel extends StatelessWidget {
  final Widget child;
  final EdgeInsets padding;
  final Color? border;
  const Panel({super.key, required this.child, this.padding = const EdgeInsets.all(14), this.border});
  @override
  Widget build(BuildContext context) {
    final p = Pal.of(context);
    return Container(
      padding: padding,
      decoration: BoxDecoration(color: p.panel, borderRadius: BorderRadius.circular(6), border: Border.all(color: border ?? p.line, width: border == null ? 1 : 1.6)),
      child: child,
    );
  }
}

class SectionTitle extends StatelessWidget {
  final String text;
  const SectionTitle(this.text, {super.key});
  @override
  Widget build(BuildContext context) =>
      Text(text.toUpperCase(), style: TextStyle(fontSize: 13, letterSpacing: 1.1, fontWeight: FontWeight.w700, color: Pal.of(context).muted));
}
