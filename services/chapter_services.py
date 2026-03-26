
# --- Imports
from dotenv import load_dotenv
import base64
import os
from mistralai.client import Mistral

import pickle
import re

from pydantic import BaseModel
from typing import List
import pandas as pd

# --- keys
def get_mistral_client():
    """
    Initializes and returns a Mistral API client using the API key from environment variables.

    Loads the environment variables, retrieves the Mistral API key,
    and creates a Mistral client instance.

    Returns:
        Mistral: An authenticated Mistral API client.
    """
    load_dotenv()
    API_KEY = os.getenv('MISTRAL_API_KEY')
    client = Mistral(api_key=API_KEY)
    return client


# --- Class
# Model
class NumChapterReposne(BaseModel):
    """
    Represents a response containing chapter numbers and titles.

    Attributes:
        chapters_num (List[str]): List of chapter numbers.
        chapters_title (List[str]): List of chapter titles.
    """
    chapters_num : List[str]
    chapters_title : List[str]

class ChapterReposne(BaseModel) :
    """
    Represents a response containing a single chapter.

    Attributes:
        chapters (str): The chapter content.
    """
    chapters : str

class ChapterListReposne(BaseModel):
    """
    Represents a response containing a list of chapters.

    Attributes:
        chapters (List[str]): List of chapter contents.
    """
    chapters : List[str]

# Erreurs
class CustomProcessingError(Exception):
    """
    Custom exception for processing-related errors.
    """
    pass


# --- Fonctions
# 2. OCR 

# Base64 encoding
def encode_pdf(pdf_path):
    """
    Encodes a PDF file to a base64 string for transmission.

    Args:
        pdf_path (str): Path to the PDF file to be encoded.

    Returns:
        str: Base64 encoded string of the PDF file, or None if an error occurs.

    Raises:
        Prints an error message if the file is not found or if another exception occurs.
    """
    try:
        with open(pdf_path, "rb") as pdf_file:
            return base64.b64encode(pdf_file.read()).decode('utf-8')
    except FileNotFoundError:
        print(f"Error: The file {pdf_path} was not found.")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None


# Mistral OCR
def doc_OCR(doc_path, client) :
    """
    Sends a PDF (encoded in base64) to Mistral OCR and retrieves a list of pages in Markdown format.

    Args:
        doc_path (str): Path to the PDF file to process.
        client: Authenticated Mistral API client instance.

    Returns:
        List[str]: List of Markdown strings, each representing a page from the processed PDF.
                  Returns an empty list if processing fails.
    """
    base64_pdf = encode_pdf(doc_path)

    ocr_response = client.ocr.process(
    model="mistral-ocr-latest",
    document={
        "type": "document_url",
        "document_url": f"data:application/pdf;base64,{base64_pdf}" },
    include_image_base64=False)
    
    doc_pages = []

    for i in range(len(ocr_response.pages)):
        doc_pages.append(ocr_response.pages[i].markdown)

    return doc_pages

# 3.1
# 1. Get table of contents in the first 6 pages
def get_toc_llm(doc_list, client) :
    
    """
    Extracts the main chapters from the table of contents in the first 6 pages of a document using LLM.

    Args:
        doc_list (List[str]): List of Markdown strings representing the document pages.
        client: Authenticated Mistral API client instance.

    Returns:
        pd.DataFrame: A DataFrame with two columns:
            - "Numerotation": List of chapter numbers with exact formatting.
            - "Titre": List of chapter titles without numbering.

    Notes:
        Only processes the first 6 pages of the document.
        Uses the LLM to strictly extract main chapters, excluding sub-chapters.
    """

    part1 = ""
    for i in range(6):
        part1 += doc_list[i]

    chapitre_ocr = [{"role": "user", 
            "content": 
            f"""
            Dans le document ci-dessous, extrais **uniquement les chapitres principaux** de la table des matières.
            **Consignes strictes :**
            1. **Ne retourne pas les sous-chapitres** (ex. : 1.1, 1.a, etc.).

            2. **Conserve la numérotation exacte** des chapitres principaux, 
            y compris les caractères qui l'accompagnent (ex. : "1 -", "1)", "1. ", "ARTICLE 1", etc.).

            3. Retourne :
                - La numérotation **exacte** (avec les caractères) dans une liste Python nommée `chapters_num`.
                - Les titres **seuls** (sans numérotation) dans une liste Python nommée `chapters_title`.

            **Format attendu :**
            ```python
            chapters_num = ["1 -", "2)", "3. ", ...]  # Exemple avec différents formats de numérotation
            chapters_title = ["Titre du chapitre 1", "Titre du chapitre 2", ...]
            ```
            -----
            DOCUMENT :
            {part1}
            -----
            """}]

    chat_ocr = client.chat.parse(model = 'mistral-large-latest',
                                messages = chapitre_ocr,
                                response_format = NumChapterReposne,
                                temperature = 0)

    num = chat_ocr.choices[0].message.parsed.__dict__['chapters_num']
    titre = chat_ocr.choices[0].message.parsed.__dict__['chapters_title']


    data = {"Numerotation": num,
    "Titre" : titre}

    df = pd.DataFrame(data).astype(str)

    return df



 # 3.2
