import requests
import json
from datetime import datetime, timezone, date, timedelta

LEETCODE_URL = "https://leetcode.com/graphql"

def fetch_leetcode_data(username):
    """
    Fetches the public profile, submission stats, recent submissions, and contest ranking
    for a given LeetCode username via the official GraphQL endpoint.
    """
    query = """
    query userCombinedData($username: String!) {
      matchedUser(username: $username) {
        username
        profile {
          realName
          userAvatar
          ranking
        }
        submissionCalendar
        submitStatsGlobal {
          acSubmissionNum {
            difficulty
            count
          }
        }
      }
      recentAcSubmissionList(username: $username, limit: 20) {
        id
        title
        titleSlug
        timestamp
      }
      userContestRanking(username: $username) {
        rating
        globalRanking
      }
    }
    """
    
    variables = {"username": username}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.post(LEETCODE_URL, json={"query": query, "variables": variables}, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if "errors" in data:
                # Log errors but don't fail immediately if matchedUser exists
                print(f"GraphQL Errors for {username}: {data['errors']}")
                
            res_data = data.get("data", {})
            if not res_data or not res_data.get("matchedUser"):
                return None
            return res_data
        else:
            print(f"HTTP Error {response.status_code} for user {username}")
            return None
    except Exception as e:
        print(f"Scraper exception for user {username}: {e}")
        return None

def parse_submission_calendar(calendar_str):
    """
    Parses LeetCode submissionCalendar JSON string into a dict of {date: count}.
    """
    if not calendar_str:
        return {}
    try:
        calendar_data = json.loads(calendar_str)
        parsed = {}
        for ts_str, count in calendar_data.items():
            ts = int(ts_str)
            # Convert LeetCode UTC timestamp to IST date (India Standard Time)
            dt = datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=5, minutes=30))).date()
            parsed[dt] = count
        return parsed
    except Exception as e:
        print(f"Error parsing submission calendar: {e}")
        return {}

def calculate_streaks(parsed_calendar):
    """
    Calculates current streak and max streak based on parsed calendar.
    """
    if not parsed_calendar:
        return 0, 0
        
    sorted_dates = sorted(parsed_calendar.keys())
    if not sorted_dates:
        return 0, 0
        
    max_streak = 0
    temp_streak = 0
    prev_date = None
    
    # Calculate historical max streak
    for d in sorted_dates:
        # We only count days where user actually solved at least 1 problem
        if parsed_calendar[d] <= 0:
            if temp_streak > max_streak:
                max_streak = temp_streak
            temp_streak = 0
            prev_date = None
            continue
            
        if prev_date is None:
            temp_streak = 1
        elif d == prev_date + timedelta(days=1):
            temp_streak += 1
        else:
            if temp_streak > max_streak:
                max_streak = temp_streak
            temp_streak = 1
        prev_date = d
        
    if temp_streak > max_streak:
        max_streak = temp_streak
        
    # Calculate current streak ending today or yesterday (IST)
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    yesterday = today - timedelta(days=1)
    
    current_streak = 0
    check_date = today
    
    # If not solved today but solved yesterday, start tracing from yesterday
    if parsed_calendar.get(today, 0) == 0 and parsed_calendar.get(yesterday, 0) > 0:
        check_date = yesterday
        
    while parsed_calendar.get(check_date, 0) > 0:
        current_streak += 1
        check_date -= timedelta(days=1)
        
    max_streak = max(max_streak, current_streak)
    return current_streak, max_streak

def calculate_period_solves(parsed_calendar):
    """
    Calculates problems solved today, weekly (last 7 days), and monthly (last 30 days) in IST.
    """
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    
    today_solves = parsed_calendar.get(today, 0)
    
    weekly_solves = 0
    for i in range(7):
        d = today - timedelta(days=i)
        weekly_solves += parsed_calendar.get(d, 0)
        
    monthly_solves = 0
    for i in range(30):
        d = today - timedelta(days=i)
        monthly_solves += parsed_calendar.get(d, 0)
        
    return today_solves, weekly_solves, monthly_solves
