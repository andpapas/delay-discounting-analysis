# Private data folder — do not publish

This directory is intentionally excluded by the repository's root `.gitignore`.

For a local/private reproduction of the reported analysis, place the original
Google Forms export here as:

`raw_responses_private.xlsx`

Then run:

```bash
python analysis.py \
  --input data/private/raw_responses_private.xlsx \
  --output outputs/private
```

**Do not upload the participant-level workbook to a public GitHub repository.**
Even if direct identifiers have been removed, row-level educational data may
still be sensitive or re-identifiable when combined with other information.

The public repository should contain only `data/stub_responses.xlsx`, which is
fully synthetic and contains no real participant data.