def check_all_toc(doc_list : List, last_titre : str, client : object) :
    """
    Verifies that the entire table of contents has been processed by checking for additional main chapters
    following the last identified chapter in the document.

    Args:
        doc_list (List[str]): List of Markdown strings representing the document pages.
        last_titre (str): Title of the last main chapter identified in the table of contents.
        client: Authenticated Mistral API client instance.

    Returns:
        pd.DataFrame: A DataFrame with two columns:
            - "Numerotation": List of chapter numbers with exact formatting.
            - "Titre": List of chapter titles without numbering.
                      Returns an empty DataFrame if no additional chapters are found or if an error occurs.

    Raises:
        CustomProcessingError: If an error occurs during processing.

    Notes:
        Searches through the document pages starting from page 6.
        Only considers chapters that follow the same numbering format as `last_titre`.
    """
    try :
        # last page checked
        page_num = 5

        num = []
        titre = []
        
        # Check if last chapter in last page.
        while page_num < len(doc_list) :
            
            if last_titre in doc_list[page_num] :
            
                part2 = ""
                for j in range(page_num, page_num +3) :
                    part2 += doc_list[j]


                all_toc =[{"role": "user", 
                "content": 
        f"""Dans le document ci-dessous, vérifie que {last_titre} est bien le dernier chapitre principale du sommaire.
        **Identifie uniquement les chapitres principaux** qui suivent directement {last_titre}
        en respectant strictement la même logique de numérotation et de hiérarchie.

        **Consignes strictes :**
        1. **Exclus les sous-chapitres** :
           - Ignore toute numérotation imbriquée (ex. : "1.1", "1.a", "5 - 10").
           - Ignore les chapitres dont la numérotation inclut des lettres ou des sous-niveaux (ex. : "d)", "e)").

        2. **Respecte la structure exacte de {last_titre}** :
           - Si {last_titre} est numéroté "1 -", cherche uniquement des chapitres avec une numérotation similaire (ex. : "2 -", "3 -").
           - Si {last_titre} est numéroté "Article 12 -", cherche uniquement des chapitres comme "Article 13 -", "Article 14 -".
           - Si {last_titre} est numéroté "CHAPITRE 4 :", cherche uniquement des chapitres comme "CHAPITRE 5 :".

        3. **Ne retourne rien si :**
           - Aucun chapitre ne correspond à la hiérarchie de {last_titre}.
           - Les chapitres suivants changent de format de numérotation (ex. : après "3 -", tu trouves "Article 1 -").

        4. **Format de sortie :**
           - Si des chapitres valides sont trouvés, retourne **deux listes Python** :
             - `chapters_num` : Liste des numérotations **exactes** (ex. : ["2 -", "3 -"]).
             - `chapters_title` : Liste des titres **sans numérotation** (ex. : ["Travaux à la Charge de L'entreprise", "Descriptif des Travaux"]).

        -----
        DOCUMENT :
        {part2}
        -----"""}]
    
            

                all_toc_query = client.chat.parse(model = 'mistral-large-latest',
                                messages = all_toc,
                                response_format = NumChapterReposne,
                                temperature = 0)

                num2 = all_toc_query.choices[0].message.parsed.__dict__['chapters_num']
                titre2 = all_toc_query.choices[0].message.parsed.__dict__['chapters_title']


                num.extend(num2)
                titre.extend(titre2)

                page_num += 1

            else :
                page_num = len(doc_list)

    except Exception as e:
        raise CustomProcessingError(f"Erreur dans check_all_toc : {e}") from e


    data = {"Numerotation": num,
    "Titre" : titre}

    df = pd.DataFrame(data).astype(str)

    return df


