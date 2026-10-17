import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiException implements Exception {
  final String message;
  final int? status;
  ApiException(this.message, [this.status]);
  @override
  String toString() => message;
}

class Api {
  String baseUrl;
  String apiKey;
  final Duration timeout;
  Api({this.baseUrl = 'http://10.0.2.2:8000', this.apiKey = '', this.timeout = const Duration(seconds: 90)});

  Uri _u(String path, [Map<String, String>? q]) {
    final b = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
    return Uri.parse('$b$path').replace(queryParameters: q);
  }

  Map<String, String> get _h => {
        'Content-Type': 'application/json',
        if (apiKey.isNotEmpty) 'X-API-Key': apiKey,
      };

  dynamic _decode(http.Response r) {
    dynamic body;
    try {
      body = r.body.isEmpty ? null : jsonDecode(utf8.decode(r.bodyBytes));
    } catch (_) {
      throw ApiException('Server sent an unreadable response (HTTP ${r.statusCode})', r.statusCode);
    }
    if (r.statusCode >= 200 && r.statusCode < 300) return body;
    final msg = (body is Map && body['error'] != null) ? body['error'].toString() : 'HTTP ${r.statusCode}';
    throw ApiException(msg, r.statusCode);
  }

  Future<dynamic> _run(Future<http.Response> Function() f) async {
    try {
      return _decode(await f().timeout(timeout));
    } on TimeoutException {
      throw ApiException('The server took too long to answer. Check the address and try again.');
    } on ApiException {
      rethrow;
    } catch (e) {
      throw ApiException('Cannot reach the server at $baseUrl. Is the backend running? ($e)');
    }
  }

  Future<Map<String, dynamic>> health() async => Map<String, dynamic>.from(await _run(() => http.get(_u('/api/health'), headers: _h)));
  Future<List<Map<String, dynamic>>> datasets() async =>
      (await _run(() => http.get(_u('/api/datasets'), headers: _h)) as List).map((e) => Map<String, dynamic>.from(e as Map)).toList();
  Future<Map<String, dynamic>> createDemo() async => Map<String, dynamic>.from(await _run(() => http.post(_u('/api/datasets/demo'), headers: _h)));
  Future<void> deleteDataset(int id) async => _run(() => http.delete(_u('/api/datasets/$id'), headers: _h));

  Future<Map<String, dynamic>> uploadText(String name, String text, {bool real = true}) async => Map<String, dynamic>.from(await _run(
      () => http.post(_u('/api/datasets/upload', {'name': name, 'real': real ? '1' : '0'}), headers: {..._h, 'Content-Type': 'text/csv'}, body: text)));

  Future<Map<String, dynamic>> record(List<double> bbox, double minutes, double every, String name) async =>
      Map<String, dynamic>.from(await _run(() => http.post(_u('/api/datasets/opensky'),
          headers: _h, body: jsonEncode({'bbox': bbox, 'minutes': minutes, 'every': every, 'name': name}))));

  Future<Map<String, dynamic>> job(int id) async => Map<String, dynamic>.from(await _run(() => http.get(_u('/api/jobs/$id'), headers: _h)));

  Future<Map<String, dynamic>> simulate({int? datasetId, required Map<String, double> params, required Map<String, double> channel, int seed = 3}) async =>
      Map<String, dynamic>.from(await _run(() => http.post(_u('/api/simulate'),
          headers: _h, body: jsonEncode({if (datasetId != null) 'dataset_id': datasetId, 'params': params, 'channel': channel, 'seed': seed}))));

  Future<Map<String, dynamic>> results() async => Map<String, dynamic>.from(await _run(() => http.get(_u('/api/results'), headers: _h)));
}
