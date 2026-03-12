#!/usr/bin/env python3
"""
YouTube Knowledge Extractor - Web App
Uses direct APIs + MiniMax for cheap summarization
"""

import os
import json
import re
import http.client
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
            btn.textContent = 'Extracting...';
            result.innerHTML = '<div class="loading">Fetching transcript...</div>';
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


def get_transcript_youtube_api(video_id):
    """Try YouTube's native caption API."""
    try:
        conn = http.client.HTTPSConnection("www.youtube.com")
        conn.request("GET", f"/api/timedtext?lang=en&v={video_id}", headers={"User-Agent": "Mozilla/5.0"})
        response = conn.getresponse()
        if response.status == 200:
            data = response.read().decode('utf-8')
            if data and len(data) > 20:
                text = re.sub(r'<[^>]+>', ' ', data)
                text = re.sub(r'\s+', ' ', text).strip()
                if len(text) > 50:
                    return text, "YouTube Captions"
        return None, None
    except Exception as e:
        return None, None


def get_transcript_invidious(video_id):
    """Try Invidious API for captions."""
    invidious_instances = ["invidious.snopyta.org", "invidious.kavin.rocks", "invidious.fdn.fr", "yewtu.be"]
    
    for instance in invidious_instances:
        try:
            conn = http.client.HTTPSConnection(instance)
            conn.request("GET", f"/api/v1/videos/{video_id}")
            response = conn.getresponse()
            if response.status == 200:
                data = json.loads(response.read())
                captions = data.get('captions', [])
                for cap in captions:
                    if cap.get('languageCode') == 'en':
                        label = cap.get('label', '')
                        conn.request("GET", f"/api/v1/captions/{video_id}?lang=en")
                        resp2 = conn.getresponse()
                        if resp2.status == 200:
                            import base64
                            try:
                                raw = base64.b64decode(resp2.read())
                                import zlib
                                text = zlib.decompress(raw, 16 + zlib.MAX_WBITS).decode('utf-8')
                                texts = re.findall(r'<text[^>]*>([^<]+)</text>', text)
                                if texts:
                                    return " ".join(texts), f"Invidious ({instance})"
                            except:
                                pass
        except:
            continue
    
    return None, None


def get_video_info(video_id):
    """Get video title and description."""
    try:
        # Try oEmbed
        conn = http.client.HTTPSConnection("noembed.com")
        conn.request("POST", "/1/embed", json.dumps({"url": f"https://www.youtube.com/watch?v={video_id}"}))
        response = conn.getresponse()
        if response.status == 200:
            return json.loads(response.read())
    except:
        pass
    return {}


def search_video_info(title):
    """Search for video content using MiniMax."""
    if not OPENROUTER_API_KEY:
        return None
    
    prompt = f"""Search for information about this YouTube video based on the title:

Title: {title}

Provide a brief summary of what this video is likely about (2-3 sentences)."""

    try:
        conn = http.client.HTTPSConnection("openrouter.ai")
        conn.request("POST", "https://openrouter.ai/api/v1/chat/completions",
            json.dumps({
                "model": "minimax/minimax-m2.1",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500
            }),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENROUTER_API_KEY}"
            }
        )
        response = conn.getresponse()
        data = json.loads(response.read().decode())
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except:
        return None


def summarize_with_minimax(video_id, content, title=""):
    """Use MiniMax (cheap!) to summarize."""
    if not OPENROUTER_API_KEY:
        return {"error": "OPENROUTER_API_KEY not configured"}
    
    if len(content) > 6000:
        content = content[-6000:]
    
    prompt = f"""Analyze this YouTube video content and create structured notes.

Video Title: {title}

Content:
{content}

Create a JSON with:
{{
  "title": "Video title",
  "duration_estimate": "X minutes", 
  "key_insights": ["3-5 insights"],
  "actionable_ideas": ["3-5 actionable takeaways"],
  "best_quote": "best quote"
}}

Return ONLY valid JSON."""

    try:
        conn = http.client.HTTPSConnection("openrouter.ai")
        conn.request("POST", "https://openrouter.ai/api/v1/chat/completions",
            json.dumps({
                "model": "minimax/minimax-m2.1",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1500
            }),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://youtube-knowledge-extractor.vercel.app",
                "X-Title": "YouTube Knowledge Extractor"
            }
        )
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
    
    # Get video info
    video_info = get_video_info(video_id)
    title = video_info.get('title', 'YouTube Video')
    description = video_info.get('description', '')
    
    # Try to get transcript
    transcript, method = get_transcript_youtube_api(video_id)
    
    if not transcript:
        transcript, method = get_transcript_invidious(video_id)
    
    if transcript:
        # Summarize transcript with MiniMax
        summary = summarize_with_minimax(video_id, transcript, title)
        summary['video_id'] = video_id
        summary['transcript_method'] = method
        return jsonify(summary)
    
    # Fallback: use description or search
    if description and len(description) > 100:
        summary = summarize_with_minimax(video_id, description, title)
        summary['video_id'] = video_id
        summary['transcript_method'] = "Video description"
        return jsonify(summary)
    
    # Try web search for info
    search_result = search_video_info(title)
    if search_result:
        summary = summarize_with_minimax(video_id, search_result, title)
        summary['video_id'] = video_id
        summary['transcript_method'] = "Web search"
        return jsonify(summary)
    
    return jsonify({
        "error": "No captions available. Try a video with English subtitles enabled.",
        "title": title,
        "video_id": video_id
    }), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)