# 3.3 Check if the table of content was complete
def get_more_chtp(doc_list : List, last_titre : str, client : object):
    """
    Checks if any main chapters were missed in the table of contents by analyzing the end of the document.

    Args:
        doc_list (List[str]): List of Markdown strings representing the document pages.
        last_titre (str): Title of the last main chapter identified in the table of contents.
        client: Authenticated Mistral API client instance.

    Returns:
        pd.DataFrame: A DataFrame with two columns:
            - "Numerotation": List of chapter numbers with exact formatting.
            - "Titre": List of chapter titles without numbering.
                      Returns an empty DataFrame if no additional chapters are found or if an error occurs.

    Raises:
        CustomProcessingError: If an error occurs during processing.

    Notes:
        Focuses on the last 3 pages of the document to identify any missed main chapters.
        Only considers chapters that follow the same numbering format as `last_titre`.
    """
    num = []
    titre = []

    # Get last chapter.
    try :
        part3 = ""
        pag_tot = len(doc_list)

        if pag_tot > 3 : 
            for k in range(pag_tot-3, pag_tot):
                part3 += doc_list[k]
        else :
            for k in range(pag_tot):
                part3 += doc_list[k]

  
        more_chapitre = [{"role": "user", 
        "content": 
        
        f"""Dans la fin du document ci-dessous, vérifie que {last_titre} est bien le dernier titre principal du document.
        **Identifie uniquement les chapitres principaux** qui suivent directement {last_titre}
        en respectant strictement la même logique de numérotation et de hiérarchie.

        **Consignes strictes :**
        1. **Exclus les sous-chapitres** :
           - Ignore toute numérotation imbriquée (ex. : "1.1", "1.a", "5 - 10").
           - Ignore les chapitres dont la numérotation inclut des lettres ou des sous-niveaux (ex. : "d)", "e)").

        2. **Respecte la structure exacte de {last_titre}** :
           - Si {last_titre} est numéroté "1 -", cherche uniquement des chapitres avec une numérotation similaire (ex. : "2 -", "3 -").
           - Si {last_titre} est numéroté "Article 12 -", cherche uniquement des chapitres comme "Article 13 -", "Article 14 -".
           - Si {last_titre} est numéroté "CHAPITRE 4 :", cherche uniquement des chapitres comme "CHAPITRE 5 :".

        3. **Ne retourne rien si :**
           - Aucun chapitre ne correspond à la hiérarchie de {last_titre}.
           - Les chapitres suivants changent de format de numérotation (ex. : après "3 -", tu trouves "Article 1 -").

        4. **Format de sortie :**
           - Si des chapitres valides sont trouvés, retourne **deux listes Python** :
             - `chapters_num` : Liste des numérotations **exactes** (ex. : ["2 -", "3 -"]).
             - `chapters_title` : Liste des titres **sans numérotation** (ex. : ["Travaux à la Charge de L'entreprise", "Descriptif des Travaux"]).


            -----
            DOCUMENT :
            {part3}
            -----"""}]

        more_chpt = client.chat.parse(model = 'mistral-large-latest',
                        messages = more_chapitre,
                        response_format = NumChapterReposne,
                        temperature = 0)

        num3 = more_chpt.choices[0].message.parsed.__dict__['chapters_num']
        titre3 = more_chpt.choices[0].message.parsed.__dict__['chapters_title']

        num.extend(num3)
        titre.extend(titre3)


    except Exception as e :
        raise CustomProcessingError(f"Erreur dans get_more_chtp : {e}") from e

    data = {"Numerotation": num,
    "Titre" : titre}

    df = pd.DataFrame(data).astype(str)

    return df

# 5 Get chapiters pages numbers
def normaliser_texte(texte):
    """
    Normalizes French text by converting it to lowercase and replacing accented characters with their non-accented equivalents.

    Args:
        texte: Input string containing French text with accents.

    Returns:
        Normalized string in lowercase without accents.
    """
    # mapper
    table_traduction = str.maketrans({
        'à': 'a', 'â': 'a', 'ä': 'a',
        'ç': 'c',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'î': 'i', 'ï': 'i',
        'ô': 'o', 'ö': 'o',
        'ù': 'u', 'û': 'u', 'ü': 'u',
        'ÿ': 'y',
    })

    texte = texte.lower()
    texte_final = texte.translate(table_traduction)

    return texte_final.lower()


