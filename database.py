from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime, timedelta
import logging
import time
from config import MONGO_URI, DATABASE_NAME

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.videos = None
        self.users = None
        self.settings = None
        self.analytics = None
        self.connect()
    
    def connect(self):
        """Connect to MongoDB with retry logic"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"🔗 Connecting to MongoDB (attempt {attempt + 1}/{max_retries})...")
                
                # Clean URI (remove any whitespace)
                mongo_uri = MONGO_URI.strip()
                if not mongo_uri:
                    raise ValueError("MONGO_URI is empty!")
                
                # Connect with timeout and SSL
                self.client = MongoClient(
                    mongo_uri,
                    serverSelectionTimeoutMS=10000,
                    connectTimeoutMS=10000,
                    socketTimeoutMS=10000,
                    tlsAllowInvalidCertificates=False
                )
                
                # Test connection
                self.client.admin.command('ping')
                
                self.db = self.client[DATABASE_NAME]
                
                # Collections
                self.videos = self.db['videos']
                self.users = self.db['users']
                self.settings = self.db['settings']
                self.analytics = self.db['analytics']
                
                # Create indexes for performance
                self._create_indexes()
                
                # Initialize settings
                self._init_settings()
                
                logger.info("✅ Database connected successfully!")
                return
                
            except Exception as e:
                logger.error(f"❌ MongoDB connection failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error("❌ All connection attempts failed!")
                    raise
    
    def _create_indexes(self):
        """Create database indexes for faster queries"""
        try:
            # Videos indexes
            self.videos.create_index([('video_id', ASCENDING)], unique=True)
            self.videos.create_index([('category', ASCENDING)])
            self.videos.create_index([('database', ASCENDING)])
            self.videos.create_index([('added_at', DESCENDING)])
            self.videos.create_index([('views', DESCENDING)])
            
            # Users indexes
            self.users.create_index([('user_id', ASCENDING)], unique=True)
            self.users.create_index([('joined_at', DESCENDING)])
            self.users.create_index([('last_active', DESCENDING)])
            
            # Analytics indexes
            self.analytics.create_index([('timestamp', DESCENDING)])
            self.analytics.create_index([('video_id', ASCENDING)])
            self.analytics.create_index([('user_id', ASCENDING)])
            
            logger.info("✅ Database indexes created")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")
    
    def _init_settings(self):
        """Initialize default settings"""
        try:
            if not self.settings.find_one({'_id': 'config'}):
                default_settings = {
                    '_id': 'config',
                    'welcome_message': '',
                    'help_message': '',
                    'features': {
                        'maintenance_mode': False,
                        'new_user_registration': True,
                        'broadcast_enabled': True
                    },
                    'stats': {
                        'total_broadcasts': 0,
                        'total_videos_sent': 0
                    }
                }
                self.settings.insert_one(default_settings)
                logger.info("✅ Default settings initialized")
        except Exception as e:
            logger.error(f"Error initializing settings: {e}")
    
    # ==================== VIDEO OPERATIONS ====================
    
    def add_video(self, video_data):
        """Add new video to database"""
        try:
            # Add timestamps
            video_data['added_at'] = datetime.now()
            video_data['last_updated'] = datetime.now()
            
            # Set default values
            video_data['views'] = 0
            video_data['downloads'] = 0
            video_data['status'] = 'active'
            
            # Insert video
            result = self.videos.insert_one(video_data)
            logger.info(f"✅ Video added: {video_data['video_id']}")
            return result.inserted_id
        except Exception as e:
            logger.error(f"Error adding video: {e}")
            return None
    
    def get_video(self, video_id):
        """Get video by ID"""
        try:
            return self.videos.find_one({'video_id': video_id, 'status': 'active'})
        except Exception as e:
            logger.error(f"Error getting video: {e}")
            return None
    
    def get_all_videos(self, category=None, limit=50):
        """Get all videos, optionally filtered by category"""
        try:
            query = {'status': 'active'}
            if category:
                query['category'] = category
            
            return list(self.videos.find(query).sort('added_at', DESCENDING).limit(limit))
        except Exception as e:
            logger.error(f"Error getting videos: {e}")
            return []
    
    def update_video(self, video_id, updates):
        """Update video details"""
        try:
            updates['last_updated'] = datetime.now()
            result = self.videos.update_one(
                {'video_id': video_id},
                {'$set': updates}
            )
            logger.info(f"✅ Video updated: {video_id}")
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating video: {e}")
            return False
    
    def delete_video(self, video_id):
        """Soft delete video from database"""
        try:
            result = self.videos.update_one(
                {'video_id': video_id},
                {'$set': {'status': 'deleted', 'deleted_at': datetime.now()}}
            )
            logger.info(f"✅ Video deleted: {video_id}")
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error deleting video: {e}")
            return False
    
    def increment_view(self, video_id):
        """Increment video view count"""
        try:
            self.videos.update_one(
                {'video_id': video_id},
                {'$inc': {'views': 1}}
            )
        except Exception as e:
            logger.error(f"Error incrementing views: {e}")
    
    def increment_download(self, video_id):
        """Increment video download count"""
        try:
            self.videos.update_one(
                {'video_id': video_id},
                {'$inc': {'downloads': 1}}
            )
        except Exception as e:
            logger.error(f"Error incrementing downloads: {e}")
    
    def search_videos(self, query):
        """Search videos by title"""
        try:
            regex = {'$regex': query, '$options': 'i'}
            return list(self.videos.find({'title': regex, 'status': 'active'}).limit(20))
        except Exception as e:
            logger.error(f"Error searching videos: {e}")
            return []
    
    # ==================== USER OPERATIONS ====================
    
    def add_user(self, user_id, username=None, first_name=None):
        """Add new user to database"""
        try:
            # Check if user exists
            existing = self.users.find_one({'user_id': user_id})
            if existing:
                # Update last active
                self.users.update_one(
                    {'user_id': user_id},
                    {'$set': {'last_active': datetime.now()}}
                )
                return True  # User already exists
            
            # Create new user
            user_data = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'joined_at': datetime.now(),
                'last_active': datetime.now(),
                'is_banned': False,
                'total_videos_watched': 0,
                'language': 'bangla'
            }
            
            self.users.insert_one(user_data)
            logger.info(f"✅ New user added: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False
    
    def get_user(self, user_id):
        """Get user by ID"""
        try:
            return self.users.find_one({'user_id': user_id})
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
    
    def update_user_activity(self, user_id):
        """Update user last active time"""
        try:
            self.users.update_one(
                {'user_id': user_id},
                {
                    '$set': {'last_active': datetime.now()},
                    '$inc': {'total_videos_watched': 1}
                }
            )
        except Exception as e:
            logger.error(f"Error updating user activity: {e}")
    
    def get_all_users(self):
        """Get all users"""
        try:
            return list(self.users.find({'is_banned': False}))
        except Exception as e:
            logger.error(f"Error getting users: {e}")
            return []
    
    def ban_user(self, user_id):
        """Ban a user"""
        try:
            self.users.update_one(
                {'user_id': user_id},
                {'$set': {'is_banned': True, 'banned_at': datetime.now()}}
            )
            logger.info(f"✅ User banned: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error banning user: {e}")
            return False
    
    def unban_user(self, user_id):
        """Unban a user"""
        try:
            self.users.update_one(
                {'user_id': user_id},
                {'$set': {'is_banned': False}}
            )
            logger.info(f"✅ User unbanned: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error unbanning user: {e}")
            return False
    
    # ==================== STATISTICS ====================
    
    def get_stats(self):
        """Get comprehensive statistics"""
        try:
            # Total counts
            total_users = self.users.count_documents({'is_banned': False})
            total_videos = self.videos.count_documents({'status': 'active'})
            
            # Videos by category
            adult_count = self.videos.count_documents({'category': 'adult', 'status': 'active'})
            movie_count = self.videos.count_documents({'category': 'movie', 'status': 'active'})
            series_count = self.videos.count_documents({'category': 'series', 'status': 'active'})
            
            # Today's stats
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            new_users_today = self.users.count_documents({'joined_at': {'$gte': today_start}})
            new_videos_today = self.videos.count_documents({'added_at': {'$gte': today_start}, 'status': 'active'})
            
            # Top videos (last 7 days)
            seven_days_ago = datetime.now() - timedelta(days=7)
            top_videos = list(self.videos.find({
                'added_at': {'$gte': seven_days_ago},
                'status': 'active'
            }).sort('views', DESCENDING).limit(5))
            
            return {
                'total_users': total_users,
                'total_videos': total_videos,
                'adult_videos': adult_count,
                'movie_videos': movie_count,
                'series_videos': series_count,
                'new_users_today': new_users_today,
                'new_videos_today': new_videos_today,
                'top_videos': top_videos
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {
                'total_users': 0,
                'total_videos': 0,
                'adult_videos': 0,
                'movie_videos': 0,
                'series_videos': 0,
                'new_users_today': 0,
                'new_videos_today': 0
            }
    
    # ==================== ANALYTICS ====================
    
    def log_video_request(self, user_id, video_id, action='view'):
        """Log video request for analytics"""
        try:
            log_data = {
                'user_id': user_id,
                'video_id': video_id,
                'action': action,
                'timestamp': datetime.now()
            }
            self.analytics.insert_one(log_data)
        except Exception as e:
            logger.error(f"Error logging analytics: {e}")
    
    def get_popular_videos(self, days=7, limit=10):
        """Get most popular videos in last N days"""
        try:
            start_date = datetime.now() - timedelta(days=days)
            
            pipeline = [
                {'$match': {'timestamp': {'$gte': start_date}, 'action': 'view'}},
                {'$group': {
                    '_id': '$video_id',
                    'count': {'$sum': 1}
                }},
                {'$sort': {'count': -1}},
                {'$limit': limit}
            ]
            
            result = list(self.analytics.aggregate(pipeline))
            
            # Get video details
            popular_videos = []
            for item in result:
                video = self.get_video(item['_id'])
                if video:
                    video['request_count'] = item['count']
                    popular_videos.append(video)
            
            return popular_videos
        except Exception as e:
            logger.error(f"Error getting popular videos: {e}")
            return []
    
    # ==================== SETTINGS ====================
    
    def get_settings(self):
        """Get bot settings"""
        try:
            return self.settings.find_one({'_id': 'config'})
        except Exception as e:
            logger.error(f"Error getting settings: {e}")
            return {}
    
    def update_settings(self, key, value):
        """Update bot settings"""
        try:
            self.settings.update_one(
                {'_id': 'config'},
                {'$set': {key: value}}
            )
            logger.info(f"✅ Settings updated: {key}")
            return True
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
            return False
    
    # ==================== CLEANUP ====================
    
    def cleanup_old_analytics(self, days=30):
        """Remove analytics data older than N days"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            result = self.analytics.delete_many({'timestamp': {'$lt': cutoff_date}})
            logger.info(f"✅ Cleaned up {result.deleted_count} old analytics records")
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error cleaning analytics: {e}")
            return 0
    
    def __del__(self):
        """Close database connection"""
        try:
            if self.client:
                self.client.close()
                logger.info("Database connection closed")
        except:
            pass

# Create global database instance
db = Database()
