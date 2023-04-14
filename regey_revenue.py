from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import NoSuchElementException

from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options
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

#this was used to generate regey_tokens.csv in order to create a frequency distribution 
#this distribution was then used to create an effective token_filter_list
def get_all_tokens():
    with open('regey_data.csv', newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        with open('regey_tokens.csv', 'w') as csvfileout:
            for row in csvreader:
                tokens = get_org_tokens(row[0])
                for token in tokens:
                    csvfileout.write(f"{token} ")

#=================================================================
#main

def search(driver, org, foundation):
    if foundation:
        #maybe we should replace spaces with "+"s in org before searching...
        driver.get(f"https://www.google.com/search?q={org}+990+propublica")

    else:
        driver.get(f"https://www.google.com/search?q={org}+annual+revenue+zoominfo")

        results_element = driver.find_element(by=By.ID, value="rso")
        results = results_element.find_elements(by=By.XPATH, value="*")

        zoom_results = []
        for result in results:
            try:
                cite = result.find_element(by=By.TAG_NAME, value="cite")
            except NoSuchElementException:
                continue
            url_string = cite.text
            if (url_string != ""):
                url_tokens = url_string.split(" › ")
                if url_tokens[0] == "https://www.zoominfo.com":
                    zoom_results.append((result, url_tokens[1]))
        
        if len(zoom_results) == 0:
            return {"url": "", "revenue": 0}

        counts = []
        for entry in zoom_results:
            result = entry[0]
            zoom_token = entry[1]
            org_tokens = get_filtered_org_tokens(org)
            count = 0
            for org_token in org_tokens:
                if org_token in zoom_token:
                    count += 1
            counts.append(count)

        filtered_results = []
        max_count = max(counts)
        for i in range(len(counts)):
            count = counts[i]
            zoom_result = zoom_results[i][0]
            if count == max_count:
                filtered_results.append(zoom_result)

        result_dicts = []
        for result in filtered_results:
            result_dict = {}
            result_dict["url"] = result.find_element(by=By.TAG_NAME, value="a").get_attribute("href")
            result_dict["list"] = []

            rev_groups = rev_regex_grouped.findall(result.text)
            rev_strings = rev_regex.findall(result.text)

            for i in range(len(rev_groups)):
                rev_group = rev_groups[i]
                rev_string = rev_strings[i]

                revenue = float(rev_group[1])

                match rev_group[2]:
                    case "K":
                        revenue *= 1000
                    case "M":
                        revenue *= 1000000
                    case "B":
                        revenue *= 1000000000
                if rev_group[0] == "<":
                    revenue *= 0.8

                group_dict = {}
                group_dict["rev_string"] = rev_string
                group_dict["revenue"] = revenue
                result_dict["list"].append(group_dict)

            result_dicts.append(result_dict)
        
        max_url = ""
        max_string = ""
        max_revenue = 0
        for result_dict in result_dicts:
            for rev in result_dict["list"]:
                if rev["revenue"] > max_revenue:
                    max_url = result_dict["url"]
                    max_string = rev["rev_string"]
                    max_revenue = rev["revenue"]

        return {"url": max_url, "revenue": max_revenue}

def run_single(chosen_org):
    with open('regey_data.csv', newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        for row in csvreader:
            org = row[0]
            if org == chosen_org:
                driver = get_driver()
                foundation = row[1] == "TRUE"
                
                if not foundation:
                    result = search(driver, org, False)
                    if not result["url"] == "":
                        print([org, result["url"], result["revenue"]])
                    else:
                        print([org, "ERROR: empty url"])
                else:
                    print([org, "ERROR: foundation"])

                return
            
    print("ERROR: org not found")

def run(filter="", limit=math.inf):
    driver = get_driver(headless=True)

    with open('regey_data.csv', newline='') as csvfilein:
        csvreader = csv.reader(csvfilein)
        with open('regey_data_out.csv', 'w', newline='') as csvfileout:
            csvwriter = csv.writer(csvfileout)
            i = 0
            for row in csvreader:

                org = row[0]
                foundation = row[1] == "TRUE"

                if filter != "" and (filter == "foundation") != foundation:
                    continue
                i += 1
                if i > limit:
                    break

                if not foundation:
                    result = search(driver, org, False)
                    if not result["url"] == "":
                        csvwriter.writerow([org, result["url"], result["revenue"]])
                    else:
                        csvwriter.writerow([org, "ERROR: empty url"])
                else:
                    csvwriter.writerow([org, "ERROR: foundation"])

#=================================================================
#get_filtered_org_tokens

#based on frequency distribution generated from regey_tokens.csv
token_filter_list = ["foundation","the","inc","group","of","association","and","fund","for","llp","llc","international","corporation","company","co"]

#lowercases org (first column in regey_data.csv) and then splits on all non alpha-numeric characters
def get_org_tokens(org):
    lower_org = org.lower()
    tokens = re.findall(r'\w+', lower_org)
    return tokens

#runs get_org_tokens on org (first column in regey_data.csv) and removes any which belong to token_filter_list
def get_filtered_org_tokens(org):
    return list(filter(lambda token : not token in token_filter_list, get_org_tokens(org)))

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

#=================================================================
#utils

def get_driver(headless=False):
    options = Options()
    options.headless = headless
    driver = webdriver.Firefox(options=options, service=FirefoxService(GeckoDriverManager().install()))
    return driver

#=================================================================
#scratch

#run(limit=20)
#run(filter="company", limit=20)
#run(filter="foundation", limit=20)

#run_single("AmWell")
#run_single("Josiah Macy Jr. Foundation")
#run_single("Center on Budget and Policy Priorities")
#run_single("blah blah blah")