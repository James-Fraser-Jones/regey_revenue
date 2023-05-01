#requires python 3.11.3

#https://learn.microsoft.com/en-us/windows/python/web-frameworks
#https://iohk.zendesk.com/hc/en-us/articles/16724475448473-Install-Python-3-11-on-ubuntu
#https://stackoverflow.com/a/71726397

# environments:
#      create virtual environment: python3.11 -m venv .venv
#      active virtual environment: source .venv/bin/activate
#  deactivate virtual environment: deactivate
# make sure venv environment is selected in vscode as well (bottom right corner button)

# install commands (after activating environment):
# pip install selenium
# pip install webdriver-manager

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.firefox import GeckoDriverManager

import csv
import re

#=================================================================
#csv reformatting

#example usage of reading and writing csv data from and to files
def csv_test():
    with open('regey_data_50.csv', newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        with open('regey_data_50_out.csv', 'w', newline='') as csvfileout:
            csvwriter = csv.writer(csvfileout)
            for row in csvreader:
                csvwriter.writerow([row[0], row[1]])

#used to remove all but first column of regey_data.csv     
def clean_data():
    map_csv(lambda row: [row[0]], "regey_data")

#reformatting   org,url,rev_str,rev_num,match_score
#to:            org,url,rev_str,rev_num,match_score,corrected,category
def reformat_companies():
    map_csv(lambda row: [row[0],row[1],row[2],row[3],row[4],"","" if row[3] == "" else get_category(row[3])], "regey_data_companies")

#reformatting   org,url,name,year,revenue,assets,liabilities,summed
#to:            org,url,name,summed,year,revenue,category,assets,liabilities
def reformat_foundations():
    map_csv(lambda row: [row[0],row[1],row[2],row[7],row[3],row[4],"" if row[7] == "" else get_category(row[7]),row[5],row[6]], "regey_data_foundations")

#=================================================================
#main

#returns dictionary with org,url,rev_str,rev_num,match_score,corrected,category fields
def search_company(driver, org):
    results = google_search(driver, f"{org} annual revenue zoominfo", 10)
    result_infos = []
    for result in results:
        try:
            link = result.find_element(by=By.TAG_NAME, value="a")
        except NoSuchElementException:
            continue

        url = link.get_attribute("href")

        rev_strings = rev_regex.findall(result.text)
        rev_groups = rev_regex_grouped.findall(result.text)
        if len(rev_strings) == 0:
            continue

        rev_str = ""
        rev_num = 0        
        for i in range(len(rev_groups)):
            cur_rev_str = rev_strings[i]
            cur_rev_group = rev_groups[i]
            cur_rev_num = get_rev_number(cur_rev_group)
            if cur_rev_num > rev_num:
                rev_num = cur_rev_num
                rev_str = cur_rev_str

        result_infos.append({"org": org, "url": url, "rev_str": rev_str, "rev_num": rev_num})

    dist = get_dist()
    best_result = result_infos[0]
    best_match_score = 0
    for result_info in result_infos:
        url = result_info["url"]
        if not "https://www.zoominfo.com/c/" in url:
            continue

        zoom_org = url.split("/")[4]
        zoom_org_tokens = get_org_tokens(zoom_org)
        org_tokens = get_org_tokens(org)
        match_score = get_match_score(dist, org_tokens, zoom_org_tokens)

        if match_score > best_match_score:
            best_match_score = match_score
            best_result = result_info
    
    best_result["match_score"] = best_match_score
    best_result["corrected"] = ""
    best_result["category"] = get_category(best_result["rev_num"])
    return best_result

#returns dictionary with org,url,name,summed,year,revenue,category,assets,liabilities fields
def search_foundation(driver, org):
    results = google_search(driver, f"{org} 990 propublica", 10)
    for result in results:
        try:
            link = result.find_element(by=By.TAG_NAME, value="a")
        except NoSuchElementException:
            continue
        url = link.get_attribute("href")
        if "propublica" in url:

            driver.get(url)

            url_tokens = url.split("/")
            if len(url_tokens) > 6:
                url = ("/").join(url_tokens[:-2])
                driver.get(url)
            
            publica_results_element = WebDriverWait(driver, 10).until(lambda x: x.find_element(by=By.CLASS_NAME, value="filings"))
            publica_results = publica_results_element.find_elements(by=By.XPATH, value="*") #gets all direct children of an element
            name = driver.find_elements(by=By.TAG_NAME, value="h1")[1].text
            for publica_result in publica_results:
                id = publica_result.get_attribute("id")
                if "filing" in id:
                    year = id[6:]
                    rows = publica_result.find_elements(by=By.TAG_NAME, value="tr")
                    revenue = None
                    assets = None
                    liabilities = None
                    for row in rows:
                        elems = row.find_elements(by=By.XPATH, value="*")
                        if len(elems) == 0:
                            continue
                        if elems[0].text == "Total Revenue":
                            revenue = get_publica_revenue(elems[1].text)
                        elif elems[0].text == "Total Assets":
                            assets = get_publica_revenue(elems[1].text)
                        elif elems[0].text == "Total Liabilities":
                            liabilities = get_publica_revenue(elems[1].text)
                    if revenue is not None and assets is not None and liabilities is not None:
                        summed = round(revenue + assets - liabilities, 2)
                        category = get_category(summed)
                        return {"org": org, "url": url, "name": name, "summed": summed, "year": year, "revenue": revenue, "category": category, "assets": assets, "liabilities": liabilities}
            raise Exception(f"Could not find filing with revenue, assets and liabilities\nurl: {url}\nname: {name}")
    raise Exception("Could not find propublica link")

def run(foundations=False):
    driver = get_driver(headless=True)

    #get list of already done companies
    done = []
    out_file = f"regey_data_{'foundations' if foundations else 'companies'}"
    with open(f"{out_file}.csv", newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        for row in csvreader:
            done.append(row[0])

    with open('regey_data.csv', newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        with open(f"{out_file}.csv", 'a', newline='') as csvfileout:
            with open(f"{out_file}_new.csv", 'a', newline='') as csvfileoutnew:
                csvwriter = csv.writer(csvfileout)
                csvwriternew = csv.writer(csvfileoutnew)
                for row in csvreader:
                    org = row[0]
                    foundation = is_foundation(org)
                    if (foundation == foundations) and (not org in done):
                        try:
                            result = search_foundation(driver, org) if foundations else search_company(driver, org)
                        except Exception as e:
                            print(f"{org} caused exception: \n{e}")
                            return
                        entry = list(result.values())
                        print(entry)
                        csvwriter.writerow(entry)
                        csvwriternew.writerow(entry)

def run_single(org, check=True):
    driver = get_driver()

    if check:
        found = False
        with open('regey_data.csv', newline='') as csvfilein:
            csvreader = csv.reader(csvfilein)
            for row in csvreader:
                row_org = row[0]
                if org == row_org:
                    found = True
                    break
        if not found:
            raise Exception(f"Org not found in file: {org}")
    
    foundation = is_foundation(org)
    if foundation:
        print(search_foundation(driver, org))
    else:
        print(search_company(driver, org))
    return

#=================================================================
#regexes

#https://regexr.com/7bh2j
#https://stackoverflow.com/questions/3512471/what-is-a-non-capturing-group-in-regular-expressions

#these regexes both match strings containing dollar revenue quantities (usually measured in millions of dollars) 
#they also optionally match a less than sign (<) at the start
#rev_regex returns the entire matched string section
#rev_regex_grouped returns an array of 3 elements:
#   the first indicates whether a (<) was matched (either "<" or "")
#   the second returns the quantity value (including fractional decimal amounts)
#   the third returns the units ("K" "M" "B" for thousands millions billions, respectively)

rev_regex = re.compile(r'<?\$\d+(?:\.\d+)? ?(?:K|M|B)')
rev_regex_grouped = re.compile(r'(<?)\$(\d+(?:\.\d+)?) ?(K|M|B)')
org_token_regex = re.compile(r'\w+')
foundation_regex = re.compile(r' foundation| fund| trust')
publica_rev_regex = re.compile(r'\$|,')

#=================================================================
#utils

#maps a function over rows from a csv file (or elements if specified)
def map_csv(func, file, elements=False, debug=False):
    rows = []
    with open(f"{file}.csv", newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        for row in csvreader:
            rows.append(row)

    def debug_func(x):
        print(x)
        return func(x)
    real_func = debug_func if debug else func

    if elements:
        new_rows = list(map(lambda row : map(real_func, row), rows))
    else:
        new_rows = list(map(real_func, rows))

    with open(f"{file}_map.csv", 'w', newline='') as csvfileout:
        csvwriter = csv.writer(csvfileout)
        for new_row in new_rows:
            csvwriter.writerow(new_row)

def get_category(rev):
    rev = float(rev)
    if rev >= 500000000:
        category = "$500M+"
    elif rev >= 100000000:
        category = "$100M - $500M"
    elif rev >= 50000000:
        category = "$50M - $100M"
    elif rev >= 10000000:
        category = "$10M - $50M"
    elif rev >= 5000000:
        category = "$5M - $10M"
    elif rev >= 1000000:
        category = "$1M - $5M"
    else:
        category = "Under $1 Million"
    return category

def is_foundation(org):
    return len(foundation_regex.findall(org.lower())) > 0

#gets webdriver
def get_driver(headless=False):
    options = Options()
    if headless:
        options.add_argument('--headless')
    driver = webdriver.Firefox(options=options, service=FirefoxService(GeckoDriverManager().install()))
    return driver

#performs a google search and waits for results before returning them
def google_search(driver, search_string, wait):
    driver.get("https://www.google.com/")

    #remove annoying popup
    try:
        accept_all = driver.find_element(by=By.ID, value="L2AGLb")
        accept_all.click()
    except:
        pass

    search_box = driver.find_element(by=By.ID, value="APjFqb")
    search_box.send_keys(search_string)

    google_search = driver.find_element(by=By.NAME, value="btnK")
    google_search.submit() #submit instead of click is necessary for some reason

    results_element = WebDriverWait(driver, wait).until(lambda x: x.find_element(by=By.ID, value="rso"))
    results = results_element.find_elements(by=By.XPATH, value="*") #gets all direct children of an element
    return results

#produces revenue number from rev_group regex match
def get_rev_number(rev_group):
    rev_number = float(rev_group[1])
    match rev_group[2]:
        case "K":
            rev_number *= 1000
        case "M":
            rev_number *= 1000000
        case "B":
            rev_number *= 1000000000
    if rev_group[0] == "<":
        rev_number *= 0.8 #this simply ensures that the revenue will be grouped into the lower range bracket
    return round(rev_number, 2)

#lowercases org (first column in regey_data.csv) and then splits on all non alpha-numeric characters
def get_org_tokens(org):
    lower_org = org.lower()
    tokens = org_token_regex.findall(lower_org)
    return tokens

#gets frequency distribution of tokens as a dictionary, based on regey_data.csv
def get_dist():
    dist = {}
    with open('regey_data.csv', newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        for row in csvreader:
            tokens = get_org_tokens(row[0])
            for token in tokens:
                if token == "":
                    continue
                if token in dist:
                    dist[token] += 1
                else:
                    dist[token] = 1
    return {k: v for k, v in sorted(dist.items(), key=lambda item: item[1], reverse=True)}

#produces match score by sum totalling the scores (based on inverse frequency from distribution) of all token matches
def get_match_score(dist, org_tokens, zoom_org_tokens):
    match_score = 0
    max_freq = list(dist.values())[0]
    for org_token in org_tokens:
        if org_token in zoom_org_tokens:
            match_score += max_freq - dist[org_token]
    return match_score

#remove dollars and commas
def get_publica_revenue(rev_string):
    rev_string = publica_rev_regex.sub("", rev_string) 
    return round(float(rev_string), 2)

#=================================================================
#scratch

#run()
#run(foundations=True)
#run_single("Neubauer Foundation")