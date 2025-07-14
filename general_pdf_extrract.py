import re
import pandas as pd
from collections import Counter
from datetime import date
import fitz
from pydeck.bindings.deck import has_jupyter_extra 



def find_statement_year_and_span(lines):
    """
    Finds the most likely statement year and detects if it spans across two years (e.g., Dec-Jan).

    Rules:
    1. Ignores any 4-digit numbers found within 5 lines of a "DUE" date to avoid confusion.
    2. Determines the primary year based on the most common year found elsewhere.
    3. Checks if both "Jan" and "Dec" appear in transaction dates to detect a year span.

    :param lines: A list of strings from the PDF text.
    :return: A tuple (primary_year, spans_two_years), e.g., (2024, True).
    """
    # Rule 1: Identify and exclude lines near "DUE DATE"
    excluded_line_indices = set()
    for i, line in enumerate(lines):
        if "DUE" in line.upper():
            for j in range(max(0, i - 5), min(len(lines), i + 6)):
                excluded_line_indices.add(j)

    # Find all plausible years NOT in the excluded zones
    candidate_years = []
    year_regex = re.compile(r'\b(19\d{2}|20\d{2})\b')
    for i, line in enumerate(lines):
        if i not in excluded_line_indices:
            found_years = year_regex.findall(line)
            for year_str in found_years:
                year_int = int(year_str)
                # A reasonable range for statement years
                if 2000 <= year_int <= date.today().year + 1:
                    candidate_years.append(year_int)

    # The primary year is the most common one found
    if not candidate_years:
        primary_year = date.today().year # Fallback
    else:
        primary_year = Counter(candidate_years).most_common(1)[0][0]

    # Rule 2: Check for Jan/Dec span in transaction-like lines
    found_jan, found_dec = False, False
    date_pattern = re.compile(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}$', re.IGNORECASE)
    for line in lines:
        if date_pattern.match(line):
            if line.upper().startswith("JAN"):
                found_jan = True
            elif line.upper().startswith("DEC"):
                found_dec = True
    
    spans_two_years = found_jan and found_dec
    
    return primary_year, spans_two_years


def get_line_fingerprint(line):
    """
    Creates a 'fingerprint' for a line based on its type and length.
    This allows us to find repeating structural patterns.

    Returns a tuple, e.g., ('DATE', 6), ('AMOUNT',), ('TEXT', 25).
    """
    line = line.strip()
    
    # --- Feature Detection ---
    
    # AMOUNT: Very specific pattern. Length varies, so we don't include it in the fingerprint.
    if re.fullmatch(r'-?\$?[\d,]+\.\d{2}', line):
        return ('AMOUNT')

    # DATE: 'Mon Day' format. Length is usually consistent.
    if re.fullmatch(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}', line, re.IGNORECASE):
        return ('DATE')
        
    # ID_NUMBER: Long numeric string. Length can vary slightly, so we omit it.
    if re.fullmatch(r'\d{10,}', line):
        return ('ID_NUMBER')
    
    if r"thank"  in line.lower() or r"payment" in line.lower():
        return ('THANK_YOU')
    # TEXT: The default type. Length is a key feature here.
    return ('TEXT')


def merge_consecutive_text_lines(lines, fingerprints):
    """
    Merges consecutive 'TEXT' lines into a single line.
    
    This simplifies pattern detection by ensuring merchant names that span
    multiple lines are treated as a single 'TEXT' entity.

    :param lines: The original list of text lines.
    :param fingerprints: The original list of line fingerprints.
    :return: A tuple of (merged_lines, merged_fingerprints).
    """
    if not lines:
        return [], []

    merged_lines = []
    merged_fingerprints = []
    
    i = 0
    while i < len(lines):
        current_fp = fingerprints[i]
        
        # If the line is NOT a text line, just append it and move on.
        if current_fp != 'TEXT':
            merged_lines.append(lines[i])
            merged_fingerprints.append(fingerprints[i])
            i += 1
        else:
            # It's a 'TEXT' line. Look ahead to see if the next ones are also 'TEXT'.
            text_block = [lines[i]]
            j = i + 1
            while j < len(fingerprints) and fingerprints[j] == 'TEXT':
                text_block.append(lines[j])
                j += 1
            
            # Join the collected text lines into a single string.
            combined_text = ' '.join(text_block)
            merged_lines.append(combined_text)
            
            # Create a new fingerprint for the combined text line.
            # We use the combined length as the feature.
            merged_fingerprints.append('TEXT')
            
            # Move the main index past all the text lines we just merged.
            i = j
            
    return merged_lines, merged_fingerprints


