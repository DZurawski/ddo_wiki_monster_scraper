"""
main.py
Given a quest name, return info about monsters that show up in that quest.
Type in a quest name into the console. Monster info is printed in the console.
"""

import os
import urllib
import difflib
from typing import Dict, Optional, Sequence, List

import yaml
import requests
import bs4
import pandas as pd

import utils


# noinspection PyMethodMayBeStatic
class DDOWikiScraper:
    """
    Web scraper focusing on the DDO wiki. Given a quest name, return info about monsters that show up in that quest.
    """
    def __init__(self, configs: Dict) -> None:
        """
        Initialize this class with configs.
        """
        self.configs = configs

    def get_monsters_in_quest(self, quest_name: str) -> pd.DataFrame:
        """
        Get monster info about the monsters that show up in the quest matching to quest_name.
        """
        # Get the quest that most closely matches the supplied quest_name.
        quest_urls = self.get_quest_urls()
        closest_matching_quest = self.get_closest_matching_quest(quest_name, list(quest_urls.keys()))
        print(f"The closest matching quest was: {closest_matching_quest}.")

        # Extract the monster_info using the closest matching quest to the inputted quest name.
        monster_urls = self.get_monster_urls(quest_urls[closest_matching_quest])
        monster_info = [{**{"Name": key}, **self.get_monster_info(value)} for key, value in monster_urls.items()]

        # Clean up the monster_info into a DataFrame.
        df = pd.DataFrame(monster_info)
        if "Alignment" in df.columns:
            df["Lawfulness"] = self.get_lawfulness(df["Alignment"])
            df["Goodness"] = self.get_goodness(df["Alignment"])
            df = df.drop("Alignment", axis=1)
        df = df.sort_values(["Lawfulness", "Goodness", "Race", "Name"])
        df = df.reset_index(drop=True)

        return df

    def get_quest_urls(self, url: Optional[str] = None) -> Dict[str, str]:
        """
        Get the set of all quests in DDO from the DDO wiki.
        Mapping (Quest Name -> URL of the quest's page in the DDO wiki)
        """
        # Get the table of quest information.
        if url is None:
            url = self.configs["ddo_wiki_quest_url"]
        response = requests.get(url=url)
        soup = bs4.BeautifulSoup(response.content, 'html.parser')
        header = soup.find(id=self.configs["level"]).parent
        table = header.find_next_sibling()

        # Quest names are in the first column of the HTML table.
        quest_names_column = table.select('table tr td:nth-of-type(1)')

        # Make a mapping (quest name -> quest page url).
        quest_urls = dict()
        for quest_name in quest_names_column:
            quest_name = quest_name.find("a")
            title = quest_name["title"]
            href = quest_name["href"]
            quest_urls[title] = urllib.parse.urljoin(self.configs["ddo_wiki_base_url"], href)

        return quest_urls

    def get_monster_urls(self, url: str) -> Dict[str, str]:
        """
        Get the mapping (monster name -> ddo wiki url of the monster's entry) from a quest page url.
        The returned monsters all show up in the quest.
        """
        # Get the table of monsters that show up in the quest.
        response = requests.get(url=url)
        soup = bs4.BeautifulSoup(response.content, 'html.parser')
        header = soup.find(id="Monsters").parent
        table = header.find_next_sibling()

        # Monster names are in the first column of the HTML table.
        monster_names_column = table.select('table tr td:nth-of-type(1)')

        # Make a mapping (monster name -> monster page url).
        monster_urls = dict()
        for monster_name in monster_names_column:
            monster_name = monster_name.find("a")
            title = monster_name["title"]
            href = monster_name["href"]
            monster_urls[title] = urllib.parse.urljoin(self.configs["ddo_wiki_base_url"], href)

        return monster_urls

    def get_monster_info(self, url: str) -> Dict[str, str]:
        """
        Extract a dictionary of monster data from the supplied url.
        """
        # Load in the text containing monster information from the monster page url.
        response = requests.get(url=url)
        soup = bs4.BeautifulSoup(response.content, 'html.parser')
        text = soup.find(id="mw-content-text").text

        # The column names of information that we want to extract about the monster.
        keywords = self.configs["columns"]

        # Clean the lines and remove lines that do not matter.
        lines = text.split("\n")
        lines = (line.strip() for line in lines)
        lines = (line for line in lines if line)
        lines = [line for line in lines if line.startswith(tuple(keywords))]

        # Get raw information about an aspect of the monster.
        monster_info = dict()
        for keyword in keywords:
            for line in lines:
                if line.startswith(keyword):
                    monster_info[keyword] = line
                    break
            else:
                monster_info[keyword] = ""

        # Clean up the information found in the monster_info.
        for key, value in monster_info.items():
            value = value.replace(key, "")
            value = value.replace(":", "")
            value = value.replace("(List)", "")
            value = value.strip()
            monster_info[key] = value

        return monster_info

    def get_closest_matching_quest(self, quest_name: str, candidate_names: Sequence[str]) -> str:
        """
        Given a quest name and a set of candidate quest names, return the candidate that is most similar to the quest
        name. Similarity uses the edit distance between the quest name string and the candidate string.
        """
        # Clean up the input variables.
        quest_name = str(quest_name)
        candidate_names = [str(_) for _ in candidate_names]

        # Collect the similarity scores (edit distance) of the candidates.
        # The score in candidate_scores at index i corresponds with the name in candidate_names at index i.
        candidate_scores = []
        for candidate_name in candidate_names:
            if candidate_name is None:
                candidate_name = ""
            candidate_name = str(candidate_name)
            similarity = difflib.SequenceMatcher(
                None, quest_name.lower().strip(), candidate_name.lower().strip()).ratio()
            candidate_scores.append(similarity)

        # Sort the candidates by their similarity scores.
        candidates = sorted(list(zip(candidate_scores, candidate_names)), key=lambda x: x[0])

        # Return the candidate name with the highest similarity score.
        return [y for x, y in candidates][-1]

    def get_lawfulness(self, alignments: Sequence[str]) -> List[str]:
        """
        Given a list of strings representing alignments, extract the law vs. chaos parts and return them as a list.
        We expect strings in alignments to look like one of these:
            (Lawful Good, Lawful Evil, Chaotic Good, Chaotic Evil, True Neutral, Neutral Good, Neutral Evil)
        """
        lawfulness = []
        for alignment in alignments:
            if alignment:
                alignment = alignment.strip()
                # The "True Neutral" alignment is parsed differently than the other alignments.
                # This is because it doesn't conform to the pattern:
                # "[law vs chaos] [good vs evil]" - "Chaotic Good".
                if alignment.lower() == "true neutral":
                    alignment = "Neutral Neutral"

                split = alignment.split(" ")

                if len(split) < 1:
                    lawfulness.append("")
                elif len(split) == 1:
                    lawfulness.append(split[0])
                else:
                    # We only want the first part. "Chaotic Good" -> "Chaotic".
                    lawfulness.append(split[0])
            else:
                lawfulness.append("")

        return lawfulness

    def get_goodness(self, alignments: Sequence[str]) -> List[str]:
        """
        Given a list of strings representing alignments, extract the good vs. evil parts and return them as a list.
        We expect strings in alignments to look like one of these:
            (Lawful Good, Lawful Evil, Chaotic Good, Chaotic Evil, True Neutral, Neutral Good, Neutral Evil)
        """
        goodness = []
        for alignment in alignments:
            if alignment:
                alignment = alignment.strip()
                # The "True Neutral" alignment is parsed differently than the other alignments.
                # This is because it doesn't conform to the pattern:
                # "[law vs chaos] [good vs evil]" - "Chaotic Good".
                if alignment.lower() == "true neutral":
                    alignment = "Neutral Neutral"

                split = alignment.split(" ")

                if len(split) < 1:
                    goodness.append("")
                elif len(split) == 1:
                    goodness.append(split[0])
                else:
                    # We only want the second part. "Chaotic Good" -> "Good".
                    goodness.append(split[1])
            else:
                goodness.append("")
        return goodness


def main_loop() -> None:
    """
    The main loop of this script.
    1. Ask the user to type in the name of a quest.
    2. Display the monster information of that quest.
    3. Repeat the prior steps until the user inputs "quit" to leave the loop.
    """
    while True:
        # Ask the user to supply a quest name.
        print("\nPlease enter a quest name. Enter 'quit' to leave.")
        user_input = input("Quest Name: ")
        user_input = user_input.strip().lower()

        # If the user inputted a quit signal, then break.
        if user_input in ("q", "quit", "exit"):
            break

        # Load the configs.
        root = utils.get_project_root()
        configs_path = os.path.realpath(os.path.join(root, "configs.yaml"))
        try:
            with open(configs_path, "r") as file:
                configs = yaml.safe_load(file)
        except FileNotFoundError:
            print(f"Could not find {configs_path}. Make sure that it exists.")
            break

        # Get the monsters found in the user-specified quest. Display their information.
        scraper = DDOWikiScraper(configs)
        df = scraper.get_monsters_in_quest(user_input)
        print(df)


def main() -> None:
    """
    The main function. Set a few options and then start the main loop.
    """
    print("Starting.")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    main_loop()
    print("Ending.")


if __name__ == '__main__':
    main()
