import tweepy
import time
import logging
import os
from datetime import datetime
import random
from dotenv import load_dotenv
import sys

# Set up logging to file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("twitter_bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger()

# Load environment variables from .env file
load_dotenv()


# Access Twitter API credentials
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

# Print to check if they are loaded (optional, remove this in production)
print("API Key:", TWITTER_API_KEY)

# ======= CONFIGURATION =======
# Bot behavior settings (customize these)
TWEET_INTERVAL = 60 * 60  # Post every 60 minutes (in seconds)
HASHTAGS_TO_LIKE = ["python", "coding", "technology"]  # Hashtags to search and like
MAX_LIKES_PER_RUN = 3  # Maximum number of tweets to like per cycle
TWEETS = [
    "Just another day coding with Python! #Python #Coding",
    "Exploring new programming techniques today. #Coding #Technology",
    "Automation makes life easier! #Python #Technology",
    "Building cool stuff with code. #Coding #Development",
    "Learning something new every day in tech. #Technology #Learning"
]
# =================================================

def get_credentials():
    """Get API credentials from environment variables"""
    required_vars = [
        "TWITTER_API_KEY", 
        "TWITTER_API_SECRET", 
        "TWITTER_ACCESS_TOKEN", 
        "TWITTER_ACCESS_SECRET",
        "TWITTER_BEARER_TOKEN"
    ]
    
    # Check if all required variables exist
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        logger.error(f"Missing environment variables: {', '.join(missing)}")
        logger.error("Create a .env file with these variables or set them in your environment")
        return None
    
    # Return credentials as dictionary
    return {
        "api_key": os.getenv("TWITTER_API_KEY"),
        "api_secret": os.getenv("TWITTER_API_SECRET"),
        "access_token": os.getenv("TWITTER_ACCESS_TOKEN"),
        "access_secret": os.getenv("TWITTER_ACCESS_SECRET"),
        "bearer_token": os.getenv("TWITTER_BEARER_TOKEN")
    }

def authenticate_twitter():
    """Connect to Twitter API v2"""
    credentials = get_credentials()
    if not credentials:
        return None, None
    
    try:
        # Client for v2 endpoints that require OAuth 1.0a User Context
        client_v1 = tweepy.Client(
            consumer_key=credentials["api_key"],
            consumer_secret=credentials["api_secret"],
            access_token=credentials["access_token"],
            access_token_secret=credentials["access_secret"]
        )
        
        # Client for v2 endpoints with bearer token (app-only auth)
        client_v2 = tweepy.Client(bearer_token=credentials["bearer_token"])
        
        # Also create API v1.1 object for some functionalities not yet in v2
        auth = tweepy.OAuth1UserHandler(
            credentials["api_key"], 
            credentials["api_secret"],
            credentials["access_token"], 
            credentials["access_secret"]
        )
        api_v1 = tweepy.API(auth, wait_on_rate_limit=True)
        
        # Verify credentials
        me = client_v1.get_me()
        logger.info(f"Connected as @{me.data.username}")
        
        return client_v1, client_v2, api_v1
    
    except tweepy.TweepyException as e:
        logger.error(f"Authentication failed: {e}")
        return None, None, None

def post_tweet(client):
    """Post a random tweet from our list using v2 API"""
    tweet = random.choice(TWEETS)
    try:
        response = client.create_tweet(text=tweet)
        tweet_id = response.data['id']
        logger.info(f"Posted tweet: {tweet} (ID: {tweet_id})")
        return tweet_id
    except tweepy.TooManyRequests:
        logger.warning("Rate limit exceeded. Waiting before next attempt.")
        return None
    except tweepy.Forbidden:
        logger.error("Posting tweets forbidden. Check your API access level.")
        return None
    except Exception as e:
        logger.error(f"Error posting tweet: {e}")
        return None

def like_tweets(client_v2, api_v1):
    """Like some tweets with our target hashtags using v2 API for search and v1.1 for liking"""
    hashtag = random.choice(HASHTAGS_TO_LIKE)
    try:
        # Search tweets with v2 API
        query = f"#{hashtag} -is:retweet lang:en"
        tweets = client_v2.search_recent_tweets(
            query=query, 
            max_results=10,
            tweet_fields=['created_at']
        )
        
        if not tweets.data:
            logger.info(f"No recent tweets found with #{hashtag}")
            return 0
            
        liked_count = 0
        for tweet in tweets.data[:MAX_LIKES_PER_RUN]:
            try:
                # We need to use v1.1 API for liking as v2 might require different permissions
                api_v1.create_favorite(tweet.id)
                logger.info(f"Liked tweet with #{hashtag} (ID: {tweet.id})")
                liked_count += 1
                time.sleep(5)  # Small delay between likes
            except tweepy.TweepyException as e:
                if "already favorited" in str(e).lower():
                    logger.info(f"Tweet already liked (ID: {tweet.id})")
                else:
                    logger.error(f"Error liking tweet {tweet.id}: {e}")
                
        return liked_count
    except tweepy.TooManyRequests:
        logger.warning("Rate limit exceeded when searching tweets. Waiting before next attempt.")
        return 0
    except Exception as e:
        logger.error(f"Error searching or liking tweets: {e}")
        return 0

