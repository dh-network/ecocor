"""
ecocor_md_to_tei.py — EcoCor Markdown-to-TEI Conversion Script
===============================================================

This script converts prose texts marked up with the lightweight EcoCor
markdown syntax into TEI/XML files conforming to the ELTeC schema.

PIPELINE OVERVIEW
-----------------
1. Read the metadata Excel table (one row per work).
2. For each row, locate the corresponding `.txt` source file in `ecocorMD/`.
3. Parse the structural markers in the text and build a TEI/XML tree by
   populating a pre-filled TEI stub (`EcoStub.xml`).
4. Enrich the tree with metadata: title, author (formatted via Wikidata),
   publication year, word count, and unique XML identifiers.
5. Write the finished TEI document to `tei/2026/{lang}/{folder}/`.

ECOCOR MARKDOWN SYNTAX (summary)
---------------------------------
  #          Part / highest-order division (closes front matter)
  ##         Chapter / subdivision
  ###        Subchapter / sub-subdivision
  ^^^        Front-matter delimiter (always prepended automatically)
  $          Back-matter delimiter (appendices, glossaries, etc.)

  All other non-empty lines become <p> elements.

USAGE
-----
  Run from inside the `corpus/` directory:

      python ecocor_md_to_tei.py

DEPENDENCIES
------------
  beautifulsoup4, pandas, lxml (or html.parser), wikidataintegrator, openpyxl

OUTPUT
------
  tei/2026/{de|en}/{has_text|no_text_yet}/{filename}.xml
"""

# ---------------------------------------------------------------------------
# Standard-library and third-party imports
# ---------------------------------------------------------------------------
from bs4 import BeautifulSoup   # XML/HTML parsing and tree building
import pandas as pd             # Reading the metadata Excel table
import re                       # Regex-based word counting
import os                       # File-existence checks and path handling
import wikidataintegrator as wdi  # Querying Wikidata's SPARQL endpoint

# ---------------------------------------------------------------------------
# Path constants
# All paths are relative to the `corpus/` directory (the script's working
# directory).  Edit these if the project layout changes.
# ---------------------------------------------------------------------------
METADATA_FILE = "aux/EcoCorMetadataTest26.xlsx"  # Metadata for all works
MARKDOWN_DIR  = "ecocorMD"                        # Source .txt files
TEI_STUB      = "aux/EcoStub.xml"                 # Pre-filled TEI template
OUTPUT_BASE   = "tei/2026"                         # Root of the output tree

# ---------------------------------------------------------------------------
# Wikidata helper functions
# ---------------------------------------------------------------------------
# These are module-level functions (not methods) because they encapsulate
# network I/O that does not depend on any TEI document state.  They must be
# defined *before* the TEI class because the class calls them.

def query_wikidata_for_author_data(auth_wikidata_id):
    """
    Retrieve an author's family name, given name, birth date, and death date
    from the Wikidata SPARQL endpoint.

    Parameters
    ----------
    auth_wikidata_id : str
        A bare Wikidata item identifier, e.g. ``"Q100876"`` (no URL prefix).

    Returns
    -------
    dict
        The raw JSON response from the SPARQL endpoint.  Relevant data is
        under ``result['results']['bindings']``.
    """
    sparql_query = f"""
    SELECT ?family_nameLabel ?given_nameLabel ?dob ?dod
    WHERE {{
      wd:{auth_wikidata_id} wdt:P735 ?given_name.
      wd:{auth_wikidata_id} wdt:P734 ?family_name.
      wd:{auth_wikidata_id} wdt:P569 ?dob.
      wd:{auth_wikidata_id} wdt:P570 ?dod.

      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }}
    }}
    """
    return wdi.wdi_core.WDItemEngine.execute_sparql_query(sparql_query)


