#!/usr/bin/env python3
"""
YouTube Knowledge Extractor - Web App
Turn YouTube videos into structured notes.
"""

import os
import json
import re
import http.client
from datetime import datetime
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
            result.innerHTML = '<div class="loading">Processing video...</div>';
            try {
                const res = await fetch('/extract', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url}) });
                const data = await res.json();
                if (data.error) {
                    result.innerHTML = '<div class="error">Error: ' + data.error + '</div>';
                } else {
                    let html = '<div class="success">✅ Extracted!</div><br>';
                    html += '<strong>📺 ' + (data.title || 'Unknown') + '</strong><br><br>';
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
    """Get transcript using YouTube's caption API."""
    try:
        conn = http.client.HTTPSConnection("www.youtube.com")
        headers = {"User-Agent": "Mozilla/5.0"}
        conn.request("GET", f"/api/timedtext?lang=en&v={video_id}", headers=headers)
        response = conn.getresponse()
        if response.status == 200:
            data = response.read().decode('utf-8')
            text = re.sub(r'<[^>]+>', ' ', data)
            text = re.sub(r'\s+', ' ', text).strip()
            return text
        return None
    except Exception as e:
        print(f"Transcript error: {e}")
        return None


def get_video_title(video_id):
    """Get video title from oEmbed."""
    try:
        conn = http.client.HTTPSConnection("noembed.com")
        headers = {"Content-Type": "application/json"}
        data = json.dumps({"url": f"https://www.youtube.com/watch?v={video_id}"})
        conn.request("POST", "/1/embed", data, headers)
        response = conn.getresponse()
        if response.status == 200:
            info = json.loads(response.read().decode())
            return info.get('title', 'Unknown')
    except:
        pass
    return 'YouTube Video'


def summarize_with_llm(video_id, transcript, title=""):
    """Use Perplexity Sonar via OpenRouter to generate summary."""
    if not OPENROUTER_API_KEY:
        return {"error": "OPENROUTER_API_KEY not configured"}
    
    if len(transcript) > 8000:
        transcript = transcript[-8000:]
    
    prompt = f"""Analyze this YouTube video transcript and create structured notes.

Video Title: {title}
Video ID: {video_id}

Transcript:
{transcript}

Create a JSON response with this exact structure:
{{
  "title": "Video title",
  "duration_estimate": "X minutes",
  "key_insights": ["insight1", "insight2", "insight3"],
  "actionable_ideas": ["idea1", "idea2", "idea3"],
  "best_quote": "most impactful quote"
}}

Return ONLY valid JSON, no markdown."""

    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": "perplexity/sonar-pro",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000
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
    transcript = get_transcript(video_id)
    
    if not transcript:
        transcript = "This video does not have captions available. Please use a video with English subtitles enabled."
    
    summary = summarize_with_llm(video_id, transcript, title)
    summary['video_id'] = video_id
    
    return jsonify(summary)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
