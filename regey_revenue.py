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
import math

#=================================================================
#examples and now unsused code

#example usage of reading and writing csv data from and to files
def csv_test():
    with open('regey_data_50.csv', newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        with open('regey_data_50_out.csv', 'w', newline='') as csvfileout:
            csvwriter = csv.writer(csvfileout)
            for row in csvreader:
                csvwriter.writerow([row[0], row[1]])

#this was used to generate "regey_tokens.csv" in order to create a frequency distribution 
#this distribution was then used to create an effective token_filter_list
def get_all_tokens():
    with open('regey_data.csv', newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        with open('regey_tokens.csv', 'w', newline='') as csvfileout:
            csvwriter = csv.writer(csvfileout)
            for row in csvreader:
                tokens = get_org_tokens(row[0])
                for token in tokens:
                    csvwriter.writerow([token])

#used to generate "regey_dist.csv" file with frequency distribution of tokens
def get_freq_dist():
    dist = {}
    with open('regey_tokens.csv', newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        for row in csvreader:
            if len(row) == 0:
                continue
            token = row[0]
            if token == "":
                continue
            if token in dist:
                dist[token] += 1
            else:
                dist[token] = 1
    with open('regey_dist.csv', 'w', newline='') as csvfileout:
        csvwriter = csv.writer(csvfileout)
        for token in sorted(dist, key=dist.get, reverse=True):
            count = dist[token]
            csvwriter.writerow([token, count])
        
#=================================================================
#main

#returns dictionary with "org","url","rev_str","rev_num","match_score" fields
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

    dist = make_dist()
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
        #print(f"{org_tokens}, {zoom_org}, {zoom_org_tokens}, {match_score}")
        if match_score > best_match_score:
            best_match_score = match_score
            best_result = result_info
    
    best_result["match_score"] = best_match_score
    return best_result

#returns dictionary with "org","url","name","year","revenue","assets","liabilities","summed" fields
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
                    if revenue and assets and liabilities:
                        summed = round(revenue + assets - liabilities, 2)
                        return {"org": org, "url": url, "name": name, "year": year, "revenue": revenue, "assets": assets, "liabilities": liabilities, "summed": summed}
            return {"error":"could not find filing with revenue, assets and liabilities"}
    return {"error":"could not find propublica link"}

def run_single(chosen_org):
    with open('regey_data.csv', newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        for row in csvreader:
            org = row[0]
            if org == chosen_org:
                driver = get_driver()
                foundation = row[1] == "TRUE"
                if foundation:
                    print(search_foundation(driver, chosen_org))
                else:
                    print(search_company(driver, chosen_org))
                return
    print("ERROR: org not found")

# def run(filter="", limit=math.inf):
#     driver = get_driver(headless=True)

#     with open('regey_data.csv', newline='') as csvfilein:
#         csvreader = csv.reader(csvfilein)
#         with open('regey_data_out.csv', 'w', newline='') as csvfileout:
#             csvwriter = csv.writer(csvfileout)
#             i = 0
#             for row in csvreader:

#                 org = row[0]
#                 foundation = row[1] == "TRUE"

#                 if filter != "" and (filter == "foundation") != foundation:
#                     continue
#                 i += 1
#                 if i > limit:
#                     break

#                 print(search(driver, org, foundation))
#                 #csvwriter.writerow([...])

def run_companies():
    driver = get_driver(headless=True)

    #get list of already done companies
    done = []
    with open("regey_data_companies.csv", newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        for row in csvreader:
            done.append(row[0])

    with open('regey_data.csv', newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        with open('regey_data_companies.csv', 'a', newline='') as csvfileout:
            csvwriter = csv.writer(csvfileout)
            for row in csvreader:
                org = row[0]
                foundation = row[1] == "TRUE"
                if (not foundation) and (not org in done):

                    try:
                        result = search_company(driver, org)
                    except:
                        print(f"{org} caused exception")
                        return
                    
                    if not "error" in result:
                        entry = [result["org"],result["url"],result["rev_str"],result["rev_num"],result["match_score"]]
                        print(entry)
                        csvwriter.writerow(entry)
                    else:
                        print([org,result["error"]])
                        return
                    
def run_foundations():
    driver = get_driver(headless=True)

    #get list of already done companies
    done = []
    with open("regey_data_foundations.csv", newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        for row in csvreader:
            done.append(row[0])

    with open('regey_data.csv', newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        with open('regey_data_foundations.csv', 'a', newline='') as csvfileout:
            csvwriter = csv.writer(csvfileout)
            for row in csvreader:
                org = row[0]
                foundation = row[1] == "TRUE"
                if foundation and (not org in done):

                    try:
                        result = search_foundation(driver, org)
                    except:
                        print(f"{org} caused exception")
                        return
                    
                    if not "error" in result:
                        #"org","url","name","year","revenue","assets","liabilities","summed"
                        entry = [result["org"],result["url"],result["name"],result["year"],result["revenue"],result["assets"],result["liabilities"],result["summed"]]
                        print(entry)
                        csvwriter.writerow(entry)
                    else:
                        print([org,result["error"]])
                        return
#=================================================================
#revenue regexes

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

#=================================================================
#utils

def get_driver(headless=False):
    options = Options()
    options.headless = headless
    driver = webdriver.Firefox(options=options, service=FirefoxService(GeckoDriverManager().install()))
    return driver

#performs a google search and waits for results before returning them
def google_search(driver, search_string, wait):
    driver.get("https://www.google.com/")
    search_box = driver.find_element(by=By.ID, value="APjFqb")
    search_box.send_keys(search_string)
    search_box.send_keys(Keys.ENTER)
    try:
        results_element = WebDriverWait(driver, wait).until(lambda x: x.find_element(by=By.ID, value="rso"))
        results = results_element.find_elements(by=By.XPATH, value="*") #gets all direct children of an element
    except TimeoutException:
        results = []
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

#produces match score by sum totalling the scores (based on inverse frequency from distribution) of all token matches
def get_match_score(dist, org_tokens, zoom_org_tokens):
    match_score = 0 
    for org_token in org_tokens:
        if org_token in zoom_org_tokens:
            match_score += 98 - dist[org_token]
    return match_score

#turns "regey_dist.csv" into lookup table (i.e. a dictionary) and returns it
def make_dist():
    dist = {}
    with open('regey_dist.csv', newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        for row in csvreader:
            dist[row[0]] = int(row[1])
    return dist

def get_publica_revenue(rev_string):
    rev_string = re.sub(r"\$|,", "", rev_string) #remove dollars and commas
    return round(float(rev_string), 2)
#=================================================================
#scratch

#run(limit=20)
#run(filter="company", limit=20)
#run(filter="foundation", limit=20)

#run_single("AmWell")
#run_single("Abell-Hanger Foundation")
#run_single("Josiah Macy Jr. Foundation")
#run_single("Center on Budget and Policy Priorities")
#run_single("blah blah blah")
#run_single("Wartsila Energy Storage & Optimisation") #this breaks because of the ampersand
#run_single("Kelly Restaurant Group")
#run_single("Black Mountain Energy Storage")
#run_single("Ed Foundation")

#get_all_tokens()
#get_freq_dist()

#############################################

#run_companies()
run_foundations()
#run_single("Moore Foundation")