# 5.1
def find_all_occurrences(main_string, sub_string):
    """
    Finds all starting indices of a substring within a main string.

    Args:
        main_string: The string to search within.
        sub_string: The substring to locate.

    Returns:
        List of starting indices where the substring is found.
        Empty list if no occurrences exist.
    """
    start = 0
    occurrences = []
    while True:
        start = main_string.find(sub_string, start)
        if start == -1:
            break
        occurrences.append(start)
        start += 1 
    return occurrences


# Get all chapter occurences in ['Title_found]
def get_chapter_pages_index(df, doc_pages):
    """
    Locates all occurrences of chapter titles in the document pages and checks for associated numbering.

    Args:
        df: DataFrame containing columns "Titre" (titles) and "Numerotation" (numbering).
        doc_pages: List of document pages in string format.

    Returns:
        DataFrame with two additional columns:
            - "Title_found": List of [page_index, string_index] for each title occurrence.
            - "Num_Title": List of [page_index, string_index] for each title with its numbering.

    Process:
        1. Normalizes titles and document text for case-insensitive and accent-insensitive comparison.
        2. Finds all occurrences of each title in the document.
        3. Checks if the chapter numbering appears near each title occurrence.
    """
    # Initialise 'Title_found'
    df['Title_found'] = df.apply(lambda _: [], axis=1)
    
    # Row iterreration
    for index, row in df.iterrows() :
        title = row["Titre"]
        title = normaliser_texte(title)
        pg_occur = []
        # for every page
        for i in range(len(doc_pages)):
            # If titlie in page
            if title in normaliser_texte(doc_pages[i]):

                occurrences = find_all_occurrences(normaliser_texte(doc_pages[i]), title)
                # for every title found, adds [page, str_index]
                for ele in occurrences:
                    pg_occur.append([i, ele])

        # list to df
        df.at[index, 'Title_found'] = pg_occur



    # Checks chapter number in title
    df['Num_Title'] = df.apply(lambda _: [], axis=1)

    for index, row in df.iterrows():
        num_title = []
        num = row['Numerotation']
        if len(row['Title_found']) > 0:
            for ele in row['Title_found']:
                pg = ele[0]
                title_ind = ele[1]
                title_length = len(row["Titre"])
                num_lenght = len(num)

                # chapter number near title (10 characters) ?
                start_index = max(0, title_ind - (10 + num_lenght))
                end_index = title_ind + title_length
                page_content = doc_pages[pg][start_index:end_index]
                num_index = page_content.find(str(num))
                if num_index != -1:
                    num_ind = start_index + num_index
                    num_title.append([pg, num_ind])
        if num_title:
            df.at[index, 'Num_Title'] = num_title

    return df


# 5.2
def classify_chapter(df):
    """
    Classifies chapter occurrences into "Toc" (table of contents) and "Body" (main document) based on their positions.

    Args:
        df: DataFrame with columns "Num_Title" containing lists of [page_index, string_index] for each chapter occurrence.

    Returns:
        DataFrame with two additional columns:
            - "Toc": [page_index, string_index] for table of contents occurrences.
            - "Body": [page_index, string_index] for main document occurrences.

    Logic:
        1. Chapters found twice are classified as the first occurrence in "Toc" and the second in "Body".
        2. Chapters found once are classified as "Toc" if their page is in the list of known TOC pages,
           otherwise as "Body" if their page is greater than or equal to the minimum body page.
    """

    df['Toc'] = df.apply(lambda _: [], axis=1)
    df['Body'] = df.apply(lambda _: [], axis=1)

    # Loop 1 : chapter found twice case
    # 1st occurence, 2nd = TOC, body texte

    toc_pages = []
    body_pages = []

    for index, row in df.iterrows():
        if len(row['Num_Title']) == 2 :
            # result in df
            df.at[index, 'Toc'] = row['Num_Title'][0]
            df.at[index, 'Body'] = row['Num_Title'][1]

            if row['Num_Title'][0][0] not in toc_pages :
                toc_pages.append(row['Num_Title'][0][0])

            if row['Num_Title'][1][0] not in body_pages :
                body_pages.append(row['Num_Title'][1][0])   

    # Loop 2 : chapter found once case
    # Checks if it's TOC or Body
    for index, row in df.iterrows() :
        if len(row['Num_Title']) == 1 :
            pg = row['Num_Title'][0][0]

            if pg in toc_pages :
                df.at[index, 'Toc'] = row['Num_Title'][0]

            elif pg >= min(body_pages) :
                df.at[index, 'Body'] = row['Num_Title'][0]

            else :
                pass

    return df



