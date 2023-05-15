#!/usr/bin/env/python 

"""
Preprocess list of strings (chapters or paragraphs of novels) **text** with spacy: Tokenization, Lemmatization
Retrieve word info dict from given URL: {list_lemma: {ID:val},...}
    this format is extendable with e.g. PoS info
For each entry in **text* extract frequency of words in word info dict
Return dictionary with {list_lemma:{ID: val, segment_frequency: {chapter_ID: frequency,...,} overall_frequency: frequency},...}
"""

import sys
import requests
from collections import Counter
from enum import Enum

import spacy
from fastapi import FastAPI

app = FastAPI()

class Language(Enum):
    EN = "en"
    DE = "de"

SEGMENT_FRQ = "segment_frequency"
OVERALL_FRQ = "overall_frequency"

@app.get("/")
def root():
    return{
            'service': 'ecocor-metrics',
            'version': '0.0.0'
            }

#TODO: check if the file belongs to a certain **secure** URL 
def read_word_list(url):
    response = requests.get(url).json()
    return response

def initialize_de():
     global nlp
     nlp = spacy.load('de_core_news_sm')

def initialize_en():
    global nlp
    nlp = spacy.load('en_core_web_sm')

def setup_analysis_components(language: str, resource_url:str) -> dict[str, dict[str,str]]:
    languages = {x.value for x in Language}
    assert language in languages, f"Language must be one of the following: {languages}" 
    
    id_word_info_dict = read_word_list(resource_url)

    if language == Language.DE.value:
        initialize_de()
    elif language == Language.EN.value:
        initialize_en()

    return id_word_info_dict

# can we get a list here? or hug magic
# language should be in ?language=de and should be read automatically here
# how is the resouce url (word list) passed?
@app.post("/metrics/")
def process_text(text: list[str], language:str, resource_url:str) -> dict[str, dict[str, dict[str,int]]]:
    word_info = setup_analysis_components(language, resource_url)
    unique_words = set(word_info.keys())

    # annotate
    word_to_chapter_frq = {}
    for i, segment in enumerate(nlp.pipe(text, disable=["parser", "ner"])):
        lemmatized_text = [token.lemma_ for token in segment]

        # count and intersect
        vocabulary = set(lemmatized_text)
        counted = Counter(lemmatized_text)
        intersect = unique_words.intersection(vocabulary)

        # save frequencies
        for word in intersect:
            if word not in word_to_chapter_frq:
                word_to_chapter_frq[word] = word_info[word]
                word_to_chapter_frq[word][SEGMENT_FRQ] = {}
            word_to_chapter_frq[word][SEGMENT_FRQ][i] = counted[word]
    
    for word, info in word_to_chapter_frq.items():
        word_to_chapter_frq[word][OVERALL_FRQ] = sum(info[SEGMENT_FRQ].values())
    print(word_to_chapter_frq)
    return word_to_chapter_frq 

if __name__ == '__main__':
    args = sys.argv
    if len(args) != 4:
        print(f"usage: {args[0]} path/to/test/file en||de url/to/wordlist")
        exit(-1)
    with open(args[1]) as txt_in:
        segments = txt_in.readlines()

    process_text(segments, args[2], args[3])
