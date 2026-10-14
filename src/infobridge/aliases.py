"""Alias table: name knowledge used by the name finder and the entity resolver.

Kept small and general (common Indian nicknames, spelling variants, honorifics),
not tuned to individual people in the test data.
"""

from __future__ import annotations

# nickname -> full first name
NICKNAMES = {
    "srini": "srinivas", "venky": "venkatesh", "chinni": "chinmayi", "raju": "rajendra",
    "babu": "suresh", "sandy": "sandeep", "abhi": "abhishek", "vicky": "vikram", "subbu": "subramanyam",
}

# spelling variant -> canonical spelling (applied to every name token)
SPELLINGS = {
    "laxmi": "lakshmi", "mohd": "mohammed", "md": "mohammed", "mohammad": "mohammed", "muhammad": "mohammed",
    "sreenivas": "srinivas", "srinivasa": "srinivas", "shiva": "siva", "sathish": "satish", "swati": "swathi",
    "preeti": "preethi", "kartik": "karthik", "rahim": "raheem",
}

# words that are not part of a name: honorifics, kinship terms and titles
HONORIFICS = {
    "bhai", "anna", "akka", "garu", "ji", "sir", "madam", "maam", "sahab", "saab", "uncle", "aunty",
    "dr", "coach", "mr", "mrs", "ms", "prof", "captain",
}

# leading name parts that are not the name people are called by ("Mohammed Farhan" -> "Farhan")
NAME_PREFIXES = {"mohammed", "syed", "sri", "shri", "smt"}

# programme acronyms and their long forms
PROGRAMME_ACRONYMS = {"hmtp": "half marathon training programme"}

# organisation names that prefix event titles ("Hyderabad Runners Winter 10K")
ORG_NAMES = {"hyderabad runners", "hr"}
