# Script adapted from Andrew Grant (github.com/Andrew6rant)

import os
import json
import requests
from lxml import etree
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- SETTINGS ---
START_DATE = datetime(2008, 12, 25) 
USER_NAME = os.environ.get("USER_NAME", "")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")
CACHE_FILE = "loc_cache.json" # The file where we will save the fast-cache

HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

def run_query(query, variables=None):
    """Runs a GraphQL query and returns the JSON data."""
    request = requests.post("https://api.github.com/graphql", json={"query": query, "variables": variables}, headers=HEADERS)
    if request.status_code == 200:
        return request.json()
    raise Exception(f"Query failed! Code: {request.status_code}. Response: {request.text}")

def get_uptime():
    """Calculates age/uptime from START_DATE."""
    now = datetime.now()
    diff = relativedelta(now, START_DATE)
    return f"{diff.years} years, {diff.months} months, {diff.days} days"

def fetch_stats():
    print(f"Fetching stats for {USER_NAME}...")

    # 1. Get Basic Stats & User ID
    user_query = """
    query($login: String!) {
      user(login: $login) {
        id
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
          totalCount
        }
        repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) {
          totalCount
        }
      }
    }
    """
    user_data = run_query(user_query, {"login": USER_NAME})["data"]["user"]
    author_id = user_data["id"]
    repos_count = user_data["repositories"]["totalCount"]
    contrib_count = user_data["repositoriesContributedTo"]["totalCount"]

    # 2. Get Total Commits via Search API (Super Fast)
    commit_req = requests.get(
        f"https://api.github.com/search/commits?q=author:{USER_NAME}", 
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}", "Accept": "application/vnd.github.cloak-preview+json"}
    )
    commits = commit_req.json().get("total_count", 0) if commit_req.status_code == 200 else 0

    # 3. LOC Calculation with Local Cache Logic
    try:
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}

    repos_query = """
    query ($login: String!, $cursor: String) {
      user(login: $login) {
        repositories(first: 50, after: $cursor, ownerAffiliations:[OWNER, COLLABORATOR, ORGANIZATION_MEMBER]) {
          pageInfo { hasNextPage endCursor }
          nodes {
            nameWithOwner
            owner { login }
            name
            defaultBranchRef { target { ... on Commit { history { totalCount } } } }
          }
        }
      }
    }
    """
    
    all_repos =[]
    has_next = True
    cursor = None
    
    # Fetch all repo names and their total commit counts
    while has_next:
        data = run_query(repos_query, {"login": USER_NAME, "cursor": cursor})["data"]["user"]["repositories"]
        all_repos.extend(data["nodes"])
        has_next = data["pageInfo"]["hasNextPage"]
        cursor = data["pageInfo"]["endCursor"]

    total_additions = 0
    total_deletions = 0

    print(f"Calculating LOC across {len(all_repos)} repositories using cache...")
    
    for repo in all_repos:
        if not repo.get("defaultBranchRef"):
            continue # Skip empty repos
            
        name_with_owner = repo["nameWithOwner"]
        owner = repo["owner"]["login"]
        name = repo["name"]
        repo_total_commits = repo["defaultBranchRef"]["target"]["history"]["totalCount"]
        
        # --- CACHE CHECK ---
        # If the total commits haven't changed since yesterday, load from cache!
        if name_with_owner in cache and cache[name_with_owner].get("total_commits") == repo_total_commits:
            total_additions += cache[name_with_owner].get("additions", 0)
            total_deletions += cache[name_with_owner].get("deletions", 0)
        else:
            # Cache miss: We made a new commit! Query ONLY this repo's lines of code
            print(f"  -> Cache miss for {name_with_owner}. Fetching updates...")
            repo_additions = 0
            repo_deletions = 0
            
            loc_query = """
            query ($owner: String!, $name: String!, $author_id: ID!, $cursor: String) {
              repository(owner: $owner, name: $name) {
                defaultBranchRef {
                  target {
                    ... on Commit {
                      history(first: 100, after: $cursor, author: {id: $author_id}) {
                        pageInfo { hasNextPage endCursor }
                        nodes { additions deletions }
                      }
                    }
                  }
                }
              }
            }
            """
            loc_has_next = True
            loc_cursor = None
            
            while loc_has_next:
                loc_data = run_query(loc_query, {"owner": owner, "name": name, "author_id": author_id, "cursor": loc_cursor})
                history = loc_data["data"]["repository"]["defaultBranchRef"]["target"]["history"]
                
                for node in history["nodes"]:
                    repo_additions += node["additions"]
                    repo_deletions += node["deletions"]
                    
                loc_has_next = history["pageInfo"]["hasNextPage"]
                loc_cursor = history["pageInfo"]["endCursor"]
            
            # Update the cache with the new numbers
            cache[name_with_owner] = {
                "total_commits": repo_total_commits,
                "additions": repo_additions,
                "deletions": repo_deletions
            }
            total_additions += repo_additions
            total_deletions += repo_deletions

    # Save the cache file for tomorrow's run
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

    print(f"Complete! Found {total_additions + total_deletions} lines of code.")
    return {
        "repo_data": f"{repos_count}",
        "contrib_data": f"{contrib_count}",
        "commit_data": f"{commits:,}",
        "loc_data": f"{total_additions + total_deletions:,}",
        "loc_add_data": f"{total_additions:,}++",
        "loc_del_data": f"{total_deletions:,}--"
    }

def update_svg(filename, stats):
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(filename, parser)
    
    for element_id, new_text in stats.items():
        elements = tree.xpath(f"//*[@id='{element_id}']")
        for el in elements:
            el.text = new_text
            
    tree.write(filename, pretty_print=True, xml_declaration=True, encoding="utf-8")

if __name__ == "__main__":
    stats = fetch_stats()
    stats["age_data"] = get_uptime()
    
    update_svg("dark_mode.svg", stats)
    update_svg("light_mode.svg", stats)