# V2 5.3
def get_bornes_index(df, doc_pages):
    """
    Determines the start and end boundaries for chapters missing a 'Body' index by analyzing surrounding chapters.

    Args:
        df: DataFrame containing columns 'Body' and 'Toc' with [page_index, string_index] pairs.
        doc_pages: List of document pages in string format.

    Returns:
        DataFrame with two additional columns:
            - 'Body_min': [page_index, string_index] for the lower boundary of the chapter.
            - 'Body_max': [page_index, string_index] for the upper boundary of the chapter.

    Logic:
        1. For chapters without a 'Body' index:
            - The lower boundary is the last valid 'Body' before the current index, or the last 'Toc' if no valid 'Body' exists.
            - The upper boundary is the next valid 'Body' after the current index, or the end of the document if none exists.
    """

    df['Body_min'] = df.apply(lambda _: [], axis=1)
    df['Body_max'] = df.apply(lambda _: [], axis=1)

    for index, row in df.iterrows():
        if len(row['Body']) == 0 :

            # start boundaries
            # Find the last "correct body" before actual row 
            df_min = df[(df.index < index) & (df['Body'].apply(len) == 2)]

            # last one = start boundary
            if not df_min.empty:
                borne_min = df_min['Body'].iloc[-1]

            else:
                # Else start boundary = last "good toc" [page, index]
                df_toc_max = df[df['Toc'].apply(len) == 2]
                if not df_toc_max.empty :
                    toc_max = df_toc_max['Toc'].iloc[-1]
                    if toc_max[0] > 0:
                        borne_min = toc_max
                    else:
                        borne_min = [0, 0]
                else:
                    borne_min = [0, 0]

            df.at[index, 'Body_min'] = borne_min

            # end boundaries
            # Find the last "correct body" after actual row 
            df_max = df[(df.index > index) & (df['Body'].apply(len) == 2)]
            
            # first one = end boundary
            if not df_max.empty:
                borne_max = df_max['Body'].iloc[0]

            else :
                page_max = len(doc_pages)-1
                index_max = len(doc_pages[page_max])
                borne_max = [page_max, index_max]

            df.at[index, 'Body_max'] = borne_max

    return df

# 6.1
def get_text_from_boundaries(doc_pages: list, b_min: list, b_max: list):
    """
    Extracts text from a document between two boundaries defined by page and character indices.

    Args:
        doc_pages: List of document pages as strings.
        b_min: Starting boundary as [page_index, character_index].
        b_max: Ending boundary as [page_index, character_index].

    Returns:
        Extracted text between the boundaries (inclusive of start, exclusive of end).

    Logic:
        - If boundaries are on the same page, returns the substring between indices.
        - If boundaries span multiple pages, concatenates:
            1. Text from the starting page (from `ind_min` to end).
            2. Full text of intermediate pages.
            3. Text from the ending page (from start to `ind_max`).
    """
    text = ""
    page_min, ind_min = b_min
    page_max, ind_max = b_max

    if page_min == page_max:
        text = doc_pages[page_min][ind_min:ind_max]
    else:
        text += doc_pages[page_min][ind_min:]
        for i in range(page_min + 1, page_max):
            text += doc_pages[i]
        text += doc_pages[page_max][:ind_max]

    return text



