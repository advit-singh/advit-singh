import os
import requests
from lxml import etree
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- 1. SETTINGS ---
# Set your birthday / start date here to calculate "Uptime"
START_DATE = datetime(2008, 12, 25) 

USER_NAME = os.environ.get("USER_NAME", "")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def get_uptime():
    now = datetime.now()
    diff = relativedelta(now, START_DATE)
    return f"{diff.years} years, {diff.months} months, {diff.days} days"

def fetch_stats():
    print(f"Fetching stats for {USER_NAME}...")

    # 1. Get Total Commits using GitHub Search API
    commit_req = requests.get(
        f"https://api.github.com/search/commits?q=author:{USER_NAME}", 
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}", "Accept": "application/vnd.github.cloak-preview+json"}
    )
    commits = commit_req.json().get("total_count", 0) if commit_req.status_code == 200 else 0

    # 2. Get Repos & Contributed using GraphQL
    query = """
    query($login: String!) {
      user(login: $login) {
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
          totalCount
          nodes {
            name
          }
        }
        repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) {
          totalCount
        }
      }
    }
    """
    gql_req = requests.post("https://api.github.com/graphql", json={"query": query, "variables": {"login": USER_NAME}}, headers=HEADERS)
    data = gql_req.json().get("data", {}).get("user", {})
    
    repos_count = data.get("repositories", {}).get("totalCount", 0)
    contrib_count = data.get("repositoriesContributedTo", {}).get("totalCount", 0)
    repo_nodes = data.get("repositories", {}).get("nodes",[])

    # 3. Calculate Lines of Code (Additions & Deletions)
    print(f"Calculating LOC across {len(repo_nodes)} repositories... (This might take a moment)")
    additions = 0
    deletions = 0

    for repo in repo_nodes:
        repo_name = repo["name"]
        stats_req = requests.get(f"https://api.github.com/repos/{USER_NAME}/{repo_name}/stats/contributors", headers=HEADERS)
        
        if stats_req.status_code == 200:
            stats = stats_req.json()
            if isinstance(stats, list):
                for contributor in stats:
                    # Only tally YOUR code, not people who contributed to your repos
                    if contributor.get("author", {}).get("login", "").lower() == USER_NAME.lower():
                        for week in contributor.get("weeks",[]):
                            additions += week.get("a", 0)
                            deletions += week.get("d", 0)

    total_loc = additions + deletions

    print("Data fetching complete!")
    return {
        "repo_data": f"{repos_count}",
        "contrib_data": f"{contrib_count}",
        "commit_data": f"{commits:,}",
        "loc_data": f"{total_loc:,}",
        "loc_add_data": f"{additions:,}++",
        "loc_del_data": f"{deletions:,}--"
    }

def update_svg(filename, stats):
    # Parse SVG
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(filename, parser)
    
    # Update elements by ID
    for element_id, new_text in stats.items():
        # Uses xpath to find the ID regardless of XML namespaces
        elements = tree.xpath(f"//*[@id='{element_id}']")
        for el in elements:
            el.text = new_text
            
    # Save file
    tree.write(filename, pretty_print=True, xml_declaration=True, encoding="utf-8")
    print(f"Updated {filename}")

if __name__ == "__main__":
    # Gather all data
    stats = fetch_stats()
    stats["age_data"] = get_uptime()
    
    # Update both SVGs
    update_svg("dark_mode.svg", stats)
    update_svg("light_mode.svg", stats)
