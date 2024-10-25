import argparse
import json
import re
import zipfile
from pathlib import Path

import genanki
import MeCab

FreqDict = dict[str, dict[str, int]]


def load_frequency_dictionary(dict_json_path: Path) -> FreqDict:
    """Load a custom frequency dictionary."""
    if not dict_json_path.exists():
        dict_path_zip = dict_json_path.with_suffix(".zip")
        if not dict_path_zip.exists():
            print(f"Could not find the zipped dictionary at {dict_path_zip}")
            exit(0)
        create_frequency_dictionary(dict_path_zip)

    with dict_json_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def create_frequency_dictionary(dict_path_zip: Path) -> None:
    """Unzip and adapt a yomitan frequency dictionary from jpdb."""
    with zipfile.ZipFile(dict_path_zip, "r") as zip_file:
        with zip_file.open("term_meta_bank_1.json") as json_file:
            data = json.load(json_file)

    frequency_dict: FreqDict = {}
    for entry in data:
        word, _, last = entry
        if word not in frequency_dict:
            frequency_dict[word] = {}

        if "reading" in last:
            # The word is a kanji compound
            frequency_dict[word][last["reading"]] = last["frequency"]["value"]
        else:
            # The word is already in hiragana / katakana
            # Some words like は can have multiple entries. We keep the most frequent.
            if word not in frequency_dict[word]:
                frequency_dict[word][word] = last["value"]

    with dict_path_zip.with_suffix(".json").open("w", encoding="utf-8") as output_file:
        json.dump(frequency_dict, output_file, ensure_ascii=False)

    print(f"Cached frequency dict at {dict_path_zip.with_suffix(".json")}")


def segment_text(text: str) -> list[str]:
    """Get segmented words."""
    tagger = MeCab.Tagger("-Owakati")
    return tagger.parse(text).split()


def get_min_frequency(word: str, frequency_dict: FreqDict) -> int:
    """Get the min frequency amongst all the readings.
    Returns 0 if the word is not found in the dictionary."""
    try:
        readings = frequency_dict[word]
        return min(readings.values())
    except KeyError:
        return 0


def get_cards(
    text: str,
    frequency_dict: FreqDict,
    *,
    sentence_separator=r"。",
    lower_freq_bound: int = 500,
    min_number_sentences: int = 1,
    reverse_order: bool,
):
    # We use 0 to discard words not found in frequency_dict
    assert lower_freq_bound > 0

    sentences = re.split(sentence_separator, text)

    cards = {}
    for sentence in sentences:
        _words = segment_text(sentence)
        words = list(set(_words))
        for word in words:
            frequency = get_min_frequency(word, frequency_dict)
            if frequency < lower_freq_bound:
                continue

            if word not in cards:
                cards[word] = {
                    "frequency": frequency,
                    "readings": frequency_dict[word].keys(),
                    "sentences": [sentence],
                }
            else:
                cards[word]["sentences"].append(sentence)

    sorted_cards = sorted(cards.items(), key=lambda p: p[1]["frequency"])

    # Filter by min_number_sentences:
    if min_number_sentences > 1:
        sorted_cards = [sc for sc in sorted_cards if len(sc[1]["sentences"]) > min_number_sentences]

    if reverse_order:
        sorted_cards = sorted_cards[::-1]

    # Debug
    print_summary(sorted_cards)

    cards = dict(sorted_cards)

    return cards


def print_summary(sorted_cards):
    f_header = "Frequency"
    s_header = "Sentences"
    f_pad = len(f_header)
    s_pad = len(s_header)
    print(f"{f_header:>{f_pad}}  {s_header:>{s_pad}}  Word")

    for card, info in sorted_cards[:5]:
        freq, n_sen = info["frequency"], info["sentences"]
        print(f"{freq:{f_pad}}  {len(n_sen):{s_pad}}  {card}")

    for _ in range(2):
        print(" " * (f_pad + s_pad) + "...")

    for card, info in sorted_cards[-5:]:
        freq, n_sen = info["frequency"], info["sentences"]
        print(f"{freq:{f_pad}}  {len(n_sen):{s_pad}}  {card}")

    print(f"\nTotal cards: {len(sorted_cards)}")