# 6.2 
def get_body_by_llm(df : object, doc_pages : object, client : object):
    """
    Uses LLM to find and correct chapter titles in the document body when their positions are unclear.
    Updates the DataFrame with corrected titles and their positions.

    Args:
        df: DataFrame containing chapter metadata, including 'Body_min' and 'Body_max' boundaries.
        doc_pages: List of document pages as strings.
        client: Authenticated Mistral API client for LLM queries.

    Returns:
        DataFrame with two additional columns:
            - 'Titre_llm': Corrected chapter title as identified by LLM.
            - 'Title_corrected_by_llm': Boolean indicating if the title was found and corrected.

    Process:
        1. For chapters missing a clear 'Body' position, extracts text between boundaries.
        2. Queries LLM to find the correct title within the extracted text.
        3. Searches for the corrected title in the document and updates its position if found.
    """
    df['Titre_llm'] = ""
  
    for index, row in df.iterrows():
        if len(row['Body']) < 2 :
            
            # get text between its boudaries
            part = get_text_from_boundaries(doc_pages, row['Body_min'], row['Body_max'])
            titre_chapt = f"{row['Numerotation']} {row['Titre']}"

            query_chpt = [{"role": "user", 
                            
            "content": f"""Dans le texte ci-dessous,
            Je ne retrouve pas le titre principal suivant : {titre_chapt}
            Trouve le titre principal qui correspond à ce titre ou qui y ressemble.
            Ne retourne que le titre principal exact, sans modifications ni ajouts. 
            Inclus tous les caractères tels que les sauts de ligne s'ils font partie du titre.
            TEXTE:{part}"""}]

            query_llm = client.chat.parse(model = 'mistral-large-latest',
                            messages = query_chpt,
                            response_format = ChapterReposne,
                            temperature = 0)

            title_corrected = query_llm.choices[0].message.parsed.__dict__['chapters']
            df.at[index, 'Titre_llm'] = title_corrected

    # Check the title found by the LLM and get its index.
    for index, row in df.iterrows():
        if len(row['Body']) < 2 :
            for i in range(row['Body_min'][0], row['Body_max'][0]+1) :
                titre = normaliser_texte(row['Titre_llm'])

                if i == row['Body_min'][0] :
                    index_min = row['Body_min'][1]
                    texte = normaliser_texte(doc_pages[i][index_min:])

                elif i ==row['Body_max'] :
                    index_max = row['Body_max'][1]
                    texte = normaliser_texte(doc_pages[i][:index_max])

                else :
                    texte = normaliser_texte(doc_pages[i])

                if titre in texte :
                    ind = texte.find(titre)
                    if i == row['Body_min'][0] :
                        ind += index_min

                    df.at[index, 'Body'] = [i, ind]
                    df.at[index, 'Title_correctec_by_llm'] = True
                    break
                else :
                    df.at[index, 'Title_correctec_by_llm'] = False
                    
    return df


# 7. 
def make_bornes(df) :
    """
    Prepares chapter boundaries by inserting a "Sommaire" entry and filtering out entries without a body.

    Args:
        df: DataFrame containing chapter data with columns 'Titre' and 'Body'.

    Returns:
        Tuple of three lists:
            - Index: List of chapter indices.
            - Titre: List of chapter titles, starting with "Sommaire".
            - Bornes: List of chapter boundaries as [page, character_index] pairs.

    Process:
        1. Adds a "Sommaire" entry at the beginning.
        2. Removes entries without a valid 'Body'.
        3. Extracts indices, titles, and boundaries for further processing.
    """
    new_row_df = pd.DataFrame([{'Titre': 'Sommaire', 'Body': [0,0]}])
    df2 = pd.concat([new_row_df, df], ignore_index=True)

    df2 = df2[df2['Body'].apply(lambda x: len(x) > 0)]
    df2.loc[:, 'Index'] = df2.index

    index = df2['Index'].to_list()
    titre = df2['Titre'].to_list()
    bornes = df2['Body'].to_list()

    return index, titre, bornes


def division_chapitre(bornes, doc_pages):
    """
    Divides a document into chapters using boundaries defined by page and character indices.

    Args:
        bornes: List of [page, character_index] pairs defining chapter boundaries.
        doc_pages: List of document pages as strings.

    Returns:
        List of chapter texts extracted between consecutive boundaries.

    Example:
        If bornes = [[0, 0], [2, 10]], extracts text from the start of the document
        to page 2, character index 10.
    """
    last_page = len(doc_pages)-1
    last_index = len(doc_pages[last_page])
    bornes.append([last_page, last_index])

    chapt_txt = []

    for i in range(len(bornes)-1):
        texte = get_text_from_boundaries(doc_pages, bornes[i], bornes[i+1])
        chapt_txt.append(texte)

    return chapt_txt



