#!/usr/bin/env/python 

"""
Preprocess list of strings (chapters or paragraphs of novels) **text** with spacy: Tokenization, Lemmatization
Read in json with animal words and nature words 
For each entry in **text* extract frequency of nature words
Return dictionary with {paragraph1:{nature_word_1:frequency,...},...}
"""

import sys
import json
from numpy import e
from typing_extensions import Literal
from collections import Counter
from enum import Enum

import spacy
from fastapi import FastAPI

app = FastAPI()

DE_NATURE_WORDS = "../wordlists/nature_words.json"
EN_NATURE_WORDS = "path/to/file"

class Language(Enum):
    EN = "en"
    DE = "de"

class NatureCategories(Enum):
    Animal = "animal"
    Plant = "plant"

@app.get("/")
def root():
    return{
            'service': 'ecocor-metrics',
            'version': '0.0.0'
            }
def read_json(fp):
    with open(fp, 'r') as json_in:
        loaded = json.load(json_in)
    uniques = {key: set(val) for key, val in loaded.items()}
    return uniques


def initialize_de():
     global nlp
     nlp = spacy.load('de_core_news_sm')
     return read_json(DE_NATURE_WORDS)

def initialize_en():
    global nlp
    nlp = spacy.load('en_core_web_sm')
    return read_json(EN_NATURE_WORDS)

def setup_analysis_components(language: str):
    languages = {x.value for x in Language}
    assert language in languages, f"Language must be one of the following: {languages}" 

    if language == Language.DE.value:
        nature_words = initialize_de()
    elif language == Language.EN.value:
        nature_words = initialize_en()
    return nature_words

# can we get a list here? or hug magic
# language should be in ?language=de and should be read automatically here
@app.post("/metrics/")
def process_text(text: list[str], language:str) -> dict[str, dict[str, dict[str,int]]]:
    nature_words = setup_analysis_components(language)
    # annotate
    segment_to_frq = {}
    for i, segment in enumerate(nlp.pipe(text, disable=["parser", "ner"])):
        lemmatized_text = [token.lemma_ for token in segment]
        vocabulary = set(lemmatized_text)
        counted = Counter(lemmatized_text)

        result = {}
        # for word in nature_words[nature_category]:
        for description, word_list in nature_words.items():
            category_result = {}
            intersect = word_list.intersection(vocabulary)
            for word in intersect:
                category_result[word] = counted[word]
            result[description] = category_result
        segment_to_frq[i] = result
    return segment_to_frq

# TODO add option for selecting which nature category to get the frequencies for and only pass that to the process segment function 


if __name__ == '__main__':
    args = sys.argv
    if len(args) != 2:
        print(f"usage: {args[0]} path/to/test/file")
        exit(-1)
    with open(args[1]) as txt_in:
        segments = txt_in.readlines()

    process_text(segments, "de")
