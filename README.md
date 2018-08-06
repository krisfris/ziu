# ziu
File manager

## Requirements
apt install libmagic1

## Notes

### File type recognition
ziu defines file type by looking at the filename extension and
python-magic for filenames without extensions.

This is only relevant if an item is opened through the "open with" menu
as xdg-open will be used otherwise.

https://github.com/h2non/filetype.py may be another good option
especially for cross-platform.
