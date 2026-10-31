---
name: print-local
description: Converts generated markdown lists, tables, or text into a PDF and sends it to the local Brother printer.
---

# Skill: Local Printer

## Description

Converts generated markdown lists, tables, or text into a PDF and sends it to the local Brother printer.

## Instructions

When I ask you to print a document, table, or list (such as the tare weight reference sheet):

1. **Format the Output:**

* Ensure the data is formatted cleanly using standard Markdown. If it is a table, ensure the Markdown spacing is neat and readable, as it will be rendered into a PDF.

2. **Execute the Print Command:**

* Pass the formatted markdown text as a single string argument to the print script located at `scripts/print_to_brother.sh`.
* Example command execution: `bash scripts/print_to_brother.sh "YOUR_FORMATTED_MARKDOWN_TEXT"`

3. **Confirmation:**

* Confirm to the user that the print job has been spooled to `BrotherPrinter`, but do not output the raw table to the terminal again unless explicitly asked.
