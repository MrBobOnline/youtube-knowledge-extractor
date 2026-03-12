#!/usr/bin/env python3
"""
YouTube Knowledge Extractor - Web App
Turn YouTube videos into structured notes using MiniMax (cheap!)
"""

import os
import json
import re
from flask import Flask, request, render_template_string, jsonify

app = Flask(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>YouTube Knowledge Extractor</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; background: #0f0f0f; color: #fff; }
        h1 { text-align: center; color: #ff0000; }
        input { width: 100%; padding: 15px; font-size: 16px; border: none; border-radius: 8px; margin-bottom: 15px; background: #222; color: #fff; }
        button { width: 100%; padding: 15px; font-size: 16px; background: #ff0000; color: white; border: none; border-radius: 8px; cursor: pointer; }
        button:hover { background: #cc0000; }
        button:disabled { background: #666; }
        #result { background: #1a1a1a; padding: 20px; border-radius: 8px; margin-top: 20px; white-space: pre-wrap; overflow-x: auto; max-height: 600px; }
        .loading { text-align: center; color: #888; }
        .error { color: #ff6b6b; }
        .success { color: #51cf66; }
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
            result.innerHTML = '<div class="loading">Getting transcript + summarizing...</div>';
            try {
                const res = await fetch('/extract', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url}) });
                const data = await res.json();
                if (data.error) {
                    result.innerHTML = '<div class="error">Error: ' + data.error + '</div>';
                } else {
                    let html = '<div class="success">✅ Extracted!</div><br>';
                    html += '<strong>📺 ' + (data.title || 'Unknown') + '</strong><br><br>';
                    if (data.transcript_method) {
                        html += '<div style="background:#1a3a1a;padding:8px;border-radius:5px;margin-bottom:10px;font-size:12px;">📝 Transcript: ' + data.transcript_method + '</div>';
                    }
                    html += '<strong>⏱️ Duration:</strong> ' + (data.duration_estimate || 'Unknown') + '<br><br>';
                    html += '<strong>💡 Key Insights:</strong><ul>';
                    (data.key_insights || []).forEach(i => html += '<li>' + i + '</li>');
                    html += '</ul><strong>🎯 Actionable Ideas:</strong><ul>';
                    (data.actionable_ideas || []).forEach(i => html += '<li>' + i + '</li>');
                    html += '</ul>';
                    if (data.best_quote) {
                        html += '<strong>💬 Best Quote:</strong><br><em>"' + data.best_quote + '"</em>';
                    }
                    result.innerHTML = html;
                }
            } catch(e) { result.innerHTML = '<div class="error">Error: ' + e + '</div>'; }
            btn.disabled = false;
            btn.textContent = 'Extract Knowledge';
        }
    </script>
</body>
</html>
'''


def extract_video_id(url):
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'youtu\.be\/([0-9A-Za-z_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_transcript(video_id):
    """Try multiple methods to get transcript."""
    import sys
    import subprocess
    
    # Try using youtube-transcript-api
    try:
        result = subprocess.run(
            [sys.executable, '-c', f'''
from youtube_transcript_api import YouTubeTranscriptApi
transcript = YouTubeTranscriptApi.get_transcript("{video_id}", languages=["en"])
text = " ".join([t["text"] for t in transcript])
print(text)
'''],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and len(result.stdout) > 50:
            return result.stdout.strip(), "YouTube Transcript API"
    except Exception as e:
        print(f"youtube-transcript-api failed: {e}")
    
    # Fallback: try Invidious API
    try:
        import http.client
        conn = http.client.HTTPSConnection("invidious.fdn.fr")
        conn.request("GET", f"/api/v1/videos/{video_id}")
        response = conn.getresponse()
        if response.status == 200:
            data = json.loads(response.read())
            captions = data.get('captions', [])
            for cap in captions:
                if cap.get('languageCode') == 'en':
                    # Get caption track
                    conn2 = http.client.HTTPSConnection("invidious.fdn.fr")
                    conn2.request("GET", f"/api/v1/captions/{video_id}?label=English")
                    resp2 = conn2.getresponse()
                    if resp2.status == 200:
                        import base64
                        import zlib
                        try:
                            raw = base64.b64decode(resp2.read())
                            text = zlib.decompress(raw, 16 + zlib.MAX_WBITS).decode('utf-8')
                            # Extract text from TTML
                            import re
                            texts = re.findall(r'<text[^>]*>([^<]+)</text>', text)
                            if texts:
                                return " ".join(texts), "Invidious Captions"
                        except:
                            pass
    except Exception as e:
        print(f"Invidious failed: {e}")
    
    return None, None


def get_video_title(video_id):
    """Get video title."""
    try:
        import http.client
        conn = http.client.HTTPSConnection("noembed.com")
        conn.request("POST", "/1/embed", json.dumps({"url": f"https://www.youtube.com/watch?v={video_id}"}))
        response = conn.getresponse()
        if response.status == 200:
            info = json.loads(response.read())
            return info.get('title', 'YouTube Video')
    except:
        pass
    return 'YouTube Video'


def summarize_with_minimax(video_id, transcript, title=""):
    """Use MiniMax (cheap!) to summarize."""
    if not OPENROUTER_API_KEY:
        return {"error": "OPENROUTER_API_KEY not configured"}
    
    # Truncate if too long
    if len(transcript) > 6000:
        transcript = transcript[-6000:]
    
    prompt = f"""Analyze this YouTube video transcript and create structured notes.

Video Title: {title}

Transcript:
{transcript}

Create a JSON with:
{{
  "title": "Video title",
  "duration_estimate": "X minutes", 
  "key_insights": ["3-5 insights"],
  "actionable_ideas": ["3-5 actionable takeaways"],
  "best_quote": "best quote"
}}

Return ONLY valid JSON."""

    import http.client
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": "minimax/minimax-m2.1",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://youtube-knowledge-extractor.vercel.app",
        "X-Title": "YouTube Knowledge Extractor"
    }
    
    try:
        conn = http.client.HTTPSConnection("openrouter.ai")
        conn.request("POST", url, json.dumps(payload), headers)
        response = conn.getresponse()
        data = json.loads(response.read().decode())
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"raw": content}
    except Exception as e:
        return {"error": str(e)}


@app.route('/')
def home():
    return render_template_string(HTML)


@app.route('/extract', methods=['POST'])
def extract():
    data = request.json
    url = data.get('url', '')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    title = get_video_title(video_id)
    
    # Get transcript
    transcript, method = get_transcript(video_id)
    
    if not transcript:
        return jsonify({
            "error": "No captions available for this video. Try a video with English subtitles.",
            "title": title,
            "video_id": video_id
        }), 200
    
    # Summarize with MiniMax
    summary = summarize_with_minimax(video_id, transcript, title)
    summary['video_id'] = video_id
    summary['transcript_method'] = method
    
    return jsonify(summary)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