def reply_to_mentions(client, since_id=None):
    """Reply to any mentions of the bot using v2 API"""
    try:
        # Get user ID first
        me = client.get_me()
        user_id = me.data.id
        
        # Get mentions
        query_params = {"expansions": "author_id"}
        if since_id:
            query_params["since_id"] = since_id
            
        mentions = client.get_users_mentions(
            id=user_id,
            **query_params
        )
        
        if not mentions.data:
            logger.info("No new mentions found")
            return since_id
            
        logger.info(f"Found {len(mentions.data)} mentions to process")
        new_since_id = since_id
        
        for mention in mentions.data:
            if not since_id or mention.id > since_id:
                if not new_since_id or mention.id > new_since_id:
                    new_since_id = mention.id
                
                # Get username from includes
                author_id = mention.author_id
                username = None
                if mentions.includes and "users" in mentions.includes:
                    for user in mentions.includes["users"]:
                        if user.id == author_id:
                            username = user.username
                            break
                
                if not username:
                    user = client.get_user(id=author_id).data
                    username = user.username
                
                reply = f"@{username} Thanks for the mention! This is an automated reply."
                
                try:
                    client.create_tweet(
                        text=reply,
                        in_reply_to_tweet_id=mention.id
                    )
                    logger.info(f"Replied to @{username}")
                    time.sleep(5)  # Small delay between replies
                except Exception as e:
                    logger.error(f"Error replying to mention: {e}")
                
        return new_since_id
    except tweepy.TooManyRequests:
        logger.warning("Rate limit exceeded when getting mentions. Waiting before next attempt.")
        return since_id
    except Exception as e:
        logger.error(f"Error processing mentions: {e}")
        return since_id

def follow_back_users(client, api_v1):
    """Follow back users who follow the bot but aren't followed back yet"""
    try:
        me = client.get_me()
        user_id = me.data.id
        
        # Get followers (using v1.1 API as it's easier to iterate)
        followers = tweepy.Cursor(api_v1.get_followers, user_id=user_id).items(20)
        following = tweepy.Cursor(api_v1.get_friends, user_id=user_id).items(100)
        
        # Convert following to a set of IDs for quick lookup
        following_ids = set()
        for user in following:
            following_ids.add(user.id)
        
        count = 0
        for follower in followers:
            if follower.id not in following_ids:
                try:
                    client.follow_user(follower.id)
                    logger.info(f"Followed back @{follower.screen_name}")
                    count += 1
                    time.sleep(5)  # Small delay between follows
                    
                    # Limit to 5 new follows per run to avoid rate limits
                    if count >= 5:
                        break
                except Exception as e:
                    logger.error(f"Error following user @{follower.screen_name}: {e}")
        
        if count > 0:
            logger.info(f"Followed back {count} users")
        else:
            logger.info("No new users to follow back")
            
        return count
    except Exception as e:
        logger.error(f"Error in follow-back process: {e}")
        return 0

def run_bot():
    """Main bot function with improved error handling and retry logic"""
    print("🤖 Starting Twitter bot...")
    
    # Connect to Twitter
    client_v1, client_v2, api_v1 = authenticate_twitter()
    if not client_v1 or not client_v2:
        print("⚠️  Error: Could not authenticate with Twitter API")
        return
    
    print("🟢 Bot is now running! Press CTRL+C to stop.")
    
    since_id = None
    last_tweet_time = 0
    follow_back_interval = 6 * 60 * 60  # Every 6 hours
    last_follow_back_time = 0
    consecutive_errors = 0
    max_errors = 5
    
    # Main loop
    while True:
        try:
            current_time = time.time()
            
            # Check and reply to mentions
            # since_id = reply_to_mentions(client_v1, since_id)
            
            # Post a tweet if it's time
            if current_time - last_tweet_time >= TWEET_INTERVAL:
                if post_tweet(client_v1):
                    last_tweet_time = current_time
            
            # Like some tweets with our hashtags
            # liked = like_tweets(client_v2, api_v1)
            # if liked:
            #     logger.info(f"Liked {liked} tweets")
            
            # Follow back users periodically
            # if current_time - last_follow_back_time >= follow_back_interval:
            #     followed = follow_back_users(client_v1, api_v1)
            #     if followed:
            #         last_follow_back_time = current_time
            
            # Reset error counter on successful run
            consecutive_errors = 0
            
            # Wait before next cycle - check every 5 minutes
            logger.info("Waiting for next check...")
            time.sleep(100)  # 5 minutes
            
        except KeyboardInterrupt:
            print("\n👋 Bot stopped by user. Goodbye!")
            break
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Unhandled error: {e}")
            
            if consecutive_errors >= max_errors:
                logger.critical(f"Too many consecutive errors ({consecutive_errors}). Stopping bot.")
                break
                
            # Exponential backoff on repeated errors
            wait_time = min(300 * (2 ** (consecutive_errors - 1)), 3600)  # Max 1 hour
            logger.warning(f"Waiting {wait_time} seconds before retry...")
            time.sleep(wait_time)

if __name__ == "__main__":

    run_bot()