def create_anki_deck_from_cards(deck_name: str, cards: dict):
    # TODO: move this somewhere else

    # python3 -c "import random; print(random.randrange(1 << 30, 1 << 31))"
    deck_id = 2028942093
    deck = genanki.Deck(deck_id, deck_name)

    # Create a model for the cards (basic front and back template)
    model_id = 1098333037
    model = genanki.Model(
        model_id,
        "Simple Model",
        fields=[
            {"name": "Word"},
            {"name": "Readings"},
            {"name": "Sentences"},
            {"name": "Frequency"},
        ],
        templates=[
            {
                "name": "Card Template",
                "qfmt": '<div style="text-align:center; font-size:40; font-weight:bold;">{{Word}}</div>'
                '<div style="text-align:center; font-size:16px; color:gray;">Frequency: {{Frequency}}</div>'
                '<div style="text-align:left; margin-top:24px; font-size:20px; padding-left:30px;">{{Sentences}}</div>',
                "afmt": '{{FrontSide}}<hr id="answer">'
                '<div style="text-align:center; font-size:30px; color:blue;">{{Readings}}</div>',
            },
        ],
    )

    # Create notes (individual cards) and add them to the deck
    for word, data in cards.items():
        readings = ", ".join(data["readings"])
        # sentences with Jisho links on the index number
        sentences = "<br>".join(
            f'<a href="https://jisho.org/search/{sentence}" target="_blank">{idx}.</a> '
            f"{sentence.replace(word, f'<strong>{word}</strong>')}"
            for idx, sentence in enumerate(data["sentences"], 1)
        )
        frequency = str(data["frequency"])

        note = genanki.Note(model=model, fields=[word, readings, sentences, frequency])
        deck.add_note(note)

    # Create a package and save the deck
    deck_package = genanki.Package(deck)
    deck_path = f"{deck_name}.apkg"
    deck_package.write_to_file(deck_path)
    print(f"Wrote deck to destination: {deck_path}")


def read_text_or_folder(path: Path) -> str:
    """Read a text file if given a path with a text extension (.txt, .srt, etc.).
    When given a folder, read and merge every text file inside (not recursive)."""
    # It should work with more, but I only tested these:
    valid_extensions = {".txt", ".srt"}

    if path.is_file():
        if path.suffix in valid_extensions:
            return path.read_text(encoding="utf-8")
        else:
            raise ValueError(f"File {path} does not have a valid text extension.")
    elif path.is_dir():
        merged_text = []
        for file in path.iterdir():
            if file.is_file() and file.suffix in valid_extensions:
                merged_text.append(file.read_text(encoding="utf-8"))
        return "\n".join(merged_text)
    else:
        raise ValueError(f"Path {path} is neither a valid file nor a directory.")


def book2anki(
    ipath: Path,
    lower_freq_bound: int,
    min_number_sentences: int,
) -> None:
    dict_json_path = Path("src") / "fdict" / "JPDB_v2.2_Frequency_Kana_2024-10-13.json"
    frequency_dict = load_frequency_dictionary(dict_json_path)

    text = read_text_or_folder(ipath)

    cards = get_cards(
        text,
        frequency_dict,
        sentence_separator=r"\n",
        lower_freq_bound=lower_freq_bound,
        min_number_sentences=min_number_sentences,
        reverse_order=False,
    )

    create_anki_deck_from_cards("dict", cards)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert text files into Anki cards.",
    )
    parser.add_argument(
        "-i",
        "--ipath",
        type=Path,
        default=Path("media/GTO/GTO19draft.srt"),
        help="Input path to a text file or a folder containing text files.",
    )
    parser.add_argument(
        "-f",
        dest="lower_freq_bound",
        type=int,
        default=1,
        help="Lower frequency bound.",
    )
    parser.add_argument(
        "-s",
        dest="min_n_sentences",
        type=int,
        default=1,
        help="Minimum number of sentences.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    book2anki(
        args.ipath,
        args.lower_freq_bound,
        args.min_n_sentences,
    )


if __name__ == "__main__":
    main()
