# Book2Anki

Convert text files into word Anki cards. 

At the moment it only supports Japanese.

It utilizes the [MeCab](https://github.com/SamuraiT/mecab-python3) library for word segmentation and integrates frequency data from JPDB through [yomitan-dictionaries](https://github.com/Kuuuube/yomitan-dictionaries).

## Requires

It comes already with the `JPDB v2.2 Kana Display Only` dictionary from [yomitan-dictionaries](https://github.com/Kuuuube/yomitan-dictionaries). Changing it is a matter of renaming a couple paths in the code.

The manifest already includes the lightweight dictionary `unidic-lite`. If you want to use the latest [UniDic](https://github.com/SamuraiT/mecab-python3?tab=readme-ov-file#dictionaries), you can run:
```
pip uninstall unidic-lite # Optional
pip install unidic
python -m unidic download
```
