from flask import Flask, request, render_template_string
import subprocess
import json

app = Flask(__name__)

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>YouTube Knowledge Extractor</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; background: #0f0f0f; color: #fff; }
        h1 { text-align: center; color: #ff0000; }
        input { width: 100%; padding: 15px; font-size: 16px; border: none; border-radius: 8px; margin-bottom: 15px; }
        button { width: 100%; padding: 15px; font-size: 16px; background: #ff0000; color: white; border: none; border-radius: 8px; cursor: pointer; }
        button:hover { background: #cc0000; }
        button:disabled { background: #666; }
        #result { background: #1a1a1a; padding: 20px; border-radius: 8px; margin-top: 20px; white-space: pre-wrap; overflow-x: auto; }
        .loading { text-align: center; color: #888; }
    </style>
</head>
<body>
    <h1>📺 YouTube Knowledge Extractor</h1>
    <input type="text" id="url" placeholder="Paste YouTube URL here..." />
    <button onclick="extract()" id="btn">Extract Knowledge</button>
    <div id="result"></div>
    <script>
        async function extract() {
            const url = document.getElementById('url').value;
            const btn = document.getElementById('btn');
            const result = document.getElementById('result');
            if(!url) return;
            btn.disabled = true;
            btn.textContent = 'Extracting... (may take 30s)';
            result.textContent = '';
            try {
                const res = await fetch('/extract', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url}) });
                const data = await res.json();
                result.textContent = JSON.stringify(data, null, 2);
            } catch(e) { result.textContent = 'Error: ' + e; }
            btn.disabled = false;
            btn.textContent = 'Extract Knowledge';
        }
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    return render_template_string(HTML)

@app.route('/extract', methods=['POST'])
def extract():
    data = request.json
    url = data.get('url', '')
    if not url:
        return {'error': 'No URL provided'}, 400
    try:
        result = subprocess.run(['python3', '/data/.openclaw/scripts/youtube_extractor.py', url, '--json'], capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return {'error': result.stderr}, 500
        return json.loads(result.stdout)
    except Exception as e:
        return {'error': str(e)}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
