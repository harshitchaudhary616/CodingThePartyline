import 'package:flutter/material.dart';
import '../theme.dart';

class MethodScreen extends StatelessWidget {
  const MethodScreen({super.key});
  @override
  Widget build(BuildContext context) {
    final pal = Pal.of(context);
    Widget block(String title, List<String> items) => Panel(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SectionTitle(title),
            const SizedBox(height: 8),
            for (final t in items) Padding(padding: const EdgeInsets.only(bottom: 6), child: Text('• $t', style: TextStyle(color: pal.ink, height: 1.4))),
          ]),
        );
    return ListView(padding: const EdgeInsets.all(14), children: [
      block('The model', [
        'Each aircraft holds its own clearance (sent by the usual addressed message) plus every clearance it has decoded since.',
        'A clearance is relevant to another aircraft when their predicted paths pass within the relevance radius inside the look-ahead horizon.',
        'Each aircraft-clearance pair has a deadline: predicted loss of separation minus processing, crew response and manoeuvre time.',
        'A transmission is the XOR of equal-length messages. An aircraft decodes message m only if it already holds every other message in the set.',
        'All schemes see identical scenarios, channel and information. Only transmission choice differs.',
        'ADS-B is used to decide relevance only, never as decoding side information.',
      ]),
      const SizedBox(height: 12),
      block('What the data is', [
        'Real mode: aircraft paths recorded from OpenSky Network by the backend. Clearances are simulated because no public dataset contains them.',
        'Synthetic mode: a built-in sector generator. It is always labelled synthetic in the app.',
      ]),
      const SizedBox(height: 12),
      block('Decision for the paper', [
        'Not supported: "Coding substantially reduces datalink load versus broadcast."',
        'Supported: addressed messaging cannot sustain party-line coverage; broadcast restores it at a fraction of the load.',
        'Lead: the coding gain grows with load and loss (3.4% fewer transmissions and 3.5 points fewer misses at 3 arrivals/min and 30% loss). Richer side information is the main open experiment.',
      ]),
      const SizedBox(height: 24),
    ]);
  }
}