def extract_transactions_dynamically(lines):
    """
    A general-purpose transaction extractor that dynamically finds the most
    common data pattern in a PDF and uses it to extract data.
    """
    primary_year, spans_two_years = find_statement_year_and_span(lines)
    # 2. Create a fingerprint for every single line in the document
    initial_fingerprints = [get_line_fingerprint(line) for line in lines]
    # 3. *** NEW STEP: Merge consecutive text lines ***
    lines, fingerprints = merge_consecutive_text_lines(lines, initial_fingerprints)
    

    # 3. Discover the most common transaction pattern
    pattern_counts = Counter()
    # We assume a transaction pattern will be between 3 and 6 lines long
    for length in range(3, 6):
        for i in range(len(fingerprints) - length + 1):
            pattern = tuple(fingerprints[i : i + length])
            
            # A valid pattern must contain a DATE and an AMOUNT to be a transaction
            has_date = any(fp == 'DATE' for fp in pattern)
            has_amount = any(fp == 'AMOUNT' for fp in pattern)
            has_txt = any(fp == 'TEXT' for fp in pattern)
            
            if has_date and has_amount and has_txt and pattern[0] == 'DATE':
                pattern_counts[pattern] += 1
    
    if not pattern_counts:
        print("Error: Could not automatically determine a recurring transaction pattern.")
        return pd.DataFrame()

    # The best pattern is the one that repeats most often
    max_count = pattern_counts.most_common(1)[0][1]
    top_patterns = [p for p, c in pattern_counts.items() if c == max_count]
    best_pattern = top_patterns[-1]
    # best_pattern = pattern_counts.most_common(1)[0][0]
    # print(f"Success: Detected most common transaction pattern: {best_pattern}")

    # 4. Extract data using the discovered 'best_pattern'
    transactions = []
    pattern_len = len(best_pattern)

    i = 0
    while i <= len(lines) - pattern_len:
        current_fingerprint_slice = tuple(fingerprints[i : i + pattern_len])
        
        # If the current slice of fingerprints matches our best pattern
        if current_fingerprint_slice == best_pattern:
            raw_text_slice = lines[i : i + pattern_len]
            
            # Extract info based on the pattern's structure
            date_str = raw_text_slice[ best_pattern.index(('DATE'))]
            amount_str = raw_text_slice[best_pattern.index(('AMOUNT'))]
            
            # All non-date/amount/id lines are part of the merchant name
            merchant_indices = [idx for idx, fp in enumerate(best_pattern) if fp == 'TEXT']
            merchant = ' '.join([raw_text_slice[idx] for idx in merchant_indices])
            amount = float(amount_str.replace('$', '').replace(',', ''))
            
            if spans_two_years and f'date_str.upper() contains "DEC"':
                year = primary_year + 1
            else:
                year = primary_year
            full_date = pd.to_datetime(f"{date_str} {year}", format="%b %d %Y", errors='coerce')

            transactions.append({
                "Date": full_date,
                "Merchant": merchant,
                "Amount": amount
            })
            # Jump forward by the length of the pattern to find the next one
            i += pattern_len
        else:
            i += 1
            
    return pd.DataFrame(transactions)




if __name__ == "__main__":
    path = r"F:\Work\github\BankAcount\example_pdf\2025-03.pdf"
    path = r"F:\Work\github\BankAcount\example_pdf\5415902751986709_2024_12_07_2025_01_06.pdf"
    path = r"F:\Work\github\BankAcount\example_pdf\Account Statement-May.pdf"

    doc = fitz.open(path)
    full_text = "".join(page.get_text() for page in doc)
    lines = [line.strip() for line in full_text.split('\n') if line.strip()]


    # 2. Run the dynamic extraction function on our dummy file
    print(f"--- Running Dynamic Parser on '{path}' ---")
    primary_year, spans_two_years = find_statement_year_and_span(lines)
    extracted_df = extract_transactions_dynamically(lines, primary_year, spans_two_years)

    # 3. Print the results
    print("--- Extracted Transactions ---")
    if not extracted_df.empty:
        print(extracted_df)
        print(extracted_df['Amount'].sum())
        print(extracted_df[extracted_df['Amount'] >= 0]['Amount'].sum())
    else:
        print("No transactions were extracted.")
        