def get_author_correct_format(wikidata_id):
    """
    Return an author name formatted in ELTeC style:
    ``"Surname, Forename (YYYY-YYYY)"``.

    The format matches the ELTeC convention used in corpora such as ELTeC-deu
    and ELTeC-eng, e.g. ``"Forster, Edward Morgan (1879-1970)"``.

    Parameters
    ----------
    wikidata_id : str
        Either a bare Wikidata ID (``"Q100876"``) or a full entity URL
        (``"https://www.wikidata.org/entity/Q100876"``).  The URL prefix is
        stripped automatically.

    Returns
    -------
    str
        Formatted author name string.
    """
    # Strip the URL prefix if present, leaving just the Q-identifier
    wikidata_id = wikidata_id.replace("https://www.wikidata.org/entity/", "")

    result = query_wikidata_for_author_data(wikidata_id)
    for item in result["results"]["bindings"]:
        surname   = item["family_nameLabel"]["value"]
        given     = item["given_nameLabel"]["value"]
        yob       = item["dob"]["value"][:4]   # ISO date → keep year only
        yod       = item["dod"]["value"][:4]

    return f"{surname}, {given} ({yob}-{yod})"


# ---------------------------------------------------------------------------
# TEI class
# ---------------------------------------------------------------------------

class TEI:
    """
    Represents a single TEI document being built from an EcoCor markdown file.

    Class-level attributes are shared across all instances and persist for the
    lifetime of the conversion run:

    langmap : dict
        Maps the verbose language labels used in the metadata table to ISO
        639-1 two-letter codes.

    authors_formatted : dict
        Cache of ``{wikidata_url: formatted_name_string}`` pairs.  Prevents
        redundant network requests when the same author appears in multiple
        rows of the metadata table.

    teiid : int
        Global counter for generating unique document identifiers.  Must be
        reset to 1 before each full conversion run (see ``main()``).
    """

    # --- class-level attributes -------------------------------------------

    langmap = {
        "Englisch": "en",
        "Deutsch":  "de",
        "Orig. Franz. / Englisch": "en",
    }

    authors_formatted = {}  # Wikidata URL → "Surname, Forename (YYYY-YYYY)"
    teiid = 1               # Incremented by update_tree() after each document

    # --- constructor -------------------------------------------------------

    def __init__(self, title, author, sourcetxtname):
        """
        Initialise a TEI document object.

        Parameters
        ----------
        title : str
            The work's title (from the metadata table).
        author : str
            The author's name as it appears in the metadata table.
        sourcetxtname : str
            The filename (with or without ``.txt`` extension) of the EcoCor
            markdown source.  Pass ``"NoSourceTxt"`` when no source is
            available yet.
        """
        print(title)  # Progress indicator (preserved from original notebook)

        self.title  = title
        self.author = author
        self.empty  = False  # True if no markdown source file exists

        # Strip the .txt extension so we can construct both input and output
        # paths from the same base name
        self.sourcetxtname = sourcetxtname.replace(".txt", "")

        if sourcetxtname != "NoSourceTxt":
            self.sourcetxtpath  = f"{MARKDOWN_DIR}/{self.sourcetxtname}.txt"
            self.outputfilename = self.sourcetxtname
            if not os.path.exists(self.sourcetxtpath):
                # The filename was listed in metadata but the file is missing
                self.empty = True
        else:
            # No source file is expected for this entry
            self.empty          = True
            self.sourcetxtpath  = None
            self.outputfilename = title  # Fall back to the title as filename

        # XML does not allow spaces in attribute values such as xml:id;
        # also avoids spaces in file system paths
        self.outputfilename = self.outputfilename.replace(" ", "")

        # Metadata fields — populated by row_to_tei() after construction
        self.year           = None
        self.wikidataid     = None   # Wikidata entity URL for the *work*
        self.wikidataidauth = None   # Wikidata entity URL for the *author*
        self.lang           = "Undefined"

        # Load the TEI stub as a mutable BeautifulSoup tree.
        # Every document starts from a fresh copy of the stub.
        with open(TEI_STUB) as stub_file:
            self.tree = BeautifulSoup(stub_file, "xml")

        self.len_words = 0  # Filled by add_text() / measure_length()

    # --- language helper ---------------------------------------------------

    def isolang(self):
        """
        Return the ISO 639-1 language code for this document.

        Looks up ``self.lang`` in the class-level ``langmap``.  Returns
        ``None`` if the language string is not recognised.
        """
        return self.langmap.get(self.lang)

    # --- word-count helper ------------------------------------------------

    def measure_length(self, text):
        """
        Count the approximate number of words in *text*.

        Uses the regex pattern ``r'\\b\\w.*?\\b'``, which matches sequences
        starting at a word boundary and ending at another.  This slightly
        over-counts compared to a simple whitespace split but is consistent
        with the original notebook behaviour and is applied to the full raw
        text (including structural markers).

        Parameters
        ----------
        text : str
            The full source text as a single string.

        Returns
        -------
        int
            Approximate word count.
        """
        return len(re.findall(r"\b\w.*?\b", text))

    # --- author-name fallback --------------------------------------------

    def heur_conv(self, auth_string):
        """
        Heuristic conversion of an author name for works without a Wikidata
        entry.

        Takes the last "character slice" of ``auth_string`` as the probable
        surname and the rest as forenames, returning ``"surname, rest"``.

        Note: ``auth_string`` is a raw string from the metadata cell.
        Python's ``[-1:]`` slice on a string returns the last *character*,
        so this is a best-effort fallback rather than a robust parser.

        Parameters
        ----------
        auth_string : str
            Author name as it appears in the metadata table.

        Returns
        -------
        str
            Reformatted name string.
        """
        probable_surname = auth_string[-1:]   # last character of the string
        rest             = auth_string[:-1]   # everything except the last character
        return f"{probable_surname}, {rest}"

    # --- Wikidata enrichment ----------------------------------------------

    def wikify_tree(self, treetitle, treeauthor):
        """
        Populate the ``<title>`` and ``<author>`` elements with Wikidata
        references.

        The ``<author>`` element is cleared and refilled with a correctly
        formatted name string, then given a ``ref`` attribute pointing to the
        author's Wikidata entity.  The ``<title>`` element receives a ``ref``
        attribute pointing to the work's Wikidata entity.

        Author name formatting is retrieved from Wikidata when a valid entity
        URL is available, and is cached in ``TEI.authors_formatted`` to avoid
        duplicate network requests.  When no Wikidata entry exists,
        ``heur_conv()`` is used as a fallback.

        Parameters
        ----------
        treetitle  : bs4.element.Tag  — the ``<title>`` element in the stub
        treeauthor : bs4.element.Tag  — the ``<author>`` element in the stub
        """
        treeauthor.clear()  # Remove the placeholder text from the stub

        if "entity/Q" not in self.wikidataidauth:
            # No valid Wikidata entity URL → fall back to heuristic conversion
            auth_corr_format = self.heur_conv(self.author)
        elif self.wikidataidauth not in TEI.authors_formatted:
            # First time we see this author: fetch from Wikidata and cache
            auth_corr_format = get_author_correct_format(self.wikidataidauth)
            TEI.authors_formatted[self.wikidataidauth] = auth_corr_format
        else:
            # Already cached from an earlier row in the same run
            auth_corr_format = TEI.authors_formatted[self.wikidataidauth]

        treeauthor.append(auth_corr_format)
        treeauthor["ref"] = self.wikidataidauth  # author Wikidata URI
        treetitle["ref"]  = self.wikidataid      # work Wikidata URI

    # --- structural-marker detection helpers ------------------------------
    # Each helper receives a single line from the markdown source and returns
    # True if the line is the corresponding structural marker.

    def checkpartheader(self, paragraph):
        """True if *paragraph* is a part/group header (``#`` but not ``##``)."""
        return paragraph.startswith("#") and not paragraph.startswith("##")

    def checkchapterheader(self, paragraph):
        """True if *paragraph* is a chapter header (``##`` but not ``###``)."""
        return paragraph.startswith("##") and not paragraph.startswith("###")

    def checksubchapterheader(self, paragraph):
        """True if *paragraph* is a subchapter header (``###``)."""
        return paragraph.startswith("###")

    def checkfront(self, paragraph):
        """True if *paragraph* is the front-matter delimiter (``^^^``)."""
        return paragraph.startswith("^^^")

    def checkback(self, paragraph):
        """True if *paragraph* is the back-matter delimiter (``$``)."""
        return paragraph.startswith("$")

    # --- ID generation ----------------------------------------------------

    def get_full_id(self):
        """
        Return the document-level XML identifier, e.g. ``eco_de_000001``.

        The zero-padding adapts to the magnitude of ``TEI.teiid``:
          - teiid  1–9  → 5 leading zeros  (e.g. ``000001``)
          - teiid 10+   → 4 leading zeros  (e.g. ``000010``)
        """
        numzeros = 5 if TEI.teiid < 10 else 4
        return f"eco_{self.isolang()}_{'0' * numzeros}{TEI.teiid}"

    def get_paragraph_id(self, count):
        """
        Return the ``xml:id`` for paragraph number *count*.

        IDs are spaced by 10 (``count * 10``) to leave room for future
        insertions without renumbering the whole sequence.
        E.g. the first paragraph of document ``eco_de_000001`` gets
        ``eco_de_000001_10``, the second ``eco_de_000001_20``, etc.

        Parameters
        ----------
        count : int
            1-based paragraph counter maintained inside ``add_text()``.
        """
        return f"{self.get_full_id()}_{count * 10}"

    # --- core text-parsing method -----------------------------------------

    def add_text(self):
        """
        Parse the EcoCor markdown source and build the ``<text>`` subtree.

        A ``^^^`` sentinel is always prepended so that any content before
        the first ``#`` marker ends up inside a ``<front>`` element.

        The source files use soft line-wrapping: a single newline within a
        paragraph is merely a typographic break in the editor, not a semantic
        boundary.  A blank line marks the end of a logical paragraph, and a
        structural marker line always ends the current paragraph too — even
        when it appears directly after body text with only a single newline
        (e.g. ``"ENDE\\n$"``).  Within a paragraph, soft-wrapped lines are
        joined with a single space before the text is inserted into ``<p>``.

        Structural logic
        ----------------
        - ``^^^`` → open a ``<front>`` element; plain text after it goes
          into ``<p>`` children of ``<front>``.
        - ``#``   → open a ``<div type="group">``; subsequent chapter divs
          are appended here until the next group starts.
        - ``##``  → open a ``<div type="chapter">`` inside the current group.
        - ``###`` → open a ``<div type="subchapter">`` inside the current
          chapter.
        - ``$``   → open a ``<back>`` element; plain text after it goes into
          ``<p>`` children of ``<back>``.
        - Any other non-empty block → one ``<p xml:id="...">`` appended to the
          currently active container element (front, group, chapter,
          subchapter, or back).

        After parsing, the method appends ``<body>`` (and ``<back>`` if
        present) to the ``<text>`` element of the stub tree, and stores
        the total word count in ``self.len_words``.

        Returns
        -------
        str or None
            ``"NoText"`` if no source file could be found; ``None`` on
            success.
        """
        # Locate the <text> element in the stub and clear its placeholder content
        teitext = self.tree.find("text")
        teitext.clear()

        # The <body> container is always created, even for empty documents
        body = self.tree.new_tag("body")

        # toptag tracks the element that receives new <div type="chapter"> nodes.
        # It starts as <body> and is updated whenever a new <div type="group">
        # is opened.
        toptag     = body
        currentdiv = body   # the element that receives <p> paragraphs
        back       = None   # created on demand when '$' is encountered
        chapter    = None   # the current <div type="chapter">, for subchapters

        # Guard: abort gracefully if there is no source file
        if self.sourcetxtpath is None:
            self.empty = True
            return "NoText"
        if not os.path.exists(self.sourcetxtpath):
            self.empty = True
            return "NoText"

        # Read the entire file as a single string
        with open(self.sourcetxtpath) as source_file:
            raw_content = source_file.read()

        # Always prepend the front-matter sentinel.  This ensures that
        # everything before the first '#' marker ends up inside <front>.
        raw_content = "^^^\n" + raw_content

        # Word count is measured on the entire raw text (including markers)
        self.len_words = self.measure_length(raw_content)

        # Build the list of logical units to iterate over using a small
        # state machine that walks the text line by line.  Three rules apply:
        #
        #   1. Blank line → flush whatever paragraph text has accumulated so far.
        #   2. Structural marker line (#, ##, ###, ^^^, $) → flush any pending
        #      paragraph text, then add the marker as its own standalone entry.
        #      This guarantees markers are always isolated even when the source
        #      file places them immediately after body text with only a single
        #      newline (e.g. "ENDE\n$").
        #   3. Any other line → append to the current paragraph accumulator;
        #      it will be joined with the preceding lines using a space, so
        #      soft editor line-wraps do not produce spurious <p> elements.
        lines = raw_content.split("\n")
        paragraphs = []
        current_lines = []   # lines being accumulated for the current paragraph

        for line in lines:
            stripped = line.strip()
            is_marker = stripped.startswith(("#", "^^^", "$"))

            if not stripped:
                # Blank line — end of the current paragraph (if any)
                if current_lines:
                    paragraphs.append(" ".join(current_lines))
                    current_lines = []
            elif is_marker:
                # Marker line — flush pending text, then add marker on its own
                if current_lines:
                    paragraphs.append(" ".join(current_lines))
                    current_lines = []
                paragraphs.append(stripped)
            else:
                # Regular text line — accumulate (joined with space on flush)
                current_lines.append(stripped)

        # Flush any remaining text at the end of the file
        if current_lines:
            paragraphs.append(" ".join(current_lines))

        # Paragraph counter — used to generate unique xml:id values
        pcount = 1

        for paragraph in paragraphs:

            if self.checksubchapterheader(paragraph):
                # ### → <div type="subchapter"> inside the current chapter
                div  = self.tree.new_tag("div")
                head = self.tree.new_tag("head")
                head.append(paragraph.strip("#"))
                div["type"] = "subchapter"
                div.append(head)
                chapter.append(div)   # nest under the current chapter div
                currentdiv = div

            elif self.checkchapterheader(paragraph):
                # ## → <div type="chapter"> inside the current group (toptag)
                div  = self.tree.new_tag("div")
                head = self.tree.new_tag("head")
                head.append(paragraph.strip("#"))
                div["type"] = "chapter"
                div.append(head)
                toptag.append(div)
                chapter    = div   # remember for potential subchapters
                currentdiv = div

            elif self.checkpartheader(paragraph):
                # # → <div type="group"> directly under <body>
                div  = self.tree.new_tag("div")
                head = self.tree.new_tag("head")
                head.append(paragraph.strip("#"))
                div["type"] = "group"
                div.append(head)
                body.append(div)
                toptag     = div   # future chapters nest inside this group
                currentdiv = div

            elif self.checkfront(paragraph):
                # ^^^ → open the <front> element
                front = self.tree.new_tag("front")
                p     = self.tree.new_tag("p")
                p["xml:id"] = self.get_paragraph_id(pcount)
                pcount += 1
                # Strip the sentinel characters and surrounding whitespace
                p.append(paragraph.strip("^ \n"))
                # Only add the <p> if there is actual content on this line
                if len(paragraph.strip("^")) > 0:
                    front.append(p)
                teitext.append(front)
                currentdiv = front

            elif self.checkback(paragraph):
                # $ → open the <back> element
                back = self.tree.new_tag("back")
                p    = self.tree.new_tag("p")
                p["xml:id"] = self.get_paragraph_id(pcount)
                pcount += 1
                p.append(paragraph.strip("$ \n"))
                if len(paragraph.strip("$")) > 0:
                    back.append(p)
                currentdiv = back

            else:
                # Plain text block → one <p> in the current container.
                # Blank blocks are already excluded by the pre-processing above,
                # but the strip-guard is kept as a safety net.
                p = self.tree.new_tag("p")
                p["xml:id"] = self.get_paragraph_id(pcount)
                pcount += 1
                p.append(paragraph)
                if len(paragraph.strip()) > 0:
                    currentdiv.append(p)

        # Attach the completed <body> (and optional <back>) to <text>
        teitext.append(body)
        if back is not None:
            teitext.append(back)

    # --- stub-population method -------------------------------------------

    def update_tree(self):
        """
        Fill all variable fields in the TEI stub tree with metadata from
        this document, then increment the global ``TEI.teiid`` counter.

        Operations performed (in order):
        1. Update ``<title>`` text content.
        2. Set ``<date when="YYYY">`` inside ``<bibl type="firstEdition">``.
        3. Call ``wikify_tree()`` to set author text and Wikidata ``ref``
           attributes on ``<author>`` and ``<title>``.
        4. Call ``add_text()`` to parse the markdown source and build the
           ``<text>`` subtree.
        5. Update ``<measure unit="words">`` with the word count from
           ``add_text()``.
        6. Set ``xml:id`` and ``xml:lang`` on the root ``<TEI>`` element.
        7. Increment ``TEI.teiid``.
        """
        # 1. Title
        treetitle = self.tree.find("title")
        treetitle.clear()
        treetitle.append(self.title)

        # 2. Publication year — located inside the firstEdition bibl block
        sdesc = self.tree.find("sourceDesc")
        for bibl in sdesc.findAll("bibl"):
            if bibl.get("type") == "firstEdition":
                thisdate = bibl.find("date")
                thisdate.append(str(self.year))
                thisdate["when"] = str(self.year)[:4]

        # 3. Author + Wikidata links
        treeauthor = self.tree.find("author")
        self.wikify_tree(treetitle, treeauthor)

        # 4. Parse markdown and build the <text> subtree
        self.add_text()

        # 5. Word count
        numpages = self.tree.find("measure")
        numpages.clear()
        numpages.append(str(self.len_words))

        # 6. Root element attributes
        root = self.tree.find("TEI")
        root["xml:id"]   = self.get_full_id()
        root["xml:lang"] = self.isolang()

        # 7. Advance the global counter so the next document gets a different ID
        TEI.teiid += 1

    # --- serialisation and output -----------------------------------------

    def serialize(self):
        """
        Trigger tree population and return the finished TEI document as a
        pretty-printed XML string.

        Returns
        -------
        str
            Indented UTF-8 XML string.
        """
        self.update_tree()
        return self.tree.prettify()

    def choose_folder(self):
        """
        Return the output sub-folder name based on source availability.

        Returns
        -------
        str
            ``"has_text"`` when a markdown source was found and parsed;
            ``"no_text_yet"`` when the entry has no source file.
        """
        if self.empty:
            return "no_text_yet"
        return "has_text"

    def output_TEI(self):
        """
        Serialise the document and write it to the correct output path.

        Output path pattern::

            tei/2026/{iso_lang}/{has_text|no_text_yet}/{outputfilename}.xml

        The directory is expected to exist; this method does not create it.
        """
        current_path = (
            f"{OUTPUT_BASE}/{self.isolang()}/"
            f"{self.choose_folder()}/{self.outputfilename}.xml"
        )
        print(f"to path {current_path}")
        with open(current_path, "w") as outfile:
            outfile.write(self.serialize())


