import re
import hashlib
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ==================== VIDEO ID GENERATION ====================

def generate_video_id(message_id, database):
    """Generate unique video ID"""
    try:
        timestamp = int(datetime.now().timestamp())
        raw = f"{database}_{message_id}_{timestamp}"
        hash_obj = hashlib.md5(raw.encode())
        short_hash = hash_obj.hexdigest()[:8]
        return f"vid_{short_hash}"
    except Exception as e:
        logger.error(f"Error generating video ID: {e}")
        return f"vid_{message_id}"

# ==================== CATEGORY DETECTION ====================

def detect_category(text):
    """Auto-detect video category from text"""
    try:
        if not text:
            return 'movie'
        
        text_lower = str(text).lower()
        
        # Adult content detection
        adult_keywords = ['18+', 'adult', 'xxx', 'porn', 'sex', 'nsfw', '🔞', 'onlyfans', 'explicit']
        if any(keyword in text_lower for keyword in adult_keywords):
            return 'adult'
        
        # Series detection
        series_patterns = [
            r'[Ss](\d+)[Ee](\d+)',           # S01E01
            r'[Ss]eason\s*(\d+)',            # Season 1
            r'[Ee]pisode\s*(\d+)',           # Episode 1
            r'[Ee]p\s*(\d+)',               # Ep 1
            r'পর্ব\s*(\d+)',                # বাংলা: পর্ব ১
            r'সিজন\s*(\d+)'                 # বাংলা: সিজন ১
        ]
        
        for pattern in series_patterns:
            if re.search(pattern, text_lower):
                return 'series'
        
        # Movie by default
        return 'movie'
        
    except Exception as e:
        logger.error(f"Error detecting category: {e}")
        return 'movie'

# ==================== EPISODE INFO EXTRACTION ====================

def extract_episode_info(text):
    """Extract season and episode numbers from text"""
    try:
        if not text:
            return None, None
        
        text_str = str(text)
        
        # Pattern 1: S01E01 format
        match = re.search(r'[Ss](\d+)[Ee](\d+)', text_str)
        if match:
            season = int(match.group(1))
            episode = int(match.group(2))
            return season, episode
        
        # Pattern 2: Season 1 Episode 2
        match = re.search(r'[Ss]eason\s*(\d+).*?[Ee]pisode\s*(\d+)', text_str, re.IGNORECASE)
        if match:
            season = int(match.group(1))
            episode = int(match.group(2))
            return season, episode
        
        # Pattern 3: বাংলা: সিজন ১ পর্ব ২
        match = re.search(r'সিজন\s*(\d+).*?পর্ব\s*(\d+)', text_str)
        if match:
            season = int(match.group(1))
            episode = int(match.group(2))
            return season, episode
        
        return None, None
        
    except Exception as e:
        logger.error(f"Error extracting episode info: {e}")
        return None, None

# ==================== FILE SIZE FORMATTING ====================

def format_file_size(size_bytes):
    """Format file size in human-readable format"""
    try:
        if not size_bytes:
            return "Unknown"
        
        size_bytes = int(size_bytes)
        
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    except:
        return "Unknown"

# ==================== DURATION FORMATTING ====================

def format_duration(seconds):
    """Format duration in HH:MM:SS"""
    try:
        if not seconds:
            return "Unknown"
        
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    except:
        return "Unknown"

# ==================== GOOGLE SHEET CODE GENERATION ====================

def generate_sheet_code(video_data):
    """Generate Google Sheet code for video"""
    try:
        video_id = video_data.get('video_id', 'unknown')
        title = video_data.get('title', 'Untitled')
        season = video_data.get('season')
        episode = video_data.get('episode')
        
        # For series with episode info
        if season and episode:
            label = f"S{season:02d}E{episode:02d}"
        else:
            # Extract from title if available
            match = re.search(r'[Ee]p?\.?\s*(\d+)', str(title))
            if match:
                ep_num = match.group(1)
                label = f"Ep {ep_num}"
            else:
                label = "Full"
        
        return f"{label}:{video_id}"
    except Exception as e:
        logger.error(f"Error generating sheet code: {e}")
        return f"Full:vid_error"