def fichier_chapitre_en_texte(index, titres, chapt_txt, directory):
    """
    Saves each chapter as a separate text file in the specified directory.

    Args:
        index: List of chapter indices.
        titres: List of chapter titles.
        chapt_txt: List of chapter texts to be saved.
        directory: Path to the directory where files will be saved.

    Process:
        1. Sanitizes chapter titles by removing invalid filename characters.
        2. Creates a text file for each chapter with the format: "{index} {title}.txt".
        3. Writes the chapter text to the corresponding file.
    """
    caracteres_interdits = r'[\\/*?:"<>|]'

    for i in range(len(index)):
        nom = titres[i].capitalize()
        nom = re.sub(caracteres_interdits, '', nom)
        nom = nom.strip()

        nom_fichier = f"{directory}/{index[i]} {nom}.txt"

        # Écrire l'élément dans le fichier
        with open(nom_fichier, 'w', encoding='utf-8') as fichier :
            fichier.write(chapt_txt[i])

            

# ------------------------------ complete pipe ------------------------------ 
def doc_to_chapter(file, directory = None):
    
    # Mistral client
    client=get_mistral_client()

    ### ------ 2. OCR
    # OCR le document 
    doc_pages = doc_OCR(file, client)


    ### ------ 3 Get the chapters
    # --- 3.1. get toc raw
    df_toc_raw = get_toc_llm(doc_pages, client)

    # --- 3.2 complete toc ?
    last_num = df_toc_raw['Numerotation'].to_list()[-1]
    last_title = df_toc_raw['Titre'].to_list()[-1]
    last_num_title = last_num + ' '+ last_title

    complete_toc = []
    for i in range(6):
        complete_toc.append(last_num in doc_pages[i] and last_title in doc_pages[i])

    if any(complete_toc) and not complete_toc[-1] :
        pass

    elif any(complete_toc) and complete_toc[-1] :
        df_all_toc = check_all_toc(doc_pages, last_num_title, client) 

        if df_all_toc.empty :
            pass
            
        else :
            df_toc_raw = pd.concat([df_toc_raw, df_all_toc], ignore_index=True)
            last_num = df_toc_raw['Numerotation'].to_list()[-1]

    # --- 3.3 Chapter in body and not in Toc ?
    last_num = df_toc_raw['Numerotation'].to_list()[-1]
    last_title = df_toc_raw['Titre'].to_list()[-1]
    last_num_title = last_num + ' '+ last_title 
    df_more_chpt = get_more_chtp(doc_pages, last_num_title, client)


    # If more cha^ter found, add it
    if df_more_chpt.empty :
        pass
        
    else :
        merged_df = df_toc_raw.merge(df_more_chpt, on=['Numerotation', 'Titre'], how='outer', indicator=True)
        new_rows = merged_df[merged_df['_merge'] == 'right_only'][['Numerotation', 'Titre']]
        df_toc_raw = pd.concat([df_toc_raw, new_rows], ignore_index=True)

    ### ------ 5. Get chapter pages
    # --- 5.1 Titles index
    df5_1 = get_chapter_pages_index(df_toc_raw.copy(), doc_pages)
    # --- 5.2 Index from toc or body ?
    df5_2 = classify_chapter(df5_1.copy())

    # Checking if all index :
    missing_toc = df5_2['Toc'].apply(lambda x: x == []).any()
    missing_body = df5_2['Body'].apply(lambda x: x == []).any()


    if not missing_toc and not missing_body :
        index_complete = True
    else:
        index_complete = False


    # --- 5.3 Get the boundaries
    if not index_complete :
        df5_3 = get_bornes_index(df5_2.copy(), doc_pages)

    ### ------- 6 : correction by LLM
    if not index_complete :
        df6_2 = get_body_by_llm(df5_3.copy(), doc_pages, client)

    ### ------ 7. Divide the text into chapters
    if index_complete :
        doc_chapitre_llm = df5_2.copy()

    else :
        doc_chapitre_llm = df6_2.copy()

    bornes = make_bornes(doc_chapitre_llm)[2]
    chapt_txt = division_chapitre(bornes, doc_pages)

    return chapt_txt