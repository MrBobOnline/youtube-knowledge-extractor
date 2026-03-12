#!/usr/bin/env python3
"""
YouTube Knowledge Extractor - Web App
Uses Apify for transcripts + MiniMax for cheap summarization
"""

import os
import json
import re
import urllib.request
import urllib.parse
import time
from flask import Flask, request, render_template_string, jsonify

app = Flask(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")

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
            btn.textContent = 'Extracting via Apify...';
            result.innerHTML = '<div class="loading">Fetching transcript from YouTube...</div>';
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


def get_transcript_apify(video_id):
    """Get transcript using Apify YouTube scraper."""
    if not APIFY_TOKEN:
        return None, "APIFY_TOKEN not configured"
    
    try:
        # Start the actor
        actor_url = "https://api.apify.com/v2/acts/triangle~youtube-scraper/runs"
        data = json.dumps({
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "transcripts": True
        }).encode('utf-8')
        
        req = urllib.request.Request(
            actor_url,
            data=data,
            headers={
                "Authorization": f"Bearer {APIFY_TOKEN}",
                "Content-Type": "application/json"
            }
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read())
            execution_id = result.get('data', {}).get('id')
        
        if not execution_id:
            return None, "Failed to start Apify actor"
        
        # Wait for completion (max 60s)
        for _ in range(30):
            time.sleep(2)
            status_url = f"https://api.apify.com/v2/acts/triangle~youtube-scraper/runs/{execution_id}"
            req = urllib.request.Request(status_url, headers={"Authorization": f"Bearer {APIFY_TOKEN}"})
            with urllib.request.urlopen(req) as resp:
                status_data = json.loads(resp.read())
                status = status_data.get('data', {}).get('status')
                
                if status == 'SUCCEEDED':
                    dataset_id = status_data.get('data', {}).get('defaultDatasetId')
                    break
                elif status in ['FAILED', 'ABORTED']:
                    return None, f"Apify actor failed: {status}"
        else:
            return None, "Apify actor timed out"
        
        # Fetch results
        dataset_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
        req = urllib.request.Request(dataset_url, headers={"Authorization": f"Bearer {APIFY_TOKEN}"})
        with urllib.request.urlopen(req) as resp:
            items = json.loads(resp.read())
        
        if items:
            item = items[0]
            # Try transcript
            transcript_data = item.get('transcript') or item.get('captions') or item.get('subtitles')
            if transcript_data:
                if isinstance(transcript_data, list):
                    for t in transcript_data:
                        if t.get('lang') == 'en' or t.get('languageCode') == 'en':
                            return t.get('text', ''), "Apify"
                elif isinstance(transcript_data, str):
                    return transcript_data, "Apify"
            
            # Fallback to description
            description = item.get('description', '')
            if description and len(description) > 100:
                return description, "Apify (description)"
        
        return None, "No transcript found"
        
    except Exception as e:
        return None, f"Apify error: {str(e)[:50]}"


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
    
    if len(transcript) > 6000:
        transcript = transcript[-6000:]
    
    prompt = f"""Analyze this YouTube video content and create structured notes.

Video Title: {title}

Content:
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
    
    # Get transcript via Apify
    transcript, method = get_transcript_apify(video_id)
    
    if not transcript:
        return jsonify({
            "error": f"No captions. {method}. Try another video.",
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
