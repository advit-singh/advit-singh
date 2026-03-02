import datetime
from dateutil import relativedelta
import requests
import os
from lxml import etree
import time
import hashlib

HEADERS = {'authorization': 'token ' + os.environ['ACCESS_TOKEN']}
USER_NAME = os.environ['USER_NAME']

QUERY_COUNT = {
    'user_getter': 0,
    'follower_getter': 0,
    'graph_repos_stars': 0,
    'recursive_loc': 0,
    'graph_commits': 0,
    'loc_query': 0
}


def daily_readme(birthday):
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    return '{} {}, {} {}, {} {}{}'.format(
        diff.years, 'year' + format_plural(diff.years),
        diff.months, 'month' + format_plural(diff.months),
        diff.days, 'day' + format_plural(diff.days),
        ' 🎂' if (diff.months == 0 and diff.days == 0) else ''
    )


def format_plural(unit):
    return 's' if unit != 1 else ''


def simple_request(func_name, query, variables):
    request = requests.post(
        'https://api.github.com/graphql',
        json={'query': query, 'variables': variables},
        headers=HEADERS
    )
    if request.status_code == 200:
        return request
    raise Exception(func_name, 'failed with', request.status_code, request.text)


def graph_repos_stars(count_type, owner_affiliation, cursor=None):
    QUERY_COUNT['graph_repos_stars'] += 1
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        nameWithOwner
                        stargazers {
                            totalCount
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {
        'owner_affiliation': owner_affiliation,
        'login': USER_NAME,
        'cursor': cursor
    }
    request = simple_request(graph_repos_stars.__name__, query, variables)

    if count_type == 'repos':
        return request.json()['data']['user']['repositories']['totalCount']

    if count_type == 'stars':
        total_stars = 0
        for node in request.json()['data']['user']['repositories']['edges']:
            total_stars += node['node']['stargazers']['totalCount']
        return total_stars


def follower_getter(username):
    QUERY_COUNT['follower_getter'] += 1
    query = '''
    query($login: String!){
        user(login: $login) {
            followers {
                totalCount
            }
        }
    }'''
    request = simple_request(follower_getter.__name__, query, {'login': username})
    return int(request.json()['data']['user']['followers']['totalCount'])


def user_getter(username):
    QUERY_COUNT['user_getter'] += 1
    query = '''
    query($login: String!){
        user(login: $login) {
            id
            createdAt
        }
    }'''
    variables = {'login': username}
    request = simple_request(user_getter.__name__, query, variables)
    return request.json()['data']['user']['id'], request.json()['data']['user']['createdAt']


def svg_overwrite(filename, age_data, commit_data, star_data,
                  repo_data, contrib_data, follower_data):

    tree = etree.parse(filename)
    root = tree.getroot()

    def replace(element_id, new_text):
        element = root.find(f".//*[@id='{element_id}']")
        if element is not None:
            element.text = str(new_text)

    replace('age_data', age_data)
    replace('commit_data', f"{commit_data:,}")
    replace('star_data', f"{star_data:,}")
    replace('repo_data', f"{repo_data:,}")
    replace('contrib_data', f"{contrib_data:,}")
    replace('follower_data', f"{follower_data:,}")

    tree.write(filename, encoding='utf-8', xml_declaration=True)


if __name__ == '__main__':
    print("Running profile build...")

    OWNER_ID, account_created = user_getter(USER_NAME)

    # December 25, 2008
    age_data = daily_readme(datetime.datetime(2008, 12, 25))

    repo_data = graph_repos_stars('repos', ['OWNER'])
    star_data = graph_repos_stars('stars', ['OWNER'])
    contrib_data = graph_repos_stars(
        'repos',
        ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER']
    )

    follower_data = follower_getter(USER_NAME)

    # Use contributions API for total commits
    query = '''
    query($login: String!) {
        user(login: $login) {
            contributionsCollection {
                contributionCalendar {
                    totalContributions
                }
            }
        }
    }'''
    variables = {'login': USER_NAME}
    request = simple_request("commit_query", query, variables)
    commit_data = int(
        request.json()['data']['user']['contributionsCollection']
        ['contributionCalendar']['totalContributions']
    )

    svg_overwrite(
        'dark_mode.svg',
        age_data,
        commit_data,
        star_data,
        repo_data,
        contrib_data,
        follower_data
    )

    svg_overwrite(
        'light_mode.svg',
        age_data,
        commit_data,
        star_data,
        repo_data,
        contrib_data,
        follower_data
    )

    print("README SVG updated successfully.")
