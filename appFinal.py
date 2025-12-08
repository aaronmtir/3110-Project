# Comp-3110 Project: XML Line Mapping Tool

#!/usr/bin/env python3
import os
import sys
import xml.etree.ElementTree as ET


def normalize_line(line: str) -> str:
    """
    Normalize a source line for comparison:
    - Strip LF/CRLF (already done by caller)
    - Remove // comments
    - Remove single-line /* ... */ comments (non-nested, on same line)
    - Trim surrounding whitespace
    This way '"int"' and '"int"/*nonNLS*/' compare as equal.
    """
    # Remove // comments
    if '//' in line:

        # crude but works well-enough for code mapping
        line = line.split('//', 1)[0]

    # Remove single-line /* ... */ segments
    while '/*' in line and '*/' in line:
        start = line.find('/*')
        end = line.find('*/', start + 2)
        if end == -1:
            break
        line = line[:start] + line[end + 2:]

    # Trim whitespace
    return line.strip()


def read_lines(path):
    """
    Read all lines from a text file, stripping LF/CRLF endings and
    normalizing for comparison.
    Returns a list of normalized strings (one per line).
    Line count and ordering are preserved (line numbers are 1-based indexes).
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw_lines = [l.rstrip("\r\n") for l in f]
        norm_lines = [normalize_line(l) for l in raw_lines]
        return norm_lines
    except OSError as e:
        print(f"Error: Failed to open '{path}' for reading: {e}", file=sys.stderr)
        return None


def map_lines(original_lines, new_lines):
    """
    Compute a mapping between original_lines and new_lines using LCS.

    Returns a list of (orig_line_number, new_line_number) pairs where:
      - Both numbers are 1-based.
      - (i, j)  means original line i corresponds to new line j (unchanged/moved).
      - (i, -1) means original line i was removed.
      - (-1, j) means new line j was added.

    This allows:
      <LOCATION ORIG="7" NEW="-1"/>   for deletions
      <LOCATION ORIG="-1" NEW="5"/>   for insertions
    """
    n = len(original_lines)
    m = len(new_lines)

    # Build LCS DP table on normalized lines
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n):
        oi = original_lines[i]
        for j in range(m):
            if oi == new_lines[j]:
                dp[i + 1][j + 1] = dp[i][j] + 1
            else:
                dp[i + 1][j + 1] = max(dp[i][j + 1], dp[i + 1][j])

    # Backtrack to find operations: match / insert / delete
    ops = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and original_lines[i - 1] == new_lines[j - 1]:
            # lines match
            ops.append(("match", i, j))
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j - 1] >= dp[i - 1][j]):
            # insertion in new file
            ops.append(("ins", -1, j))
            j -= 1
        else:
            # deletion from original file
            ops.append(("del", i, -1))
            i -= 1

    ops.reverse()

    # Convert ops to list of (orig_line_number, new_line_number)
    mappings = []
    for kind, oi, nj in ops:
        if kind == "match":
            mappings.append((oi, nj))
        elif kind == "del":
            mappings.append((oi, -1))
        else:  # "ins"
            mappings.append((-1, nj))

    return mappings


def build_xml(test_name, original_path, version_paths, all_mappings):
  
    file_attr = os.path.basename(original_path)
    root = ET.Element("TEST", {
        "NAME": test_name,
        "FILE": file_attr
    })

    for idx, (version_path, mappings) in enumerate(zip(version_paths, all_mappings), start=1):
        version_elem = ET.SubElement(root, "VERSION", {
            "NUMBER": str(idx),
            "CHECKED": "TRUE"
        })

        for orig_num, new_num in mappings:
            ET.SubElement(version_elem, "LOCATION", {
                "ORIG": str(orig_num),
                "NEW": str(new_num)
            })

    return root


def main():
    print("=== XML Line Mapping Tool (Python) ===")

    # 1) Original file path
    original_path = input("Enter ORIGINAL file path: ").strip()
    if not original_path:
        print("Error: ORIGINAL file path is required.", file=sys.stderr)
        return 1

    # 2) TEST name
    test_name = input("Enter TEST name (e.g., TEST1): ").strip()
    if not test_name:
        test_name = "TEST"

    # 3) Number of versions to compare
    try:
        num_versions_str = input("Enter number of versions to compare: ").strip()
        num_versions = int(num_versions_str)
        if num_versions <= 0:
            raise ValueError
    except ValueError:
        print("Error: number of versions must be a positive integer.", file=sys.stderr)
        return 1

    # 4) Paths of version files
    version_paths = []
    for i in range(num_versions):
        path = input(f"Enter path for VERSION {i + 1}: ").strip()
        if not path:
            print("Error: empty path is not allowed.", file=sys.stderr)
            return 1
        version_paths.append(path)

    # Read original file
    original_lines = read_lines(original_path)
    if original_lines is None:
        return 1

    all_mappings = []
    for i, vpath in enumerate(version_paths, start=1):
        new_lines = read_lines(vpath)
        if new_lines is None:
            return 1

        mappings = map_lines(original_lines, new_lines)
        all_mappings.append(mappings)

        # Stats: match / removed / added
        matched = sum(1 for o, n in mappings if o > 0 and n > 0)
        removed = sum(1 for o, n in mappings if o > 0 and n == -1)
        added = sum(1 for o, n in mappings if o == -1 and n > 0)

        print(
            f"VERSION {i}: {matched} line(s) matched, "
            f"{removed} line(s) removed, {added} line(s) added."
        )

    # Build XML tree
    root = build_xml(test_name, original_path, version_paths, all_mappings)

    # Decide output filename → TEST5.xml style
    safe_test = "".join(c if c.isalnum() or c in "-_" else "_" for c in test_name)
    if not safe_test:
        safe_test = "TEST"
    output_filename = f"{safe_test}.xml"

    # Write XML to file (with pretty indent if Python 3.9+)
    try:
        try:
            ET.indent(root, space="  ")
        except AttributeError:
            pass  

        tree = ET.ElementTree(root)
        with open(output_filename, "wb") as f:
            tree.write(f, encoding="utf-8", xml_declaration=True)

        print(f"XML mappings written to {output_filename}")
    except OSError as e:
        print(f"Error: Failed to write XML file: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