# ---------------------------------------------------------------------------
# Row processor
# ---------------------------------------------------------------------------

def row_to_tei(row):
    """
    Convert a single metadata row into a TEI/XML file.

    This function is designed to be called via ``DataFrame.apply()``.  It
    reads all relevant columns from *row*, constructs a ``TEI`` object,
    populates its metadata fields, and calls ``output_TEI()``.

    Wikidata ID handling
    --------------------
    The metadata table stores work IDs as full Wikipedia URLs
    (``https://www.wikidata.org/wiki/QXXXXX``).  They must be converted to
    entity URLs (``…/entity/QXXXXX``) for use as RDF-style ``ref`` values.
    This replacement is done here with a ``try/except`` to handle missing
    or non-string values gracefully.

    Parameters
    ----------
    row : pandas.Series
        One row from the metadata DataFrame.

    Returns
    -------
    str
        A short status string, e.g. ``"success EzProse_Example…"``.
    """
    author       = row["Autor*in"]
    title        = row["Titel"]
    sourcetxtname = row["Filename"]

    new_tei = TEI(title, author, sourcetxtname)

    new_tei.year = row["Jahr"]

    # Work Wikidata ID: convert /wiki/ URLs to /entity/ entity URLs
    try:
        new_tei.wikidataid = row["Wiki-Data ID Work"].replace("/wiki/", "/entity/")
    except Exception:
        # Cell is empty (NaN) or not a string — leave as None
        new_tei.wikidataid = None

    # Author Wikidata ID: stored in the table as a bare Q-ID (e.g. "Q100876")
    new_tei.wikidataidauth = (
        f"https://www.wikidata.org/entity/{row['Wiki-Data ID Author']}"
    )

    new_tei.lang = row["Sprache"]

    new_tei.output_TEI()

    return f"success {sourcetxtname} "


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """
    Load the metadata table and convert every row to a TEI/XML file.

    The global ``TEI.teiid`` counter is reset to 1 at the start of each run
    so that IDs are always assigned in the same order as the rows in the
    metadata table, regardless of whether this module was imported earlier
    in the same Python session.
    """
    df = pd.read_excel(METADATA_FILE)

    # Rows without a filename value mean "no source text available yet"
    df["Filename"] = df["Filename"].fillna("NoSourceTxt")

    # Reset the document counter so IDs start from eco_de_000001 / eco_en_000001
    TEI.teiid = 1

    df.apply(row_to_tei, axis=1)


if __name__ == "__main__":
    main()