# ==================== MARKDOWN ESCAPE ====================

def escape_markdown(text):
    """Escape markdown special characters"""
    try:
        if not text:
            return ""
        
        text = str(text)
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text
    except:
        return str(text)

# ==================== TIME FORMATTING ====================

def format_time_ago(dt):
    """Format datetime as 'time ago' string"""
    try:
        if not dt:
            return "Unknown"
        
        now = datetime.now()
        diff = now - dt
        
        seconds = diff.total_seconds()
        
        if seconds < 60:
            return "Just now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} min ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} hours ago"
        elif seconds < 604800:
            days = int(seconds / 86400)
            return f"{days} days ago"
        else:
            return dt.strftime("%d %b %Y")
    except:
        return "Unknown"

# ==================== CATEGORY EMOJI ====================

def get_category_emoji(category):
    """Get emoji for category"""
    emoji_map = {
        'adult': '🔞',
        'movie': '🎬',
        'series': '📺',
        'other': '📹'
    }
    return emoji_map.get(category, '📹')

# ==================== RATE LIMITER ====================

class RateLimiter:
    """Simple rate limiter"""
    def __init__(self, max_requests=20, time_window=60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = {}
    
    def is_allowed(self, user_id):
        """Check if user is allowed to make request"""
        try:
            now = datetime.now()
            
            if user_id not in self.requests:
                self.requests[user_id] = []
            
            # Clean old requests
            self.requests[user_id] = [
                req_time for req_time in self.requests[user_id]
                if (now - req_time).total_seconds() < self.time_window
            ]
            
            # Check limit
            if len(self.requests[user_id]) >= self.max_requests:
                return False
            
            # Add new request
            self.requests[user_id].append(now)
            return True
        except:
            return True

# ==================== GREETING ====================

def get_greeting():
    """Get time-based greeting"""
    hour = datetime.now().hour
    
    if 5 <= hour < 12:
        return "সুপ্রভাত! 🌅"
    elif 12 <= hour < 17:
        return "শুভ অপরাহ্ন! ☀️"
    elif 17 <= hour < 21:
        return "শুভ সন্ধ্যা! 🌆"
    else:
        return "শুভ রাত্রি! 🌙"

# ==================== OTHER UTILITIES ====================

def clean_filename(filename):
    """Clean filename for safe storage"""
    try:
        if not filename:
            return "untitled"
        
        filename = str(filename)
        # Remove special characters
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Replace spaces with underscores
        filename = filename.replace(' ', '_')
        # Limit length
        if len(filename) > 100:
            filename = filename[:100]
        
        return filename
    except:
        return "video"

def extract_video_title(caption, filename):
    """Extract clean video title from caption or filename"""
    try:
        # Try caption first
        if caption:
            caption = str(caption)
            # Remove markdown, hashtags, etc.
            title = re.sub(r'[#@]', '', caption)
            # Take first line
            title = title.split('\n')[0].strip()
            if title and len(title) > 3:
                return title[:200]
        
        # Fallback to filename
        if filename:
            filename = str(filename)
            # Remove extension
            title = re.sub(r'\.[^.]+$', '', filename)
            # Clean up
            title = title.replace('_', ' ').replace('-', ' ')
            return title[:200]
        
        return "Untitled"
    except:
        return "Video"

def validate_channel_id(channel_id):
    """Validate Telegram channel ID format"""
    try:
        channel_id = int(channel_id)
        # Telegram channel IDs are negative
        return channel_id < 0
    except:
        return False

def generate_batch_sheet_codes(videos):
    """Generate sheet codes for multiple videos"""
    try:
        if not videos:
            return ""
        
        codes = []
        for video in sorted(videos, key=lambda x: (x.get('season', 0), x.get('episode', 0))):
            code = generate_sheet_code(video)
            codes.append(code)
        
        return ",".join(codes)
    except:
        return ""

# Create global rate limiter instance
rate_limiter = RateLimiter()

logger.info("✅ Utils loaded successfully!")
