#!/usr/bin/env python3
"""
YouTube Knowledge Extractor - Web App
Uses Apify starvibe/youtube-video-transcript + MiniMax for summarization
Saves notes to Google Drive
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
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

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
        button { width: 100%; padding: 15px; font-size: 16px; background: #ff0000; color: white; border: none; border-radius: 8px; cursor: pointer; margin-bottom: 10px; }
        button:hover { background: #cc0000; }
        button:disabled { background: #666; }
        .secondary { background: #333; }
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
    <button onclick="extractAndSave()" id="btn2" class="secondary">Extract + Save to Drive</button>
    <div id="result"></div>
    <script>
        async function extract() {
            await doExtract(false);
        }
        async function extractAndSave() {
            await doExtract(true);
        }
        async function doExtract(saveToDrive) {
            const url = document.getElementById('url').value;
            const btn = document.getElementById('btn');
            const btn2 = document.getElementById('btn2');
            const result = document.getElementById('result');
            if(!url) return;
            btn.disabled = true;
            btn2.disabled = true;
            btn.textContent = 'Transcribing video...';
            result.innerHTML = '<div class="loading">Using AI to transcribe audio...</div>';
            try {
                const res = await fetch('/extract', { 
                    method: 'POST', 
                    headers: {'Content-Type': 'application/json'}, 
                    body: JSON.stringify({url, save_to_drive: saveToDrive}) 
                });
                const data = await res.json();
                if (data.error) {
                    result.innerHTML = '<div class="error">Error: ' + data.error + '</div>';
                } else {
                    let html = '<div class="success">✅ Extracted!</div><br>';
                    if (data.drive_url) {
                        html += '<div class="success">📁 Saved to Drive: <a href="' + data.drive_url + '" target="_blank" style="color:#4dabf7">' + data.drive_url + '</a></div><br>';
                    }
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
            btn2.disabled = false;
            btn.textContent = 'Extract Knowledge';
            btn2.textContent = 'Extract + Save to Drive';
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
    """Get transcript using starvibe/youtube-video-transcript actor."""
    if not APIFY_TOKEN:
        return None, "APIFY_TOKEN not configured"
    
    try:
        actor_url = "https://api.apify.com/v2/acts/starvibe~youtube-video-transcript/runs"
        data = json.dumps({
            "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
            "language": "en",
            "include_transcript_text": True
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
        
        for _ in range(45):
            time.sleep(2)
            status_url = f"https://api.apify.com/v2/acts/starvibe~youtube-video-transcript/runs/{execution_id}"
            req = urllib.request.Request(status_url, headers={"Authorization": f"Bearer {APIFY_TOKEN}"})
            with urllib.request.urlopen(req) as resp:
                status_data = json.loads(resp.read())
                status = status_data.get('data', {}).get('status')
                
                if status == 'SUCCEEDED':
                    dataset_id = status_data.get('data', {}).get('defaultDatasetId')
                    break
                elif status in ['FAILED', 'ABORTED']:
                    return None, f"Apify failed: {status}"
        else:
            return None, "Transcription timed out"
        
        dataset_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
        req = urllib.request.Request(dataset_url, headers={"Authorization": f"Bearer {APIFY_TOKEN}"})
        with urllib.request.urlopen(req) as resp:
            items = json.loads(resp.read())
        
        if items:
            item = items[0]
            transcript = item.get('transcript_text') or item.get('transcript')
            if transcript:
                if isinstance(transcript, list):
                    text = " ".join([t.get('text', '') for t in transcript])
                    return text, "Apify AI Transcription"
                return transcript, "Apify AI Transcription"
        
        return None, "No transcript in response"
        
    except Exception as e:
        return None, f"Apify error: {str(e)[:80]}"


def get_video_title(video_id):
    """Get video title."""
    try:
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


def save_to_drive(summary, video_id, title):
    """Save notes to Google Drive."""
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        return None
    
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaInMemoryUpload
        
        creds_data = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        
        # Get access token
        scopes = ['https://www.googleapis.com/auth/drive.file']
        credentials = service_account.Credentials.from_service_account_info(creds_data, scopes=scopes)
        
        drive_service = build('drive', 'v3', credentials=credentials)
        
        # Find or create "Youtube Summary" folder
        folder_name = "Youtube Summary"
        response = drive_service.files().list(
            q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'",
            fields="files(id)"
        ).execute()
        
        if response.get('files'):
            folder_id = response['files'][0]['id']
        else:
            # Create folder
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = drive_service.files().create(body=file_metadata, fields='id').execute()
            folder_id = folder.get('id')
        
        # Create file content
        content = f"""# 📺 {summary.get('title', title)}

## ⏱️ Duration
{summary.get('duration_estimate', 'Unknown')}

## 💡 Key Insights
{chr(10).join(['- ' + i for i in summary.get('key_insights', [])])}

## 🎯 Actionable Ideas
{chr(10).join(['- ' + i for i in summary.get('actionable_ideas', [])])}

## 💬 Best Quote
> {summary.get('best_quote', 'N/A')}

---
*Generated by YouTube Knowledge Extractor*
*Video ID: {video_id}*
"""
        
        # Clean filename
        safe_title = re.sub(r'[^\w\s-]', '', title)[:50].strip()
        filename = f"YouTube Notes - {safe_title}.md"
        
        file_metadata = {
            'name': filename,
            'mimeType': 'text/markdown',
            'parents': [folder_id]
        }
        media = MediaInMemoryUpload(content.encode(), mimetype='text/markdown')
        
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id,webViewLink').execute()
        
        return file.get('webViewLink')
        
    except Exception as e:
        print(f"Drive save error: {e}")
        return None


@app.route('/')
def home():
    return render_template_string(HTML)


@app.route('/extract', methods=['POST'])
def extract():
    data = request.json
    url = data.get('url', '')
    save_to_drive_flag = data.get('save_to_drive', False)
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL"}), 400
    
    title = get_video_title(video_id)
    
    # Get transcript via Apify AI transcription
    transcript, method = get_transcript_apify(video_id)
    
    if not transcript:
        return jsonify({
            "error": f"Transcription failed. {method}",
            "title": title,
            "video_id": video_id
        }), 200
    
    # Summarize with MiniMax
    summary = summarize_with_minimax(video_id, transcript, title)
    summary['video_id'] = video_id
    summary['transcript_method'] = method
    
    # Save to Drive if requested
    drive_url = None
    if save_to_drive_flag:
        drive_url = save_to_drive(summary, video_id, title)
        summary['drive_url'] = drive_url
    
    return jsonify(summary)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)