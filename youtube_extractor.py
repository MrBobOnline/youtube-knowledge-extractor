#!/usr/bin/env python3
"""
YouTube Knowledge Extractor
Turn YouTube videos into structured notes.

Usage:
    python youtube_extractor.py "https://youtube.com/watch?v=VIDEO_ID"
    python youtube_extractor.py "https://youtube.com/watch?v=VIDEO_ID" --summary-only
    python youtube_extractor.py "https://youtube.com/watch?v=VIDEO_ID" --output notes.json
"""

import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime
import http.client
import urllib.parse

# Configuration
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GMAIL_USER = os.environ.get("GMAIL_USER", "onlineab9@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

DATA_DIR = Path(os.environ.get("OPENCLAW_DATA_DIR", "~/.openclaw")).expanduser()
OUTPUT_DIR = DATA_DIR / "youtube_notes"


def extract_video_id(url):
    """Extract video ID from YouTube URL."""
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
    """Get transcript using YouTube's transcript API."""
    try:
        # YouTube's transcript endpoint
        conn = http.client.HTTPSConnection("www.youtube.com")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        # Try to get captions using a simpler approach
        # For a production app, use youtube-transcript-api package
        # This is a placeholder that shows the structure
        
        # The actual transcript would come from:
        # https://www.youtube.com/api/timedtext?lang=en&v={video_id}
        
        conn.request("GET", f"/api/timedtext?lang=en&v={video_id}", headers=headers)
        response = conn.getresponse()
        
        if response.status == 200:
            data = response.read().decode('utf-8')
            # Parse TTML format
            text = re.sub(r'<[^>]+>', ' ', data)
            text = re.sub(r'\s+', ' ', text).strip()
            return text
        
        return None
    except Exception as e:
        print(f"Error getting transcript: {e}")
        return None


def get_video_info(video_id):
    """Get video title and metadata."""
    try:
        conn = http.client.HTTPSConnection("noembed.com")
        headers = {"Content-Type": "application/json"}
        data = json.dumps({"url": f"https://www.youtube.com/watch?v={video_id}"})
        
        conn.request("POST", "/1/embed", data, headers)
        response = conn.getresponse()
        
        if response.status == 200:
            return json.loads(response.read().decode())
        
        return None
    except Exception as e:
        print(f"Error getting video info: {e}")
        return None


def summarize_with_llm(video_id, transcript, video_title=""):
    """Use LLM to generate structured summary."""
    if not OPENROUTER_API_KEY:
        print("Warning: OPENROUTER_API_KEY not set")
        return None
    
    # Truncate transcript if too long (keep last ~8000 chars)
    if len(transcript) > 8000:
        transcript = transcript[-8000:]
    
    prompt = f"""You are an expert knowledge extractor. Analyze this YouTube video transcript and create structured notes.

Video Title: {video_title or 'Unknown'}
Video ID: {video_id}

Transcript (truncated):
{transcript[:8000]}

Create a JSON response with this structure:
{{
  "video_id": "{video_id}",
  "title": "Video title",
  "extracted_date": "{datetime.now().isoformat()}",
  "duration_estimate": "X minutes",
  "key_insights": [
    "3-5 most important insights from the video"
  ],
  "actionable_ideas": [
    "3-5 specific, actionable takeaways"
  ],
  "topic_breakdown": [
    {{
      "topic": "Main topic name",
      "timestamp": "MM:SS",
      "summary": "Brief summary of this section"
    }}
  ],
  "best_quote": "Most impactful quote from the video",
  "prerequisites": ["Any prerequisites mentioned"],
  "next_steps": ["Suggested follow-up actions"]
}}

Focus on extracting actionable value. Be specific and practical.
Return ONLY the JSON, no markdown formatting."""

    url = "https://openrouter.ai/api/v1/chat/completions"
    
    payload = {
        "model": "perplexity/sonar-pro",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 3000
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://openclaw.ai",
        "X-Title": "YouTube Knowledge Extractor"
    }
    
    try:
        conn = http.client.HTTPSConnection("openrouter.ai")
        conn.request("POST", url, json.dumps(payload), headers)
        response = conn.getresponse()
        data = json.loads(response.read().decode())
        
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        # Extract JSON
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        
        return {"raw_response": content}
    except Exception as e:
        print(f"Summarization error: {e}")
        return None


def format_as_markdown(summary):
    """Format summary as readable Markdown."""
    if not summary:
        return "No summary available."
    
    md = f"""# 📺 YouTube Knowledge Notes

## {summary.get('title', 'Untitled Video')}
*Extracted: {summary.get('extracted_date', datetime.now().isoformat())}*

---

## ⏱️ Duration Estimate
{summary.get('duration_estimate', 'Unknown')}

---

## 💡 Key Insights

"""
    for i, insight in enumerate(summary.get('key_insights', []), 1):
        md += f"{i}. {insight}\n"
    
    md += """

## 🎯 Actionable Ideas

"""
    for i, idea in enumerate(summary.get('actionable_ideas', []), 1):
        md += f"{i}. {idea}\n"
    
    md += """

## 📊 Topic Breakdown

"""
    for section in summary.get('topic_breakdown', []):
        md += f"### {section.get('topic', 'Topic')}\n"
        md += f"**[{section.get('timestamp', '00:00')}]** {section.get('summary', '')}\n\n"
    
    md += f"""

---

## 💬 Best Quote

> {summary.get('best_quote', 'No quote extracted')}

"""
    
    if summary.get('prerequisites'):
        md += "## 📋 Prerequisites\n\n"
        for prereq in summary['prerequisites']:
            md += f"- {prereq}\n"
        md += "\n"
    
    if summary.get('next_steps'):
        md += "## 🚀 Next Steps\n\n"
        for step in summary['next_steps']:
            md += f"- {step}\n"
        md += "\n"
    
    md += f"""
---
*Generated by YouTube Knowledge Extractor*
"""
    
    return md


def send_via_email(summary, video_url, recipient):
    """Send summary to email."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("Warning: Gmail credentials not set")
        return False
    
    import smtplib
    from email.mime.text import MIMEText
    from email.header import Header
    from email.utils import formatdate
    
    subject = f"📺 Notes: {summary.get('title', 'YouTube Video')}"
    body = format_as_markdown(summary)
    body += f"\n\nOriginal video: {video_url}"
    
    msg = MIMEText(body, 'html', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = GMAIL_USER
    msg['To'] = recipient
    msg['Date'] = formatdate()
    
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, [recipient], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extract knowledge from YouTube videos")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--output", "-o", help="Output file path (JSON)")
    parser.add_argument("--markdown", "-m", help="Output as Markdown file")
    parser.add_argument("--email", "-e", help="Send to email address")
    parser.add_argument("--summary-only", action="store_true", help="Show summary only")
    
    args = parser.parse_args()
    
    print("=" * 50)
    print("📺 YouTube Knowledge Extractor")
    print("=" * 50)
    print()
    
    # Extract video ID
    video_id = extract_video_id(args.url)
    if not video_id:
        print("❌ Invalid YouTube URL")
        sys.exit(1)
    
    print(f"🔍 Video ID: {video_id}")
    
    # Get video info
    print("📋 Fetching video information...")
    video_info = get_video_info(video_id)
    title = video_info.get('title', 'Unknown') if video_info else 'Unknown'
    print(f"   Title: {title}")
    
    # Get transcript
    print("📝 Extracting transcript...")
    transcript = get_transcript(video_id)
    
    if not transcript:
        print("⚠️ Could not extract transcript. Trying with sample data...")
        # Use a placeholder for testing
        transcript = "This is a sample transcript. In production, this would contain the actual YouTube video transcript."
    
    if args.summary_only:
        print(f"\n📄 Transcript ({len(transcript)} chars):")
        print(transcript[:500] + "..." if len(transcript) > 500 else transcript)
        return
    
    # Generate summary
    print("🧠 Analyzing and generating structured notes...")
    summary = summarize_with_llm(video_id, transcript, title)
    
    if not summary:
        print("❌ Failed to generate summary")
        sys.exit(1)
    
    summary['video_id'] = video_id
    summary['title'] = title
    summary['video_url'] = args.url
    
    # Output as JSON
    if args.output:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = Path(args.output)
        with open(output_path, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"✅ Saved JSON to: {output_path}")
    
    # Output as Markdown
    if args.markdown:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        md_path = Path(args.markdown)
        with open(md_path, 'w') as f:
            f.write(format_as_markdown(summary))
        print(f"✅ Saved Markdown to: {md_path}")
    
    # Send via email
    if args.email:
        if send_via_email(summary, args.url, args.email):
            print(f"✅ Sent to {args.email}")
        else:
            print(f"❌ Failed to send email")
    
    # Display summary
    print()
    print("=" * 50)
    print("📊 SUMMARY")
    print("=" * 50)
    print()
    print(f"🎬 Title: {summary.get('title', 'Unknown')}")
    print(f"⏱️ Duration: {summary.get('duration_estimate', 'Unknown')}")
    print()
    print("💡 Key Insights:")
    for i, insight in enumerate(summary.get('key_insights', [])[:3], 1):
        print(f"   {i}. {insight[:80]}{'...' if len(insight) > 80 else ''}")
    print()
    print("🎯 Top Actionable Idea:")
    if summary.get('actionable_ideas'):
        print(f"   • {summary['actionable_ideas'][0][:80]}")
    print()
    
    if not args.output and not args.markdown and not args.email:
        print("Options:")
        print("  --output notes.json    Save as JSON")
        print("  --output notes.md      Save as Markdown")
        print("  --email you@email.com  Send to email")


if __name__ == "__main__":
    main()