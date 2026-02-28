from __future__ import annotations
import os
import json
import time
import traceback
from flask import Flask, request, jsonify, send_from_directory, render_template_string

app = Flask(__name__, static_folder=None)

HTML_DIR = os.path.join(os.path.dirname(__file__), 'static')


@app.route('/')
def index():
    html_path = os.path.join(HTML_DIR, 'index.html')
    if os.path.isfile(html_path):
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read()
    return _FALLBACK_HTML


@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory(HTML_DIR, path)


@app.route('/api/deobfuscate', methods=['POST'])
def api_deobfuscate():
    try:
        data = request.get_json(force=True)
        source = data.get('source', '')
        target = data.get('target', 'auto')
        options = data.get('options', {})

        if not source.strip():
            return jsonify({'error': 'No source code provided'}), 400

        if len(source) > 5_000_000:
            return jsonify({'error': 'Source too large (max 5MB)'}), 400

        from .unobfuscator import run_deobfuscation

        result, stats = run_deobfuscation(
            source,
            target=target,
            no_rename=options.get('no_rename', False),
            no_decrypt=options.get('no_decrypt', False),
            no_unwrap=options.get('no_unwrap', False),
            no_junk=options.get('no_junk', False),
            no_simplify=options.get('no_simplify', False),
            no_cf=options.get('no_cf', False),
            op_limit=min(options.get('op_limit', 20_000_000), 50_000_000),
            timeout=min(options.get('timeout', 60.0), 120.0),
        )

        return jsonify({
            'result': result,
            'stats': {
                'total_passes': stats.total_passes,
                'total_changes': stats.total_changes,
                'duration': round(stats.total_duration, 3),
                'detected_obfuscator': stats.detected_obfuscator,
                'original_size': stats.original_size,
                'final_size': stats.final_size,
                'passes': [
                    {
                        'name': pr.name,
                        'success': pr.success,
                        'changes': pr.changes,
                        'duration': round(pr.duration, 3),
                        'error': pr.error,
                    }
                    for pr in stats.pass_results
                ],
            },
        })
    except Exception as e:
        return jsonify({
            'error': f'{type(e).__name__}: {str(e)}',
            'traceback': traceback.format_exc(),
        }), 500


@app.route('/api/detect', methods=['POST'])
def api_detect():
    try:
        data = request.get_json(force=True)
        source = data.get('source', '')

        if not source.strip():
            return jsonify({'error': 'No source code provided'}), 400

        from .core.sandbox import LuaSandbox
        from .unobfuscator import _detect_target

        sandbox = LuaSandbox(op_limit=1_000_000, timeout=5.0)
        detected = _detect_target(source, sandbox)

        return jsonify({
            'detected': detected or 'unknown',
            'source_size': len(source),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


_FALLBACK_HTML = '''<!DOCTYPE html>
<html><head><title>Lua Unobfuscator</title></head>
<body><h1>Lua Unobfuscator</h1>
<p>Static files not found. Place index.html in the static/ directory.</p>
</body></html>'''


def create_app():
    return app


def run_server(host='127.0.0.1', port=5000, debug=False):
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Lua Unobfuscator Web UI')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    run_server(args.host, args.port, args.debug)
